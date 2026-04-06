"""
Offline model training script.

Trains:
  1. Isolation Forest  — per-device anomaly detection
  2. GBM Forecasters   — per-device load forecasting (1h/6h/24h/7d)
  3. Efficiency Classifier — per-profile label + score (0-100)

Usage:
  python scripts/train_models.py              # trains all
  python scripts/train_models.py --skip-efficiency  # skip efficiency (no DB needed)
"""
import argparse
import asyncio
import sys
import os
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.device import Device, SimProfile
from app.models.reading import EnergyReading
from app.ai.feature_engineering import build_features
from app.ai.anomaly.detector import train_isolation_forest
from app.ai.forecasting.load_forecaster import train_forecaster
from app.ai.efficiency.labeler import build_training_dataset
from app.ai.efficiency.classifier import train as train_efficiency


async def train_anomaly_and_forecast(db):
    result = await db.execute(select(Device).where(Device.is_active == True))
    devices = result.scalars().all()

    for device in devices:
        print(f"\n[{device.device_type.value}] {device.name}")
        df = await build_features(str(device.id), db, hours=720)  # 30 days

        if df.empty or len(df) < 100:
            print(f"  ⚠ Insufficient data ({len(df)} rows), skipping.")
            continue

        # Isolation Forest
        clf = train_isolation_forest(df, str(device.id))
        print(f"  {'✓' if clf else '⚠'} Isolation Forest {'trained' if clf else 'skipped (need ≥50 samples)'}")

        # GBM forecasters
        for horizon in ["1h", "6h", "24h", "7d"]:
            model = train_forecaster(df, str(device.id), horizon)
            print(f"  {'✓' if model else '⚠'} GBM [{horizon}] {'trained' if model else 'skipped'}")


async def train_efficiency_classifier(db):
    """
    Pulls all historical readings grouped by sim_profile and trains
    one efficiency classifier per profile (residential / commercial / industrial).
    """
    print("\n── Efficiency Classifier ─────────────────────────────────────")

    # Fetch all devices with their profiles
    result = await db.execute(select(Device).where(Device.is_active == True))
    devices = result.scalars().all()

    if not devices:
        print("  ⚠ No devices found. Run seed_db.py first.")
        return

    # Group device IDs by profile
    profile_devices: dict[str, list] = defaultdict(list)
    for d in devices:
        profile_devices[d.sim_profile.value].append(d)

    for profile, profile_devs in profile_devices.items():
        print(f"\n  Profile: {profile} ({len(profile_devs)} devices)")
        device_ids = [d.id for d in profile_devs]

        # Fetch readings for all devices in this profile (last 90 days = 8760h)
        from datetime import datetime, timezone, timedelta
        since = datetime.now(timezone.utc) - timedelta(days=90)

        readings_result = await db.execute(
            select(
                EnergyReading.recorded_at,
                EnergyReading.power_kw,
                EnergyReading.energy_kwh,
                EnergyReading.device_id,
            )
            .where(
                EnergyReading.device_id.in_(device_ids),
                EnergyReading.recorded_at >= since,
            )
            .order_by(EnergyReading.recorded_at.asc())
        )
        rows = readings_result.all()

        if not rows:
            print(f"  ⚠ No readings found for {profile}, skipping.")
            continue

        df = pd.DataFrame(rows, columns=["recorded_at", "power_kw", "energy_kwh", "device_id"])
        print(f"  → {len(df):,} readings loaded")

        # Build labeled feature dataset (24h windows, 50% overlap)
        # Use each device_id as a pseudo "building_id"
        df["building_id"] = df["device_id"].astype(str)
        df["profile"] = profile
        df["floor_area_m2"] = 120.0 if profile == "residential" else (2000.0 if profile == "commercial" else 10000.0)

        all_windows = []
        for did in df["device_id"].unique():
            ddf = df[df["device_id"] == did]
            area = ddf["floor_area_m2"].iloc[0]
            windows = build_training_dataset(ddf, profile=profile, floor_area_m2=area, window_hours=24)
            if not windows.empty:
                all_windows.append(windows)

        if not all_windows:
            print(f"  ⚠ No valid windows for {profile}.")
            continue

        feature_df = pd.concat(all_windows, ignore_index=True)
        print(f"  → {len(feature_df)} training windows")
        print(f"  → Labels: {feature_df['label'].value_counts().to_dict()}")

        if len(feature_df) < 30:
            print(f"  ⚠ Need ≥30 samples, skipping.")
            continue

        try:
            metrics = train_efficiency(feature_df, profile)
            print(f"  ✓ Accuracy:  {metrics['classifier_accuracy']:.1%}")
            print(f"  ✓ Score MAE: {metrics['regressor_mae']:.1f} pts")
            print(f"  ✓ Top features: {[f[0] for f in metrics['top_features']]}")
        except Exception as e:
            print(f"  ✗ Training failed: {e}")


async def main(skip_efficiency: bool = False):
    print("=" * 60)
    print("  SEMS Model Training")
    print("=" * 60)

    async with AsyncSessionLocal() as db:
        print("\n── Anomaly Detection + Forecasting ───────────────────────────")
        await train_anomaly_and_forecast(db)

        if not skip_efficiency:
            await train_efficiency_classifier(db)

    print("\n" + "=" * 60)
    print("  ✓ All models saved to ./models/")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-efficiency", action="store_true",
                        help="Skip efficiency classifier (no DB needed)")
    args = parser.parse_args()
    asyncio.run(main(skip_efficiency=args.skip_efficiency))
