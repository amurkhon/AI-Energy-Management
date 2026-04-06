import json
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.db.session import get_db
from app.cache.client import get_redis
from app.cache.keys import device_latest
from app.dependencies import get_current_user
from app.models.user import User
from app.models.device import Device, DeviceType
from app.models.reading import EnergyReading
from app.models.alert import AlertEvent, AlertSeverity
from app.models.suggestion import AISuggestion
import redis.asyncio as aioredis

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
async def dashboard(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    current_user: User = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Active devices
    devices_res = await db.execute(
        select(Device).where(Device.user_id == current_user.id, Device.is_active == True)
    )
    devices = list(devices_res.scalars())
    device_ids = [d.id for d in devices]

    # Current total power from Redis cache
    total_power_kw = 0.0
    battery_soc = None
    for d in devices:
        raw = await redis.get(device_latest(str(d.id)))
        if raw:
            data = json.loads(raw)
            total_power_kw += data.get("power_kw", 0)
            if d.device_type == DeviceType.battery and data.get("state_of_charge") is not None:
                battery_soc = data["state_of_charge"]

    # Today's kWh
    kwh_res = await db.execute(
        select(func.sum(EnergyReading.energy_kwh)).where(
            EnergyReading.device_id.in_(device_ids),
            EnergyReading.recorded_at >= today_start,
        )
    )
    today_kwh = round(kwh_res.scalar() or 0, 3)

    # Active unacknowledged alerts (last 24h)
    rule_ids_res = await db.execute(
        select(__import__('app.models.alert', fromlist=['AlertRule']).AlertRule.id)
        .where(__import__('app.models.alert', fromlist=['AlertRule']).AlertRule.user_id == current_user.id)
    )
    rule_ids = list(rule_ids_res.scalars())

    critical_alerts = 0
    if rule_ids:
        alert_res = await db.execute(
            select(func.count(AlertEvent.id)).where(
                AlertEvent.rule_id.in_(rule_ids),
                AlertEvent.is_acknowledged == False,
                AlertEvent.severity == AlertSeverity.critical,
            )
        )
        critical_alerts = alert_res.scalar() or 0

    # Top suggestions
    sugg_res = await db.execute(
        select(AISuggestion)
        .where(AISuggestion.user_id == current_user.id, AISuggestion.is_dismissed == False)
        .order_by(AISuggestion.generated_at.desc())
        .limit(3)
    )
    top_suggestions = [
        {"id": str(s.id), "title": s.title, "priority": s.priority, "category": s.category}
        for s in sugg_res.scalars()
    ]

    # Renewable production (solar + wind) for today
    prod_types = [DeviceType.solar_panel, DeviceType.wind_turbine]
    prod_ids = [d.id for d in devices if d.device_type in prod_types]
    renewable_kwh = 0.0
    if prod_ids:
        prod_res = await db.execute(
            select(func.sum(EnergyReading.energy_kwh)).where(
                EnergyReading.device_id.in_(prod_ids),
                EnergyReading.recorded_at >= today_start,
            )
        )
        renewable_kwh = round(prod_res.scalar() or 0, 3)

    renewable_pct = round(renewable_kwh / today_kwh * 100, 1) if today_kwh > 0 else 0.0

    return {
        "timestamp": now.isoformat(),
        "total_power_kw": round(total_power_kw, 3),
        "today_kwh": today_kwh,
        "today_renewable_kwh": renewable_kwh,
        "renewable_pct": renewable_pct,
        "battery_soc": battery_soc,
        "active_devices": len(devices),
        "critical_alerts": critical_alerts,
        "top_suggestions": top_suggestions,
    }
