import numpy as np
import pandas as pd
import joblib
import os
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split

MODEL_DIR = "models"
HORIZONS = {"1h": 60, "6h": 360, "24h": 1440, "7d": 10080}  # in minutes


def _model_path(device_id: str, horizon: str) -> str:
    os.makedirs(MODEL_DIR, exist_ok=True)
    return os.path.join(MODEL_DIR, f"gbm_{device_id}_{horizon}.pkl")


FEATURE_COLS = ["lag_1h", "lag_24h", "lag_168h", "hour_of_day", "day_of_week", "is_weekend", "temperature_c"]


def train_forecaster(df: pd.DataFrame, device_id: str, horizon: str = "1h") -> GradientBoostingRegressor | None:
    """Train a GBM forecaster for the given horizon."""
    lag_steps = HORIZONS.get(horizon, 60)

    if df.empty or len(df) < lag_steps + 50:
        return None

    df = df.copy().sort_values("recorded_at")
    df["target"] = df["power_kw"].shift(-lag_steps)
    df = df.dropna(subset=["target"])

    avail_features = [f for f in FEATURE_COLS if f in df.columns]
    X = df[avail_features].fillna(0)
    y = df["target"]

    if len(X) < 50:
        return None

    model = GradientBoostingRegressor(n_estimators=100, learning_rate=0.1, max_depth=4, random_state=42)
    model.fit(X, y)
    joblib.dump(model, _model_path(device_id, horizon))
    return model


def load_forecaster(device_id: str, horizon: str) -> GradientBoostingRegressor | None:
    path = _model_path(device_id, horizon)
    if os.path.exists(path):
        return joblib.load(path)
    return None


def forecast(df: pd.DataFrame, device_id: str, horizon: str = "1h") -> dict | None:
    """Generate a single forecast for the next horizon."""
    model = load_forecaster(device_id, horizon)
    if model is None or df.empty:
        return None

    latest = df.tail(1)
    avail_features = [f for f in FEATURE_COLS if f in latest.columns]
    X = latest[avail_features].fillna(0)

    predicted = float(model.predict(X)[0])
    # Rough confidence interval via residual std from training
    std_est = abs(predicted) * 0.15
    return {
        "predicted_kwh": round(predicted * (HORIZONS[horizon] / 60), 4),
        "lower_bound_kwh": round((predicted - 1.645 * std_est) * (HORIZONS[horizon] / 60), 4),
        "upper_bound_kwh": round((predicted + 1.645 * std_est) * (HORIZONS[horizon] / 60), 4),
        "horizon": horizon,
        "model_version": f"gbm_v1_{device_id}_{horizon}",
    }
