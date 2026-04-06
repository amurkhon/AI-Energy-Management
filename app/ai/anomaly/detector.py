import numpy as np
import pandas as pd
import joblib
import os
from sklearn.ensemble import IsolationForest

MODEL_DIR = "models"
ANOMALY_THRESHOLD = -0.1


def _model_path(device_id: str) -> str:
    os.makedirs(MODEL_DIR, exist_ok=True)
    return os.path.join(MODEL_DIR, f"iforest_{device_id}.pkl")


def train_isolation_forest(df: pd.DataFrame, device_id: str) -> IsolationForest:
    """Train and persist an Isolation Forest model for a device."""
    features = ["power_kw", "rolling_mean_1h", "rolling_std_1h", "hour_of_day", "day_of_week"]
    X = df[features].dropna()
    if len(X) < 50:
        return None
    clf = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
    clf.fit(X)
    joblib.dump(clf, _model_path(device_id))
    return clf


def load_model(device_id: str) -> IsolationForest | None:
    path = _model_path(device_id)
    if os.path.exists(path):
        return joblib.load(path)
    return None


def detect_ml_anomalies(df: pd.DataFrame, device_id: str) -> list[dict]:
    """Run Isolation Forest on the latest window; return anomaly records."""
    clf = load_model(device_id)
    if clf is None:
        return []

    features = ["power_kw", "rolling_mean_1h", "rolling_std_1h", "hour_of_day", "day_of_week"]
    available = [f for f in features if f in df.columns]
    X = df[available].dropna()
    if X.empty:
        return []

    scores = clf.decision_function(X)
    anomaly_mask = scores < ANOMALY_THRESHOLD

    anomalies = []
    for idx in X.index[anomaly_mask]:
        row = df.loc[idx]
        anomalies.append({
            "anomaly_type": "pattern_break",
            "score": float(scores[X.index.get_loc(idx)]),
            "z_score": None,
            "expected_value": float(df["rolling_mean_1h"].iloc[-1]) if "rolling_mean_1h" in df.columns else None,
            "actual_value": float(row["power_kw"]),
            "detected_at": row["recorded_at"].isoformat() if "recorded_at" in df.columns else None,
        })

    return anomalies
