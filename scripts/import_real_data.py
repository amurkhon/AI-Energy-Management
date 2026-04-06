"""
Import real-world energy datasets and train the efficiency classifier.

Supported formats:
  --format ashrae      ASHRAE Great Energy Predictor III (Kaggle)
  --format pecanstreet PecanStreet Dataport CSV export
  --format generic     Generic CSV (see --help for column mapping)

Usage examples:
  python scripts/import_real_data.py --format ashrae --path data/ashrae/train.csv --meta data/ashrae/building_metadata.csv
  python scripts/import_real_data.py --format pecanstreet --path data/pecanstreet/15minute_data_austin.csv
  python scripts/import_real_data.py --format generic --path data/my_data.csv --profile residential --area 120
  python scripts/import_real_data.py --format simulation --days 365  # use your own simulation engine

Download links:
  ASHRAE:      https://www.kaggle.com/competitions/ashrae-energy-prediction/data
  PecanStreet: https://dataport.pecanstreet.org  (free academic signup)
  UCI EE:      https://archive.ics.uci.edu/dataset/242/energy+efficiency
"""

import argparse
import asyncio
import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ai.efficiency.labeler import build_training_dataset, label_features, compute_features
from app.ai.efficiency.classifier import train, FEATURE_COLS


# ── Format: ASHRAE Great Energy Predictor III ─────────────────────────────────

def load_ashrae(train_csv: str, meta_csv: str | None = None) -> pd.DataFrame:
    """
    ASHRAE train.csv columns:
      building_id, meter, timestamp, meter_reading (kWh)
    building_metadata.csv columns:
      building_id, primary_use, square_feet, year_built, floor_count
    """
    print(f"Loading ASHRAE data from {train_csv}...")
    df = pd.read_csv(train_csv, parse_dates=["timestamp"])
    df = df.rename(columns={"timestamp": "recorded_at", "meter_reading": "energy_kwh"})
    df["power_kw"] = df["energy_kwh"]  # ASHRAE is already in kWh per hour → power_kw ≈ energy_kwh

    # Meter 0 = electricity, 1 = chilled water, 2 = steam, 3 = hot water
    df = df[df["meter"] == 0].copy()

    profile_map = {
        "Education": "commercial",
        "Office": "commercial",
        "Entertainment/public assembly": "commercial",
        "Public services": "commercial",
        "Warehouse/storage": "industrial",
        "Manufacturing/industrial": "industrial",
        "Lodging/residential": "residential",
        "Retail": "commercial",
        "Technology/science": "commercial",
        "Healthcare": "commercial",
        "Parking": "commercial",
        "Other": "commercial",
        "Food sales and service": "commercial",
        "Religious worship": "commercial",
        "Utility": "industrial",
    }

    if meta_csv and os.path.exists(meta_csv):
        meta = pd.read_csv(meta_csv)
        meta["profile"] = meta["primary_use"].map(profile_map).fillna("commercial")
        meta["floor_area_m2"] = meta["square_feet"] * 0.0929  # sq ft → m²
        df = df.merge(meta[["building_id", "profile", "floor_area_m2"]], on="building_id", how="left")
    else:
        df["profile"] = "commercial"
        df["floor_area_m2"] = 2000.0

    df["profile"] = df["profile"].fillna("commercial")
    df["floor_area_m2"] = df["floor_area_m2"].fillna(2000.0)
    df["energy_kwh"] = df["energy_kwh"].clip(lower=0)
    df["power_kw"] = -df["energy_kwh"]  # consumption = negative convention

    print(f"  → {len(df):,} readings, {df['building_id'].nunique()} buildings")
    return df


def build_ashrae_dataset(df: pd.DataFrame, max_buildings: int = 200) -> pd.DataFrame:
    """Build feature dataset from ASHRAE data, one sample per building per day."""
    all_rows = []
    buildings = df["building_id"].unique()[:max_buildings]

    for i, bid in enumerate(buildings):
        bdf = df[df["building_id"] == bid].copy()
        profile = bdf["profile"].iloc[0]
        area = bdf["floor_area_m2"].iloc[0]

        dataset = build_training_dataset(bdf, profile=profile, floor_area_m2=area, window_hours=24)
        if not dataset.empty:
            dataset["building_id"] = bid
            all_rows.append(dataset)

        if (i + 1) % 50 == 0:
            print(f"  Processed {i + 1}/{len(buildings)} buildings...")

    if not all_rows:
        return pd.DataFrame()
    return pd.concat(all_rows, ignore_index=True)


# ── Format: PecanStreet Dataport ──────────────────────────────────────────────

