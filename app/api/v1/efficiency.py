"""
Efficiency scoring API endpoints.

GET  /api/v1/efficiency/score          — current efficiency score for user's devices
GET  /api/v1/efficiency/score/{device_id} — score for a specific device
GET  /api/v1/efficiency/history        — score history over time
POST /api/v1/efficiency/analyze        — trigger on-demand efficiency analysis
"""

import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import pandas as pd

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.device import Device
from app.models.reading import EnergyReading
from app.ai.efficiency.classifier import predict_from_df
from app.ai.efficiency.labeler import build_training_dataset
from app.core.exceptions import NotFoundError

router = APIRouter(prefix="/efficiency", tags=["efficiency"])


async def _score_device(device: Device, db: AsyncSession, hours: int = 24) -> dict:
    """Compute efficiency score for a single device using last N hours of readings."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = await db.execute(
        select(EnergyReading)
        .where(EnergyReading.device_id == device.id, EnergyReading.recorded_at >= since)
        .order_by(EnergyReading.recorded_at.asc())
    )
    readings = result.scalars().all()

    if not readings:
        return {
            "device_id": str(device.id),
            "device_name": device.name,
            "device_type": device.device_type.value,
            "profile": device.sim_profile.value,
            "efficiency_score": None,
            "label": "unknown",
            "confidence": 0.0,
            "model_used": "none",
            "readings_count": 0,
        }

    df = pd.DataFrame([{
        "recorded_at": r.recorded_at,
        "power_kw": r.power_kw,
        "energy_kwh": r.energy_kwh,
    } for r in readings])

    prediction = predict_from_df(df, profile=device.sim_profile.value)

    return {
        "device_id": str(device.id),
        "device_name": device.name,
        "device_type": device.device_type.value,
        "profile": device.sim_profile.value,
        "efficiency_score": prediction["efficiency_score"],
        "label": prediction["label"],
        "confidence": prediction["confidence"],
        "model_used": prediction["model_used"],
        "readings_count": len(readings),
        "period_hours": hours,
    }


@router.get("/score")
async def efficiency_score(
    hours: int = Query(24, ge=1, le=720, description="Look-back window in hours"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns current efficiency score for all user devices combined,
    plus per-device breakdown.
    """
    result = await db.execute(
        select(Device).where(Device.user_id == current_user.id, Device.is_active == True)
    )
    devices = result.scalars().all()

    device_scores = []
    for device in devices:
        score = await _score_device(device, db, hours)
        device_scores.append(score)

    # Aggregate: weighted average by readings count
    scored = [s for s in device_scores if s["efficiency_score"] is not None]
    if scored:
        total_weight = sum(s["readings_count"] for s in scored)
        if total_weight > 0:
            overall_score = sum(
                s["efficiency_score"] * s["readings_count"] for s in scored
            ) / total_weight
        else:
            overall_score = sum(s["efficiency_score"] for s in scored) / len(scored)

        # Overall label from score
        if overall_score >= 80:
            overall_label = "efficient"
        elif overall_score >= 60:
            overall_label = "good"
        elif overall_score >= 35:
            overall_label = "moderate"
        else:
            overall_label = "inefficient"
    else:
        overall_score = None
        overall_label = "unknown"

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "period_hours": hours,
        "overall_score": round(overall_score, 1) if overall_score is not None else None,
        "overall_label": overall_label,
        "device_count": len(devices),
        "devices": device_scores,
    }


@router.get("/score/{device_id}")
async def device_efficiency_score(
    device_id: uuid.UUID,
    hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Device).where(Device.id == device_id, Device.user_id == current_user.id)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise NotFoundError("Device not found")

    return await _score_device(device, db, hours)


@router.get("/history")
async def efficiency_history(
    days: int = Query(7, ge=1, le=90),
    device_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns daily efficiency scores over the last N days.
    Uses 24h windows per day for each device.
    """
    if device_id:
        result = await db.execute(
            select(Device).where(Device.id == device_id, Device.user_id == current_user.id)
        )
        device = result.scalar_one_or_none()
        if not device:
            raise NotFoundError("Device not found")
        devices = [device]
    else:
        result = await db.execute(
            select(Device).where(Device.user_id == current_user.id, Device.is_active == True)
        )
        devices = result.scalars().all()

    if not devices:
        return {"history": []}

    device_ids = [d.id for d in devices]
    since = datetime.now(timezone.utc) - timedelta(days=days)

    readings_result = await db.execute(
        select(EnergyReading)
        .where(EnergyReading.device_id.in_(device_ids), EnergyReading.recorded_at >= since)
        .order_by(EnergyReading.recorded_at.asc())
    )
    readings = readings_result.scalars().all()

    if not readings:
        return {"history": []}

    df = pd.DataFrame([{
        "recorded_at": r.recorded_at,
        "power_kw": r.power_kw,
        "energy_kwh": r.energy_kwh,
    } for r in readings])

    # Sample one score per day
    history = []
    profile = devices[0].sim_profile.value
    for day_offset in range(days):
        day_start = since + timedelta(days=day_offset)
        day_end = day_start + timedelta(hours=24)
        day_df = df[(df["recorded_at"] >= day_start) & (df["recorded_at"] < day_end)]
        if len(day_df) >= 10:
            pred = predict_from_df(day_df, profile=profile)
            history.append({
                "date": day_start.date().isoformat(),
                "efficiency_score": pred["efficiency_score"],
                "label": pred["label"],
            })

    return {
        "device_count": len(devices),
        "days": days,
        "history": history,
    }


@router.post("/analyze", status_code=202)
async def trigger_analysis(
    current_user: User = Depends(get_current_user),
):
    """Trigger on-demand efficiency analysis (same as AI suggestions but focused on efficiency)."""
    from app.ai.engine import run_ai_analysis
    from fastapi import BackgroundTasks
    # Run synchronously in background
    import asyncio
    asyncio.create_task(run_ai_analysis(str(current_user.id)))
    return {"message": "Efficiency analysis triggered", "user_id": str(current_user.id)}
