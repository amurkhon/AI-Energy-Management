from datetime import datetime
from pydantic import BaseModel


class ConsumptionBucket(BaseModel):
    timestamp: datetime
    total_kwh: float
    avg_power_kw: float
    peak_power_kw: float


class EfficiencyStats(BaseModel):
    renewable_fraction: float
    self_sufficiency_ratio: float
    total_production_kwh: float
    total_consumption_kwh: float
    net_kwh: float


class HeatmapCell(BaseModel):
    hour: int
    day_of_week: int
    avg_kwh: float
    count: int = 1


class CostEstimate(BaseModel):
    total_kwh: float
    tariff_type: str
    estimated_cost: float
    currency: str = "USD"