def load_pecanstreet(csv_path: str) -> pd.DataFrame:
    """
    PecanStreet 15-minute data columns (varies by export):
      localminute, dataid, grid, solar, use
    grid = net grid draw (kW), solar = solar production (kW), use = total consumption (kW)
    """
    print(f"Loading PecanStreet data from {csv_path}...")
    df = pd.read_csv(csv_path, parse_dates=["localminute"])
    df = df.rename(columns={"localminute": "recorded_at", "dataid": "building_id"})

    # Standardize columns
    if "use" in df.columns:
        df["power_kw"] = -df["use"]  # consumption = negative
    elif "grid" in df.columns:
        df["power_kw"] = df["grid"]

    if "solar" in df.columns:
        # Add solar as separate production
        solar_df = df[["recorded_at", "building_id", "solar"]].copy()
        solar_df["power_kw"] = solar_df["solar"]
        solar_df["device_type"] = "solar_panel"
        df["device_type"] = "smart_meter"
        df = pd.concat([df, solar_df], ignore_index=True)

    df["energy_kwh"] = df["power_kw"] * (15 / 60)  # 15-min interval → kWh
    df["profile"] = "residential"
    df["floor_area_m2"] = 180.0  # typical Texas home

    print(f"  → {len(df):,} readings, {df['building_id'].nunique()} homes")
    return df


# ── Format: Generic CSV ───────────────────────────────────────────────────────

def load_generic(csv_path: str, profile: str = "residential", area: float = 120.0) -> pd.DataFrame:
    """
    Generic CSV. Required columns: timestamp, power_kw OR energy_kwh
    Optional: device_type, building_id
    """
    print(f"Loading generic CSV from {csv_path}...")
    df = pd.read_csv(csv_path)

    # Detect timestamp column
    ts_col = next((c for c in df.columns if "time" in c.lower() or "date" in c.lower()), None)
    if ts_col:
        df["recorded_at"] = pd.to_datetime(df[ts_col])
    else:
        raise ValueError("No timestamp column found. Expected a column with 'time' or 'date' in the name.")

    if "power_kw" not in df.columns and "energy_kwh" in df.columns:
        df["power_kw"] = df["energy_kwh"]  # treat as hourly
    elif "power_kw" not in df.columns:
        raise ValueError("Need either 'power_kw' or 'energy_kwh' column.")

    if "energy_kwh" not in df.columns:
        df["energy_kwh"] = df["power_kw"] / 12  # assume 5-min intervals

    df["building_id"] = df.get("building_id", 0)
    df["profile"] = profile
    df["floor_area_m2"] = area

    print(f"  → {len(df):,} readings")
    return df


# ── Format: Simulation (generate fresh from your engine) ─────────────────────

async def load_from_simulation(days: int = 365, profile: str = "residential") -> pd.DataFrame:
    """Generate training data from the simulation engine at 60x speed."""
    from app.simulation.weather import WeatherSimulator
    from app.simulation.occupancy import OccupancySimulator
    from app.simulation.devices.solar_panel import SolarPanel
    from app.simulation.devices.hvac import HVAC
    from app.simulation.devices.lighting import Lighting
    from app.simulation.devices.ev_charger import EVCharger
    from app.simulation.devices.appliance import GenericAppliance
    from app.simulation.devices.battery import Battery

    print(f"Generating {days} days of simulation data...")

    weather = WeatherSimulator(latitude=40.7)
    occupancy = OccupancySimulator(profile)
    devices = [
        ("solar_panel", SolarPanel(panel_area_m2=20, efficiency=0.18)),
        ("hvac", HVAC(rated_power_kw=3.5)),
        ("lighting", Lighting(rated_power_kw=0.5)),
        ("ev_charger", EVCharger(charge_power_kw=7.4)),
        ("appliance", GenericAppliance("washer")),
        ("battery", Battery(capacity_kwh=13.5, charge_rate_kw=5.0)),
    ]

    tick_min = 15  # 15-min ticks for 1 year
    tick_h = tick_min / 60
    start = datetime.now(timezone.utc) - timedelta(days=days)
    rows = []

    battery_inst = next(d for dtype, d in devices if dtype == "battery")

    for tick in range(int(days * 24 * 60 / tick_min)):
        sim_time = start + timedelta(minutes=tick * tick_min)
        w = weather.get_conditions(sim_time)
        occ = occupancy.occupancy_fraction(sim_time)

        net = 0.0
        for dtype, dev in devices:
            if dtype == "battery":
                continue
            rd = dev.generate_reading(sim_time=sim_time, weather=w, occupancy=occ, tick_hours=tick_h)
            power = rd.get("power_kw", 0)
            net += power
            rows.append({
                "recorded_at": sim_time,
                "power_kw": power,
                "energy_kwh": power * tick_h,
                "device_type": dtype,
                "building_id": 0,
                "profile": profile,
                "floor_area_m2": 120.0,
            })

        rd = battery_inst.generate_reading(sim_time=sim_time, weather=w, net_grid_kw=net, tick_hours=tick_h)
        rows.append({
            "recorded_at": sim_time,
            "power_kw": rd.get("power_kw", 0),
            "energy_kwh": rd.get("power_kw", 0) * tick_h,
            "device_type": "battery",
            "building_id": 0,
            "profile": profile,
            "floor_area_m2": 120.0,
        })

        if tick % 5000 == 0:
            pct = tick / (days * 24 * 60 / tick_min) * 100
            print(f"  {pct:.0f}% complete...")

    df = pd.DataFrame(rows)
    print(f"  → {len(df):,} readings generated")
    return df


