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


HOURLY_LOAD_KW = [
    0.8, 0.7, 0.6, 0.6, 0.7, 1.0, 2.0, 3.2, 2.8, 1.8, 1.5, 1.6,
    1.8, 1.7, 1.6, 1.8, 2.2, 3.5, 4.0, 3.8, 3.2, 2.5, 1.8, 1.2,
]


def _analytical_forecast(features: dict, horizon: str) -> dict:
    """
    Fallback when no GBM model is trained.
    Estimates energy from time-of-day load profile + temperature effect.
    """
    hour = int(features.get("hour_of_day", 12))
    is_weekend = bool(features.get("is_weekend", 0))
    temp = float(features.get("temperature_c", 20.0))
    lag_1h = float(features.get("lag_1h", HOURLY_LOAD_KW[hour]))

    # Temperature effect: HVAC draws more when very cold or very hot
    temp_factor = 1.0 + max(0, (temp - 26) * 0.04) + max(0, (10 - temp) * 0.04)
    weekend_factor = 1.15 if is_weekend else 1.0

    hours_ahead = {"1h": 1, "6h": 6, "24h": 24, "7d": 168}.get(horizon, 1)
    total_kwh = 0.0
    for h in range(hours_ahead):
        future_hour = (hour + h) % 24
        base = HOURLY_LOAD_KW[future_hour] * temp_factor * weekend_factor
        # Blend with lag_1h for short horizons
        weight = max(0, 1 - h / 6)
        blended = base * (1 - weight) + lag_1h * weight
        total_kwh += blended

    std_est = total_kwh * 0.18
    return {
        "predicted_kwh": round(total_kwh, 3),
        "lower_bound_kwh": round(max(0, total_kwh - 1.645 * std_est), 3),
        "upper_bound_kwh": round(total_kwh + 1.645 * std_est, 3),
        "horizon": horizon,
        "model": "analytical",
    }


def forecast_from_features(features: dict, device_id: str | None, horizon: str) -> dict:
    """
    Predict energy for a given horizon from explicit feature values.
    Uses the trained GBM model when available; falls back to analytical.
    features keys: hour_of_day, day_of_week, is_weekend, temperature_c,
                   lag_1h, lag_24h, lag_168h
    """
    model = load_forecaster(device_id or "default", horizon) if device_id else None

    if model is not None:
        X = pd.DataFrame([{c: features.get(c, 0) for c in FEATURE_COLS}])
        predicted = float(model.predict(X)[0])
        hours = {"1h": 1, "6h": 6, "24h": 24, "7d": 168}.get(horizon, 1)
        predicted_kwh = predicted * hours
        std_est = abs(predicted_kwh) * 0.15
        return {
            "predicted_kwh": round(predicted_kwh, 3),
            "lower_bound_kwh": round(max(0, predicted_kwh - 1.645 * std_est), 3),
            "upper_bound_kwh": round(predicted_kwh + 1.645 * std_est, 3),
            "horizon": horizon,
            "model": "gbm",
        }

    return _analytical_forecast(features, horizon)


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
