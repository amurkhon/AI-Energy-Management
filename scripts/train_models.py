"""
Offline model training script — trains Isolation Forest + GBM forecasters
for all devices that have sufficient historical data.

Usage: python scripts/train_models.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.device import Device
from app.ai.feature_engineering import build_features
from app.ai.anomaly.detector import train_isolation_forest
from app.ai.forecasting.load_forecaster import train_forecaster


async def train_all():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Device).where(Device.is_active == True))
        devices = result.scalars().all()

        for device in devices:
            print(f"\nTraining models for: {device.name} ({device.device_type.value})")
            df = await build_features(str(device.id), db, hours=720)  # 30 days

            if df.empty or len(df) < 100:
                print(f"  ⚠ Insufficient data ({len(df)} rows), skipping.")
                continue

            # Isolation Forest
            clf = train_isolation_forest(df, str(device.id))
            if clf:
                print(f"  ✓ Isolation Forest trained on {len(df)} samples")
            else:
                print(f"  ⚠ Isolation Forest skipped (need ≥50 samples)")

            # GBM forecasters
            for horizon in ["1h", "6h", "24h", "7d"]:
                model = train_forecaster(df, str(device.id), horizon)
                if model:
                    print(f"  ✓ GBM forecaster [{horizon}] trained")
                else:
                    print(f"  ⚠ GBM [{horizon}] skipped (insufficient lag data)")

    print("\n✓ Training complete! Models saved to ./models/")


if __name__ == "__main__":
    asyncio.run(train_all())
