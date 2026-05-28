"""
Unified AI Insights endpoint.
Aggregates anomaly records, GBM forecasts, renewable stats,
efficiency scores, and load-shift opportunities from real device readings.
"""
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import pandas as pd

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.device import Device, DeviceType
from app.models.reading import EnergyReading
from app.models.prediction import AnomalyRecord
from app.ai.efficiency.classifier import predict_from_df
from app.ai.feature_engineering import build_features, build_forecast_features
from app.ai.forecasting.load_forecaster import forecast as run_forecast
from app.ai.optimization.scheduler import load_shift_suggestion

router = APIRouter(prefix="/insights", tags=["insights"])


def _score_label(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score >= 80:
        return "efficient"
    if score >= 60:
        return "good"
    if score >= 35:
        return "moderate"
    return "inefficient"


@router.get("")
async def get_insights(
    hours: int = Query(24, ge=1, le=168, description="Look-back window in hours"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)

    # User's active devices
    devices_res = await db.execute(
        select(Device).where(Device.user_id == current_user.id, Device.is_active == True)
    )
    devices = list(devices_res.scalars())
    device_ids = [d.id for d in devices]
    device_map = {str(d.id): d for d in devices}

    if not device_ids:
        return _empty_response(now, hours)

    # ── 1. Anomaly records ────────────────────────────────────────────────────
    anomalies_res = await db.execute(
        select(AnomalyRecord)
        .where(AnomalyRecord.device_id.in_(device_ids), AnomalyRecord.detected_at >= since)
        .order_by(AnomalyRecord.detected_at.desc())
        .limit(30)
    )
    anomaly_records = list(anomalies_res.scalars())
    anomalies_out = [
        {
            "id": str(a.id),
            "device_id": str(a.device_id),
            "device_name": device_map[str(a.device_id)].name if str(a.device_id) in device_map else "Unknown",
            "device_type": device_map[str(a.device_id)].device_type.value if str(a.device_id) in device_map else "",
            "anomaly_type": a.anomaly_type.value,
            "expected_value": a.expected_value,
            "actual_value": a.actual_value,
            "z_score": a.z_score,
            "detected_at": a.detected_at.isoformat(),
        }
        for a in anomaly_records
    ]

    # ── 2. GBM Forecasts per device ───────────────────────────────────────────
    forecasts = []
    for device in devices:
        df = await build_features(str(device.id), db, hours=hours)
        if df.empty or len(df) < 5:
            continue
        fdf = build_forecast_features(df)
        device_preds = {}
        for horizon in ["1h", "6h", "24h"]:
            pred = run_forecast(fdf, str(device.id), horizon)
            if pred:
                device_preds[horizon] = pred
        if device_preds:
            forecasts.append({
                "device_id": str(device.id),
                "device_name": device.name,
                "device_type": device.device_type.value,
                "predictions": device_preds,
            })

    # ── 3. Renewable stats ────────────────────────────────────────────────────
    prod_ids = [d.id for d in devices if d.device_type in (DeviceType.solar_panel, DeviceType.wind_turbine)]

    total_kwh_res = await db.execute(
        select(func.sum(EnergyReading.energy_kwh))
        .where(EnergyReading.device_id.in_(device_ids), EnergyReading.recorded_at >= since)
    )
    total_kwh = float(total_kwh_res.scalar() or 0)

    renewable_kwh = 0.0
    if prod_ids:
        prod_res = await db.execute(
            select(func.sum(EnergyReading.energy_kwh))
            .where(EnergyReading.device_id.in_(prod_ids), EnergyReading.recorded_at >= since)
        )
        renewable_kwh = float(prod_res.scalar() or 0)

    consumption_kwh = abs(total_kwh - renewable_kwh)
    renewable_fraction = round(renewable_kwh / consumption_kwh, 3) if consumption_kwh > 0 else 0.0

    renewable = {
        "fraction": renewable_fraction,
        "total_production_kwh": round(renewable_kwh, 3),
        "total_consumption_kwh": round(consumption_kwh, 3),
        "net_kwh": round(renewable_kwh - consumption_kwh, 3),
        "self_sufficiency": round(min(renewable_fraction, 1.0), 3),
        "producing_devices": len(prod_ids),
    }

    # ── 4. Efficiency scores ──────────────────────────────────────────────────
    readings_res = await db.execute(
        select(EnergyReading)
        .where(EnergyReading.device_id.in_(device_ids), EnergyReading.recorded_at >= since)
        .order_by(EnergyReading.recorded_at.asc())
    )
    all_readings = list(readings_res.scalars())

    efficiency_devices = []
    for device in devices:
        dev_readings = [r for r in all_readings if r.device_id == device.id]
        if not dev_readings:
            efficiency_devices.append({
                "device_id": str(device.id),
                "device_name": device.name,
                "device_type": device.device_type.value,
                "efficiency_score": None,
                "label": "unknown",
                "confidence": 0.0,
                "readings_count": 0,
            })
            continue
        df = pd.DataFrame([{"recorded_at": r.recorded_at, "power_kw": r.power_kw, "energy_kwh": r.energy_kwh} for r in dev_readings])
        pred = predict_from_df(df, profile=device.sim_profile.value)
        efficiency_devices.append({
            "device_id": str(device.id),
            "device_name": device.name,
            "device_type": device.device_type.value,
            "efficiency_score": pred["efficiency_score"],
            "label": pred["label"],
            "confidence": pred["confidence"],
            "readings_count": len(dev_readings),
        })

    scored = [(d["efficiency_score"], d["readings_count"]) for d in efficiency_devices if d["efficiency_score"] is not None]
    if scored:
        total_w = sum(w for _, w in scored) or 1
        overall_score = round(sum(s * w for s, w in scored) / total_w, 1)
    else:
        overall_score = None

    efficiency = {
        "overall_score": overall_score,
        "overall_label": _score_label(overall_score),
        "devices": efficiency_devices,
    }

    # ── 5. Load-shifting opportunities ────────────────────────────────────────
    current_hour = now.hour
    opportunities = []
    for device in devices:
        d = {"id": str(device.id), "name": device.name, "device_type": device.device_type.value, "rated_capacity": device.rated_capacity}
        shift = load_shift_suggestion(d, current_hour, device.rated_capacity)
        if shift:
            opportunities.append({"device_id": str(device.id), "device_name": device.name, **shift})

    load_shifting = {
        "current_hour": current_hour,
        "current_rate_usd_kwh": _current_rate(current_hour),
        "opportunities": opportunities,
        "total_potential_saving_usd": round(sum(o.get("estimated_saving_cost", 0) for o in opportunities), 2),
    }

    return {
        "generated_at": now.isoformat(),
        "period_hours": hours,
        "device_count": len(devices),
        "anomalies": anomalies_out,
        "forecasts": forecasts,
        "renewable": renewable,
        "efficiency": efficiency,
        "load_shifting": load_shifting,
    }


def _current_rate(hour: int) -> float:
    return 0.20 if 8 <= hour < 22 else 0.08


def _empty_response(now: datetime, hours: int) -> dict:
    return {
        "generated_at": now.isoformat(),
        "period_hours": hours,
        "device_count": 0,
        "anomalies": [],
        "forecasts": [],
        "renewable": {"fraction": 0, "total_production_kwh": 0, "total_consumption_kwh": 0, "net_kwh": 0, "self_sufficiency": 0, "producing_devices": 0},
        "efficiency": {"overall_score": None, "overall_label": "unknown", "devices": []},
        "load_shifting": {"current_hour": now.hour, "current_rate_usd_kwh": _current_rate(now.hour), "opportunities": [], "total_potential_saving_usd": 0},
    }
