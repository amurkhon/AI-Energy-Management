"""
Converts raw energy readings into labeled feature vectors for classifier training.

Works on both:
  - Real imported data (ASHRAE / PecanStreet CSVs)
  - Simulation-generated data (from energy_readings table)
"""

import pandas as pd
import numpy as np
from app.ai.efficiency.benchmarks import eui_to_label, eui_to_score, get_benchmark


# Default floor area if not known (m²)
DEFAULT_FLOOR_AREA = {
    "residential": 120.0,
    "commercial": 2000.0,
    "industrial": 10000.0,
}

PRODUCTION_DEVICE_TYPES = {"solar_panel", "wind_turbine"}
HVAC_DEVICE_TYPES = {"hvac"}


def compute_features(df: pd.DataFrame, profile: str = "residential", floor_area_m2: float | None = None) -> dict:
    """
    Given a DataFrame of readings for one building over a time window,
    compute the feature vector used for training and inference.

    df must have columns: recorded_at, power_kw, energy_kwh, device_type (optional)
    """
    if df.empty:
        return {}

    area = floor_area_m2 or DEFAULT_FLOOR_AREA.get(profile, 120.0)
    df = df.copy()
    df["recorded_at"] = pd.to_datetime(df["recorded_at"], utc=True)

    # ── Energy totals ─────────────────────────────────────────────────────────
    total_kwh = df["energy_kwh"].abs().sum()
    duration_hours = (df["recorded_at"].max() - df["recorded_at"].min()).total_seconds() / 3600
    duration_years = max(duration_hours / 8760, 1 / 8760)

    # Annualized EUI
    eui_annual = (total_kwh / area) / duration_years

    # ── Production vs consumption ─────────────────────────────────────────────
    if "device_type" in df.columns:
        prod_mask = df["device_type"].isin(PRODUCTION_DEVICE_TYPES)
        hvac_mask = df["device_type"].isin(HVAC_DEVICE_TYPES)
        production_kwh = df.loc[prod_mask, "energy_kwh"].sum()
        hvac_kwh = df.loc[hvac_mask, "energy_kwh"].abs().sum()
    else:
        # Infer: positive power = production, negative = consumption
        production_kwh = df.loc[df["power_kw"] > 0, "energy_kwh"].sum()
        hvac_kwh = 0.0

    consumption_kwh = df.loc[df["power_kw"] < 0, "energy_kwh"].abs().sum()
    if consumption_kwh == 0:
        consumption_kwh = total_kwh

    renewable_fraction = min(1.0, production_kwh / consumption_kwh) if consumption_kwh > 0 else 0.0
    hvac_share = min(1.0, hvac_kwh / consumption_kwh) if consumption_kwh > 0 else 0.0

    # ── Peak analysis ─────────────────────────────────────────────────────────
    avg_power = df["power_kw"].abs().mean()
    peak_power = df["power_kw"].abs().max()
    peak_to_avg = peak_power / avg_power if avg_power > 0 else 1.0

    # ── Time-of-use ratio ─────────────────────────────────────────────────────
    df["hour"] = df["recorded_at"].dt.hour
    off_peak_mask = (df["hour"] < 8) | (df["hour"] >= 22)
    off_peak_kwh = df.loc[off_peak_mask & (df["power_kw"] < 0), "energy_kwh"].abs().sum()
    off_peak_ratio = off_peak_kwh / consumption_kwh if consumption_kwh > 0 else 0.0

    # ── Variability ───────────────────────────────────────────────────────────
    power_std = df["power_kw"].std()
    load_factor = avg_power / peak_power if peak_power > 0 else 1.0  # 1=flat, 0=very spiky

    # ── Temporal features ─────────────────────────────────────────────────────
    hour_of_day = df["recorded_at"].dt.hour.mean()
    is_weekend_frac = (df["recorded_at"].dt.dayofweek >= 5).mean()

    return {
        "eui_annual": round(eui_annual, 2),
        "renewable_fraction": round(renewable_fraction, 4),
        "hvac_share": round(hvac_share, 4),
        "peak_to_avg_ratio": round(peak_to_avg, 4),
        "off_peak_ratio": round(off_peak_ratio, 4),
        "load_factor": round(load_factor, 4),
        "power_std": round(power_std, 4),
        "consumption_kwh": round(consumption_kwh, 4),
        "production_kwh": round(production_kwh, 4),
        "avg_power_kw": round(avg_power, 4),
        "hour_of_day_mean": round(hour_of_day, 2),
        "is_weekend_frac": round(is_weekend_frac, 4),
        # Profile encoding
        "profile_residential": 1 if profile == "residential" else 0,
        "profile_commercial": 1 if profile == "commercial" else 0,
        "profile_industrial": 1 if profile == "industrial" else 0,
    }


def label_features(features: dict, profile: str) -> dict:
    """Add label and score to a feature dict."""
    eui = features.get("eui_annual", 999)
    bm = get_benchmark(profile)

    # Composite score: weight EUI (60%) + renewable (25%) + off-peak (15%)
    eui_score_raw = max(0, 1 - eui / (bm.moderate * 2))
    renewable_score = features.get("renewable_fraction", 0)
    off_peak_score = features.get("off_peak_ratio", 0)

    composite = (eui_score_raw * 0.60 + renewable_score * 0.25 + off_peak_score * 0.15) * 100
    efficiency_score = round(min(100.0, max(0.0, composite)), 1)

    label = eui_to_label(eui, profile)

    return {**features, "label": label, "efficiency_score": efficiency_score, "profile": profile}


def build_training_dataset(
    readings_df: pd.DataFrame,
    profile: str = "residential",
    floor_area_m2: float | None = None,
    window_hours: int = 24,
) -> pd.DataFrame:
    """
    Chunk readings into rolling 24h windows and build a labeled feature dataset.
    Each row = one 24h window = one training sample.

    readings_df must have: recorded_at, power_kw, energy_kwh
    """
    if readings_df.empty:
        return pd.DataFrame()

    readings_df = readings_df.copy()
    readings_df["recorded_at"] = pd.to_datetime(readings_df["recorded_at"], utc=True)
    readings_df = readings_df.sort_values("recorded_at")

    start = readings_df["recorded_at"].min()
    end = readings_df["recorded_at"].max()

    rows = []
    window = pd.Timedelta(hours=window_hours)
    step = pd.Timedelta(hours=window_hours // 2)  # 50% overlap
    current = start

    while current + window <= end:
        mask = (readings_df["recorded_at"] >= current) & (readings_df["recorded_at"] < current + window)
        chunk = readings_df[mask]

        if len(chunk) >= 10:
            features = compute_features(chunk, profile, floor_area_m2)
            if features:
                labeled = label_features(features, profile)
                labeled["window_start"] = current.isoformat()
                rows.append(labeled)

        current += step

    return pd.DataFrame(rows)
