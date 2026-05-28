"""
Simulated analytics data for the AI Energy Management dashboard.
Generates realistic patterns (daily load curves, solar production, cost tariffs).
Replace these functions with real DB queries when live device data is available.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

# Hourly load profile in kW (weekday) — 24 values
_WEEKDAY_LOAD_KW = [
    0.8, 0.7, 0.6, 0.6, 0.7, 1.0,   # 00-05
    2.0, 3.2, 2.8, 1.8, 1.5, 1.6,   # 06-11
    1.8, 1.7, 1.6, 1.8, 2.2, 3.5,   # 12-17
    4.0, 3.8, 3.2, 2.5, 1.8, 1.2,   # 18-23
]

# Weekend: more home usage during the day
_WEEKEND_LOAD_KW = [
    0.9, 0.8, 0.7, 0.7, 0.8, 1.1,
    1.6, 2.0, 2.5, 2.8, 3.0, 3.2,
    3.5, 3.3, 3.0, 2.8, 2.6, 3.2,
    3.8, 3.5, 2.9, 2.2, 1.7, 1.2,
]

# Solar production fraction of 4 kW peak (bell curve, daytime only)
_SOLAR_FRACTION = [
    0, 0, 0, 0, 0, 0.02,
    0.08, 0.20, 0.42, 0.65, 0.85, 0.97,
    1.0, 0.97, 0.85, 0.65, 0.42, 0.20,
    0.08, 0.02, 0, 0, 0, 0,
]
SOLAR_PEAK_KW = 4.0

FLAT_RATE = 0.15          # USD/kWh — baseline unoptimized tariff
TOU_PEAK_RATE = 0.24      # 08:00–22:00 — expensive peak
TOU_OFFPEAK_RATE = 0.06   # 22:00–08:00 — cheap off-peak
# AI shifts 45% of peak load (EV, HVAC, appliances) to off-peak via scheduler
DEFERRABLE_SHARE = 0.45


def _noise(seed: int, scale: float = 0.14) -> float:
    """Deterministic noise seeded by integer so data is stable per session."""
    return 1.0 + random.Random(seed).uniform(-scale, scale)


def _solar_day_factor(date: datetime) -> float:
    """Day-level weather factor (0.4–1.0) so each day looks different."""
    return random.Random(date.toordinal()).uniform(0.4, 1.0)


def _hourly_consumption(dt: datetime) -> float:
    """Return expected consumption kWh for one hour at given datetime."""
    profile = _WEEKEND_LOAD_KW if dt.weekday() >= 5 else _WEEKDAY_LOAD_KW
    base = profile[dt.hour]
    return round(base * _noise(dt.day * 31 + dt.hour), 3)


def _hourly_production(dt: datetime) -> float:
    """Return expected solar production kWh for one hour at given datetime."""
    fraction = _SOLAR_FRACTION[dt.hour]
    weather = _solar_day_factor(dt)
    return round(SOLAR_PEAK_KW * fraction * weather * _noise(dt.toordinal() * 24 + dt.hour, 0.10), 3)


def _iter_buckets(from_dt: datetime, to_dt: datetime, granularity: str):
    """Yield bucket start datetimes."""
    delta = {"hour": timedelta(hours=1), "day": timedelta(days=1), "week": timedelta(weeks=1)}[granularity]
    cur = from_dt.replace(minute=0, second=0, microsecond=0)
    if granularity == "day":
        cur = cur.replace(hour=0)
    elif granularity == "week":
        cur = cur.replace(hour=0) - timedelta(days=cur.weekday())
    while cur < to_dt:
        yield cur
        cur += delta


def sim_consumption(from_dt: datetime, to_dt: datetime, granularity: str):
    from app.schemas.analytics import ConsumptionBucket
    results = []
    for bucket in _iter_buckets(from_dt, to_dt, granularity):
        hours = _hours_in_bucket(bucket, granularity)
        total = sum(_hourly_consumption(bucket + timedelta(hours=h)) for h in range(hours))
        avg_kw = total / hours if hours else 0
        peak_kw = max(_hourly_consumption(bucket + timedelta(hours=h)) for h in range(hours))
        results.append(ConsumptionBucket(
            timestamp=bucket,
            total_kwh=round(total, 3),
            avg_power_kw=round(avg_kw, 3),
            peak_power_kw=round(peak_kw, 3),
        ))
    return results


def sim_production(from_dt: datetime, to_dt: datetime, granularity: str):
    from app.schemas.analytics import ConsumptionBucket
    results = []
    for bucket in _iter_buckets(from_dt, to_dt, granularity):
        hours = _hours_in_bucket(bucket, granularity)
        total = sum(_hourly_production(bucket + timedelta(hours=h)) for h in range(hours))
        avg_kw = total / hours if hours else 0
        peak_kw = max(_hourly_production(bucket + timedelta(hours=h)) for h in range(hours))
        results.append(ConsumptionBucket(
            timestamp=bucket,
            total_kwh=round(total, 3),
            avg_power_kw=round(avg_kw, 3),
            peak_power_kw=round(peak_kw, 3),
        ))
    return results


def sim_efficiency(from_dt: datetime, to_dt: datetime):
    from app.schemas.analytics import EfficiencyStats
    hours = int((to_dt - from_dt).total_seconds() / 3600)
    total_consumption = sum(_hourly_consumption(from_dt + timedelta(hours=h)) for h in range(hours))
    total_production = sum(_hourly_production(from_dt + timedelta(hours=h)) for h in range(hours))
    renewable_fraction = total_production / total_consumption if total_consumption > 0 else 0
    self_sufficiency = min(renewable_fraction, 1.0)
    net_kwh = total_production - total_consumption
    return EfficiencyStats(
        renewable_fraction=round(renewable_fraction, 3),
        self_sufficiency_ratio=round(self_sufficiency, 3),
        total_production_kwh=round(total_production, 3),
        total_consumption_kwh=round(total_consumption, 3),
        net_kwh=round(net_kwh, 3),
    )


def sim_cost(from_dt: datetime, to_dt: datetime, tariff_type: str):
    """
    flat → unoptimized baseline at FLAT_RATE.
    tou  → AI-optimized: scheduler shifts DEFERRABLE_SHARE of peak load
           (EV charger, HVAC setbacks, appliances) to off-peak hours,
           making TOU cheaper than the flat baseline.
    """
    from app.schemas.analytics import CostEstimate
    hours = int((to_dt - from_dt).total_seconds() / 3600)

    peak_kwh = 0.0
    offpeak_kwh = 0.0
    for h in range(hours):
        dt = from_dt + timedelta(hours=h)
        kwh = _hourly_consumption(dt)
        if 8 <= dt.hour < 22:
            peak_kwh += kwh
        else:
            offpeak_kwh += kwh
    total_kwh = peak_kwh + offpeak_kwh

    if tariff_type == "flat":
        estimated_cost = total_kwh * FLAT_RATE
    else:
        # AI scheduler moves DEFERRABLE_SHARE of peak load to off-peak
        shifted = peak_kwh * DEFERRABLE_SHARE
        optimized_peak = peak_kwh - shifted
        optimized_offpeak = offpeak_kwh + shifted
        estimated_cost = optimized_peak * TOU_PEAK_RATE + optimized_offpeak * TOU_OFFPEAK_RATE

    return CostEstimate(
        total_kwh=round(total_kwh, 3),
        tariff_type=tariff_type,
        estimated_cost=round(estimated_cost, 2),
    )


def sim_heatmap(from_dt: datetime, to_dt: datetime):
    from app.schemas.analytics import HeatmapCell
    # Accumulate avg_kwh per (dow, hour) using simulated hourly values
    totals: dict[tuple[int, int], list[float]] = {}
    hours = int((to_dt - from_dt).total_seconds() / 3600)
    for h in range(hours):
        dt = from_dt + timedelta(hours=h)
        key = (dt.weekday(), dt.hour)  # 0=Mon … 6=Sun
        totals.setdefault(key, []).append(_hourly_consumption(dt))

    cells = []
    for (dow, hour), vals in sorted(totals.items()):
        cells.append(HeatmapCell(
            hour=hour,
            day_of_week=dow,
            avg_kwh=round(sum(vals) / len(vals), 4),
        ))
    return cells


def _hours_in_bucket(bucket: datetime, granularity: str) -> int:
    return {"hour": 1, "day": 24, "week": 168}[granularity]
