"""
EUI (Energy Use Intensity) benchmarks per building profile.
Source: ASHRAE 90.1, CBECS 2018, DOE Building Performance Database.

EUI = total kWh / floor_area_m² / year
Efficiency score = 0–100 (100 = best)
"""

from dataclasses import dataclass


@dataclass
class EUIBenchmark:
    profile: str
    # kWh/m²/year thresholds
    excellent: float   # top 25% → score 85–100
    good: float        # median   → score 60–84
    moderate: float    # bottom 25% → score 35–59
    # anything above moderate threshold → score 0–34

    # HVAC share benchmarks (fraction of total)
    hvac_efficient: float = 0.30
    hvac_moderate: float  = 0.50

    # Renewable fraction benchmarks
    renewable_good: float = 0.30
    renewable_excellent: float = 0.60


BENCHMARKS: dict[str, EUIBenchmark] = {
    "residential": EUIBenchmark(
        profile="residential",
        excellent=80.0,
        good=130.0,
        moderate=200.0,
        hvac_efficient=0.35,
        hvac_moderate=0.55,
        renewable_good=0.25,
        renewable_excellent=0.50,
    ),
    "commercial": EUIBenchmark(
        profile="commercial",
        excellent=120.0,
        good=200.0,
        moderate=320.0,
        hvac_efficient=0.40,
        hvac_moderate=0.60,
        renewable_good=0.20,
        renewable_excellent=0.45,
    ),
    "industrial": EUIBenchmark(
        profile="industrial",
        excellent=200.0,
        good=400.0,
        moderate=650.0,
        hvac_efficient=0.20,
        hvac_moderate=0.35,
        renewable_good=0.15,
        renewable_excellent=0.35,
    ),
}


def get_benchmark(profile: str) -> EUIBenchmark:
    return BENCHMARKS.get(profile, BENCHMARKS["residential"])


def eui_to_label(eui_annual: float, profile: str) -> str:
    """Convert annualized EUI to 3-class label."""
    bm = get_benchmark(profile)
    if eui_annual <= bm.excellent:
        return "efficient"
    elif eui_annual <= bm.good:
        return "good"
    elif eui_annual <= bm.moderate:
        return "moderate"
    else:
        return "inefficient"


def eui_to_score(eui_annual: float, profile: str) -> float:
    """
    Convert annualized EUI to a 0–100 efficiency score.
    Lower EUI = higher score.
    """
    bm = get_benchmark(profile)
    if eui_annual <= bm.excellent:
        # Score 85–100
        ratio = eui_annual / bm.excellent
        return round(100 - ratio * 15, 1)
    elif eui_annual <= bm.good:
        # Score 60–84
        ratio = (eui_annual - bm.excellent) / (bm.good - bm.excellent)
        return round(84 - ratio * 24, 1)
    elif eui_annual <= bm.moderate:
        # Score 35–59
        ratio = (eui_annual - bm.good) / (bm.moderate - bm.good)
        return round(59 - ratio * 24, 1)
    else:
        # Score 0–34
        ratio = min(1.0, (eui_annual - bm.moderate) / bm.moderate)
        return round(max(0.0, 34 - ratio * 34), 1)
