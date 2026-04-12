import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.reading import EnergyReading


async def build_features(device_id: str, db: AsyncSession, hours: int = 24) -> pd.DataFrame:
    """Fetch last N hours of readings for a device and engineer features."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = await db.execute(
        select(EnergyReading)
        .where(EnergyReading.device_id == device_id, EnergyReading.recorded_at >= since)
        .order_by(EnergyReading.recorded_at.asc())
    )
    rows = result.scalars().all()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([{
        "recorded_at": r.recorded_at,
        "power_kw": r.power_kw,
        "energy_kwh": r.energy_kwh,
        "temperature_c": r.temperature_c or 15.0,
    } for r in rows])

    df["recorded_at"] = pd.to_datetime(df["recorded_at"], utc=True)
    df = df.sort_values("recorded_at").set_index("recorded_at")

    # Temporal features
    df["hour_of_day"] = df.index.hour
    df["day_of_week"] = df.index.dayofweek
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)

    # Rolling stats
    df["rolling_mean_1h"] = df["power_kw"].rolling("1h", min_periods=1).mean()
    df["rolling_std_1h"] = df["power_kw"].rolling("1h", min_periods=1).std().fillna(0)
    df["rolling_mean_6h"] = df["power_kw"].rolling("6h", min_periods=1).mean()

    # Rate of change
    df["power_delta"] = df["power_kw"].diff().fillna(0)
    df["consumption_rate_change"] = df["power_delta"].abs()

    return df.reset_index()


def build_forecast_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add lag features for forecasting."""
    if df.empty:
        return df
    df = df.copy()
    df["lag_1h"] = df["power_kw"].shift(60).bfill()
    df["lag_24h"] = df["power_kw"].shift(1440).bfill()
    df["lag_168h"] = df["power_kw"].shift(10080).bfill()
    return df