# ── Train all profiles ─────────────────────────────────────────────────────────

def train_from_dataset(df: pd.DataFrame, output_dir: str = "models") -> dict:
    """Build feature dataset and train classifier per profile."""
    results = {}
    profiles = df["profile"].unique() if "profile" in df.columns else ["residential"]

    for profile in profiles:
        print(f"\nBuilding feature dataset for profile: {profile}")
        pdf = df[df["profile"] == profile].copy() if "profile" in df.columns else df.copy()

        # Build labeled feature dataset
        if "building_id" in pdf.columns:
            all_rows = []
            for bid in pdf["building_id"].unique():
                bdf = pdf[pdf["building_id"] == bid]
                area = bdf["floor_area_m2"].iloc[0] if "floor_area_m2" in bdf.columns else None
                ds = build_training_dataset(bdf, profile=profile, floor_area_m2=area, window_hours=24)
                if not ds.empty:
                    all_rows.append(ds)
            if not all_rows:
                print(f"  ⚠ No usable windows for {profile}, skipping.")
                continue
            feature_df = pd.concat(all_rows, ignore_index=True)
        else:
            feature_df = build_training_dataset(pdf, profile=profile, window_hours=24)

        if feature_df.empty or len(feature_df) < 30:
            print(f"  ⚠ Only {len(feature_df)} samples for {profile} — need ≥30. Skipping.")
            continue

        print(f"  → {len(feature_df)} training samples")
        print(f"  Label distribution: {feature_df['label'].value_counts().to_dict()}")

        try:
            metrics = train(feature_df, profile)
            print(f"  ✓ Classifier accuracy: {metrics['classifier_accuracy']:.1%}")
            print(f"  ✓ Score regressor MAE: {metrics['regressor_mae']:.1f} points")
            print(f"  ✓ Top features: {[f[0] for f in metrics['top_features']]}")
            results[profile] = metrics
        except Exception as e:
            print(f"  ✗ Training failed: {e}")

    return results


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Import energy data and train efficiency classifier")
    parser.add_argument("--format", choices=["ashrae", "pecanstreet", "generic", "simulation"],
                        default="simulation", help="Data format")
    parser.add_argument("--path", type=str, help="Path to main CSV file")
    parser.add_argument("--meta", type=str, help="Path to metadata CSV (ASHRAE only)")
    parser.add_argument("--profile", default="residential",
                        choices=["residential", "commercial", "industrial"],
                        help="Building profile (generic/simulation)")
    parser.add_argument("--area", type=float, default=120.0,
                        help="Floor area m² (generic format)")
    parser.add_argument("--days", type=int, default=365,
                        help="Days to simulate (simulation format)")
    parser.add_argument("--max-buildings", type=int, default=200,
                        help="Max buildings to process (ASHRAE)")
    args = parser.parse_args()

    print("=" * 60)
    print("  SEMS Efficiency Classifier — Data Import & Training")
    print("=" * 60)

    if args.format == "ashrae":
        if not args.path:
            print("Error: --path required for ASHRAE format")
            print("Download from: https://www.kaggle.com/competitions/ashrae-energy-prediction/data")
            sys.exit(1)
        df = load_ashrae(args.path, args.meta)
        df = build_ashrae_dataset(df, max_buildings=args.max_buildings)
        # Already has features + labels from build_ashrae_dataset
        results = {}
        for profile in df["profile"].unique() if "profile" in df.columns else ["commercial"]:
            pdf = df[df["profile"] == profile] if "profile" in df.columns else df
            if len(pdf) >= 30:
                try:
                    metrics = train(pdf, profile)
                    results[profile] = metrics
                    print(f"✓ {profile}: accuracy={metrics['classifier_accuracy']:.1%}, MAE={metrics['regressor_mae']:.1f}")
                except Exception as e:
                    print(f"✗ {profile}: {e}")

    elif args.format == "pecanstreet":
        if not args.path:
            print("Error: --path required for PecanStreet format")
            print("Download from: https://dataport.pecanstreet.org")
            sys.exit(1)
        df = load_pecanstreet(args.path)
        results = train_from_dataset(df)

    elif args.format == "generic":
        if not args.path:
            print("Error: --path required for generic format")
            sys.exit(1)
        df = load_generic(args.path, profile=args.profile, area=args.area)
        results = train_from_dataset(df)

    elif args.format == "simulation":
        df = asyncio.run(load_from_simulation(days=args.days, profile=args.profile))
        results = train_from_dataset(df)

    print("\n" + "=" * 60)
    print("  Training Complete")
    print("=" * 60)
    for profile, metrics in results.items():
        print(f"\n  [{profile.upper()}]")
        print(f"    Samples:  {metrics['n_samples']}")
        print(f"    Accuracy: {metrics['classifier_accuracy']:.1%}")
        print(f"    Score MAE:{metrics['regressor_mae']:.1f} pts")
        print(f"    Labels:   {metrics['label_distribution']}")

    print(f"\n  Models saved to ./models/")
    print("  Run 'uvicorn app.main:app' and check /api/v1/dashboard for live scores.\n")


if __name__ == "__main__":
    main()
