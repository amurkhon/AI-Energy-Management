from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.analytics import ConsumptionBucket, EfficiencyStats, HeatmapCell, CostEstimate
from app.simulation.analytics_sim import (
    sim_consumption,
    sim_production,
    sim_efficiency,
    sim_cost,
    sim_heatmap,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _default_from() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=7)


def _default_to() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/consumption", response_model=list[ConsumptionBucket])
async def consumption(
    from_dt: datetime = Query(default_factory=_default_from),
    to_dt: datetime = Query(default_factory=_default_to),
    granularity: str = Query("hour", pattern="^(hour|day|week)$"),
    current_user: User = Depends(get_current_user),
):
    return sim_consumption(from_dt, to_dt, granularity)


@router.get("/production", response_model=list[ConsumptionBucket])
async def production(
    from_dt: datetime = Query(default_factory=_default_from),
    to_dt: datetime = Query(default_factory=_default_to),
    granularity: str = Query("hour", pattern="^(hour|day|week)$"),
    current_user: User = Depends(get_current_user),
):
    return sim_production(from_dt, to_dt, granularity)


@router.get("/efficiency", response_model=EfficiencyStats)
async def efficiency(
    from_dt: datetime = Query(default_factory=lambda: datetime.now(timezone.utc) - timedelta(days=1)),
    to_dt: datetime = Query(default_factory=_default_to),
    current_user: User = Depends(get_current_user),
):
    return sim_efficiency(from_dt, to_dt)


@router.get("/cost", response_model=CostEstimate)
async def cost(
    tariff_type: str = Query("flat", pattern="^(flat|tou)$"),
    from_dt: datetime = Query(default_factory=lambda: datetime.now(timezone.utc) - timedelta(days=1)),
    to_dt: datetime = Query(default_factory=_default_to),
    current_user: User = Depends(get_current_user),
):
    return sim_cost(from_dt, to_dt, tariff_type)


@router.get("/heatmap", response_model=list[HeatmapCell])
async def heatmap(
    from_dt: datetime = Query(default_factory=lambda: datetime.now(timezone.utc) - timedelta(days=30)),
    to_dt: datetime = Query(default_factory=_default_to),
    current_user: User = Depends(get_current_user),
):
    return sim_heatmap(from_dt, to_dt)
