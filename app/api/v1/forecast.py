"""
User-driven forecasting endpoint.
Accepts user-supplied parameters and returns GBM (or analytical fallback) predictions.
"""
from datetime import datetime, timezone, timedelta
from typing import Literal
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import json

from app.db.session import get_db
from app.cache.client import get_redis
from app.cache.keys import device_latest
from app.dependencies import get_current_user
from app.models.user import User
from app.models.device import Device
from app.models.reading import EnergyReading
from app.ai.forecasting.load_forecaster import forecast_from_features, load_forecaster

router = APIRouter(prefix="/forecast", tags=["forecast"])

FLAT_RATE = 0.15   # USD/kWh
TOU_PEAK = 0.24
TOU_OFFPEAK = 0.07
HORIZONS = ["1h", "6h", "24h", "7d"]


class ForecastRequest(BaseModel):
    device_id: str | None = Field(None, description="Device UUID; omit to use aggregate")
    target_datetime: datetime = Field(..., description="Start of forecast window (UTC)")
    temperature_c: float = Field(20.0, ge=-20, le=60, description="Ambient temperature °C")
    current_power_kw: float | None = Field(None, description="Current power (kW); auto-filled if omitted")
    horizons: list[Literal["1h", "6h", "24h", "7d"]] = Field(
        default=["1h", "6h", "24h", "7d"], description="Forecast horizons to return"
    )


class HorizonPrediction(BaseModel):
    horizon: str
    predicted_kwh: float
    lower_kwh: float
    upper_kwh: float
    estimated_cost_flat: float
    estimated_cost_tou: float
    model: str


class ForecastResponse(BaseModel):
    device_id: str | None
    device_name: str
    target_datetime: str
    features_used: dict
    predictions: list[HorizonPrediction]
    model_trained: bool


@router.get("/devices")
async def list_forecast_devices(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List user's devices with model availability info."""
    res = await db.execute(
        select(Device).where(Device.user_id == current_user.id, Device.is_active == True)
    )
    devices = list(res.scalars())
    return [
        {
            "device_id": str(d.id),
            "name": d.name,
            "device_type": d.device_type.value,
            "model_trained": any(
                load_forecaster(str(d.id), h) is not None for h in ["1h", "6h"]
            ),
        }
        for d in devices
    ]


@router.post("/predict", response_model=ForecastResponse)
async def predict(
    body: ForecastRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # ── Resolve device ────────────────────────────────────────────────────────
    device = None
    device_name = "Aggregate (all devices)"
    if body.device_id:
        res = await db.execute(
            select(Device).where(Device.id == body.device_id, Device.user_id == current_user.id)
        )
        device = res.scalar_one_or_none()
        device_name = device.name if device else "Unknown device"

    # ── Build feature vector ──────────────────────────────────────────────────
    dt = body.target_datetime
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    hour = dt.hour
    dow = dt.weekday()  # 0=Mon … 6=Sun
    is_weekend = 1 if dow >= 5 else 0

    # Auto-fill current power from Redis or last DB reading
    lag_1h = body.current_power_kw
    lag_24h = 0.0
    lag_168h = 0.0

    if device:
        device_ids = [device.id]
    else:
        dev_res = await db.execute(
            select(Device.id).where(Device.user_id == current_user.id, Device.is_active == True)
        )
        device_ids = list(dev_res.scalars())

    if device_ids:
        # lag_1h from most recent reading
        if lag_1h is None:
            r1 = await db.execute(
                select(func.avg(EnergyReading.power_kw))
                .where(
                    EnergyReading.device_id.in_(device_ids),
                    EnergyReading.recorded_at >= dt - timedelta(hours=2),
                    EnergyReading.recorded_at <= dt,
                )
            )
            lag_1h = abs(float(r1.scalar() or 2.0))

        # lag_24h
        r24 = await db.execute(
            select(func.avg(EnergyReading.power_kw))
            .where(
                EnergyReading.device_id.in_(device_ids),
                EnergyReading.recorded_at >= dt - timedelta(hours=25),
                EnergyReading.recorded_at <= dt - timedelta(hours=23),
            )
        )
        lag_24h = abs(float(r24.scalar() or 2.0))

        # lag_168h
        r168 = await db.execute(
            select(func.avg(EnergyReading.power_kw))
            .where(
                EnergyReading.device_id.in_(device_ids),
                EnergyReading.recorded_at >= dt - timedelta(hours=169),
                EnergyReading.recorded_at <= dt - timedelta(hours=167),
            )
        )
        lag_168h = abs(float(r168.scalar() or 2.0))

    if lag_1h is None:
        lag_1h = 2.0

    features = {
        "hour_of_day": hour,
        "day_of_week": dow,
        "is_weekend": is_weekend,
        "temperature_c": body.temperature_c,
        "lag_1h": lag_1h,
        "lag_24h": lag_24h,
        "lag_168h": lag_168h,
    }

    device_id_str = str(device.id) if device else None
    model_trained = (
        load_forecaster(device_id_str, "1h") is not None
        if device_id_str else False
    )

    # ── Run predictions ───────────────────────────────────────────────────────
    predictions = []
    for h in body.horizons:
        pred = forecast_from_features(features, device_id_str, h)
        kwh = pred["predicted_kwh"]
        hours_count = {"1h": 1, "6h": 6, "24h": 24, "7d": 168}[h]
        cost_flat = round(kwh * FLAT_RATE, 2)
        # TOU cost: assume half of window is peak (rough estimate)
        peak_kwh = kwh * 0.6 if 8 <= hour < 22 else kwh * 0.3
        off_kwh = kwh - peak_kwh
        cost_tou = round(peak_kwh * TOU_PEAK + off_kwh * TOU_OFFPEAK, 2)
        predictions.append(HorizonPrediction(
            horizon=h,
            predicted_kwh=pred["predicted_kwh"],
            lower_kwh=pred["lower_bound_kwh"],
            upper_kwh=pred["upper_bound_kwh"],
            estimated_cost_flat=cost_flat,
            estimated_cost_tou=cost_tou,
            model=pred["model"],
        ))

    return ForecastResponse(
        device_id=device_id_str,
        device_name=device_name,
        target_datetime=dt.isoformat(),
        features_used=features,
        predictions=predictions,
        model_trained=model_trained,
    )
