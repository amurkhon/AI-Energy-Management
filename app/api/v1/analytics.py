import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.device import Device, DeviceType
from app.models.reading import EnergyReading, EnergyReadingHourly
from app.schemas.analytics import ConsumptionBucket, EfficiencyStats, HeatmapCell, CostEstimate

router = APIRouter(prefix="/analytics", tags=["analytics"])

FLAT_TARIFF = 0.12  # USD/kWh
TOU_TARIFF = {"peak": 0.20, "off_peak": 0.08}  # peak = 8am-10pm


def _tou_cost(kwh: float, hour: int) -> float:
    if 8 <= hour < 22:
        return kwh * TOU_TARIFF["peak"]
    return kwh * TOU_TARIFF["off_peak"]


async def _user_device_ids(user_id: uuid.UUID, db: AsyncSession, device_type: DeviceType | None = None):
    q = select(Device.id).where(Device.user_id == user_id, Device.is_active == True)
    if device_type:
        q = q.where(Device.device_type == device_type)
    result = await db.execute(q)
    return list(result.scalars())


@router.get("/consumption", response_model=list[ConsumptionBucket])
async def consumption(
    from_dt: datetime = Query(default_factory=lambda: datetime.now(timezone.utc) - timedelta(days=7)),
    to_dt: datetime = Query(default_factory=lambda: datetime.now(timezone.utc)),
    granularity: str = Query("hour", pattern="^(hour|day|week)$"),
    device_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    device_ids = [device_id] if device_id else await _user_device_ids(current_user.id, db)
    trunc = {"hour": "hour", "day": "day", "week": "week"}[granularity]

    result = await db.execute(
        select(
            func.date_trunc(trunc, EnergyReading.recorded_at).label("bucket"),
            func.sum(EnergyReading.energy_kwh).label("total_kwh"),
            func.avg(EnergyReading.power_kw).label("avg_power_kw"),
            func.max(EnergyReading.power_kw).label("peak_power_kw"),
        )
        .where(
            EnergyReading.device_id.in_(device_ids),
            EnergyReading.recorded_at.between(from_dt, to_dt),
            EnergyReading.power_kw < 0,  # consumption = negative power
        )
        .group_by("bucket")
        .order_by("bucket")
    )
    rows = result.all()
    return [
        ConsumptionBucket(
            bucket=r.bucket,
            total_kwh=abs(r.total_kwh or 0),
            avg_power_kw=abs(r.avg_power_kw or 0),
            peak_power_kw=abs(r.peak_power_kw or 0),
        )
        for r in rows
    ]


@router.get("/production", response_model=list[ConsumptionBucket])
async def production(
    from_dt: datetime = Query(default_factory=lambda: datetime.now(timezone.utc) - timedelta(days=7)),
    to_dt: datetime = Query(default_factory=lambda: datetime.now(timezone.utc)),
    granularity: str = Query("hour", pattern="^(hour|day|week)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    production_types = [DeviceType.solar_panel, DeviceType.wind_turbine]
    q = select(Device.id).where(
        Device.user_id == current_user.id,
        Device.is_active == True,
        Device.device_type.in_(production_types),
    )
    result_ids = await db.execute(q)
    device_ids = list(result_ids.scalars())
    if not device_ids:
        return []

    trunc = granularity
    result = await db.execute(
        select(
            func.date_trunc(trunc, EnergyReading.recorded_at).label("bucket"),
            func.sum(EnergyReading.energy_kwh).label("total_kwh"),
            func.avg(EnergyReading.power_kw).label("avg_power_kw"),
            func.max(EnergyReading.power_kw).label("peak_power_kw"),
        )
        .where(
            EnergyReading.device_id.in_(device_ids),
            EnergyReading.recorded_at.between(from_dt, to_dt),
        )
        .group_by("bucket")
        .order_by("bucket")
    )
    rows = result.all()
    return [
        ConsumptionBucket(
            bucket=r.bucket,
            total_kwh=r.total_kwh or 0,
            avg_power_kw=r.avg_power_kw or 0,
            peak_power_kw=r.peak_power_kw or 0,
        )
        for r in rows
    ]


@router.get("/efficiency", response_model=EfficiencyStats)
async def efficiency(
    from_dt: datetime = Query(default_factory=lambda: datetime.now(timezone.utc) - timedelta(days=1)),
    to_dt: datetime = Query(default_factory=lambda: datetime.now(timezone.utc)),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    all_ids = await _user_device_ids(current_user.id, db)
    prod_ids = await _user_device_ids(current_user.id, db, DeviceType.solar_panel)
    wind_ids = await _user_device_ids(current_user.id, db, DeviceType.wind_turbine)
    production_ids = prod_ids + wind_ids

    conditions = and_(EnergyReading.device_id.in_(all_ids), EnergyReading.recorded_at.between(from_dt, to_dt))
    result = await db.execute(
        select(func.sum(EnergyReading.energy_kwh)).where(conditions)
    )
    total_kwh = result.scalar() or 0

    prod_result = await db.execute(
        select(func.sum(EnergyReading.energy_kwh)).where(
            EnergyReading.device_id.in_(production_ids),
            EnergyReading.recorded_at.between(from_dt, to_dt),
        )
    )
    production_kwh = prod_result.scalar() or 0
    consumption_kwh = abs(total_kwh - production_kwh)
    net_kwh = production_kwh - consumption_kwh

    renewable_fraction = production_kwh / consumption_kwh if consumption_kwh > 0 else 0
    self_sufficiency = min(production_kwh / consumption_kwh, 1.0) if consumption_kwh > 0 else 1.0

    return EfficiencyStats(
        renewable_fraction=round(renewable_fraction, 3),
        self_sufficiency_ratio=round(self_sufficiency, 3),
        total_production_kwh=round(production_kwh, 3),
        total_consumption_kwh=round(consumption_kwh, 3),
        net_kwh=round(net_kwh, 3),
    )


@router.get("/cost", response_model=CostEstimate)
async def cost(
    tariff: str = Query("flat", pattern="^(flat|tou)$"),
    from_dt: datetime = Query(default_factory=lambda: datetime.now(timezone.utc) - timedelta(days=1)),
    to_dt: datetime = Query(default_factory=lambda: datetime.now(timezone.utc)),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    device_ids = await _user_device_ids(current_user.id, db)
    result = await db.execute(
        select(EnergyReading.energy_kwh, EnergyReading.recorded_at)
        .where(
            EnergyReading.device_id.in_(device_ids),
            EnergyReading.recorded_at.between(from_dt, to_dt),
            EnergyReading.power_kw < 0,
        )
    )
    rows = result.all()
    total_kwh = sum(abs(r.energy_kwh) for r in rows)

    if tariff == "flat":
        estimated_cost = total_kwh * FLAT_TARIFF
    else:
        estimated_cost = sum(_tou_cost(abs(r.energy_kwh), r.recorded_at.hour) for r in rows)

    return CostEstimate(total_kwh=round(total_kwh, 3), tariff_type=tariff, estimated_cost=round(estimated_cost, 2))


@router.get("/heatmap", response_model=list[HeatmapCell])
async def heatmap(
    from_dt: datetime = Query(default_factory=lambda: datetime.now(timezone.utc) - timedelta(days=30)),
    to_dt: datetime = Query(default_factory=lambda: datetime.now(timezone.utc)),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    device_ids = await _user_device_ids(current_user.id, db)
    result = await db.execute(
        select(
            func.extract("hour", EnergyReading.recorded_at).label("hour"),
            func.extract("dow", EnergyReading.recorded_at).label("dow"),
            func.avg(func.abs(EnergyReading.energy_kwh)).label("avg_kwh"),
        )
        .where(
            EnergyReading.device_id.in_(device_ids),
            EnergyReading.recorded_at.between(from_dt, to_dt),
        )
        .group_by("hour", "dow")
        .order_by("dow", "hour")
    )
    return [HeatmapCell(hour=int(r.hour), day_of_week=int(r.dow), avg_kwh=round(r.avg_kwh or 0, 4)) for r in result.all()]
