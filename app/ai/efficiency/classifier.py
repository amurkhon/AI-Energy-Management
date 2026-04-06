"""
Efficiency classifier: predicts label (efficient/good/moderate/inefficient)
and efficiency score (0–100) from a feature vector.

Two models per profile:
  1. RandomForestClassifier  → label prediction
  2. GradientBoostingRegressor → score prediction (0–100)
"""

import os
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, mean_absolute_error

MODEL_DIR = "models"

FEATURE_COLS = [
    "eui_annual",
    "renewable_fraction",
    "hvac_share",
    "peak_to_avg_ratio",
    "off_peak_ratio",
    "load_factor",
    "power_std",
    "avg_power_kw",
    "is_weekend_frac",
    "profile_residential",
    "profile_commercial",
    "profile_industrial",
]

LABEL_ORDER = ["efficient", "good", "moderate", "inefficient"]


# ── Model persistence ──────────────────────────────────────────────────────────

def _clf_path(profile: str) -> str:
    os.makedirs(MODEL_DIR, exist_ok=True)
    return os.path.join(MODEL_DIR, f"efficiency_clf_{profile}.pkl")


def _reg_path(profile: str) -> str:
    os.makedirs(MODEL_DIR, exist_ok=True)
    return os.path.join(MODEL_DIR, f"efficiency_reg_{profile}.pkl")


def _enc_path(profile: str) -> str:
    os.makedirs(MODEL_DIR, exist_ok=True)
    return os.path.join(MODEL_DIR, f"efficiency_enc_{profile}.pkl")


# ── Training ───────────────────────────────────────────────────────────────────

def train(df: pd.DataFrame, profile: str) -> dict:
    """
    Train classifier + regressor on labeled feature DataFrame.
    df must have columns from FEATURE_COLS + 'label' + 'efficiency_score'.
    Returns dict with training metrics.
    """
    avail = [c for c in FEATURE_COLS if c in df.columns]
    X = df[avail].fillna(0)
    y_label = df["label"]
    y_score = df["efficiency_score"]

    if len(X) < 30:
        raise ValueError(f"Need at least 30 samples, got {len(X)}")

    X_train, X_test, yl_train, yl_test, ys_train, ys_test = train_test_split(
        X, y_label, y_score, test_size=0.2, random_state=42, stratify=y_label
    )

    # ── Label encoder ──────────────────────────────────────────────────────────
    enc = LabelEncoder()
    enc.fit(LABEL_ORDER)
    yl_train_enc = enc.transform(yl_train)
    yl_test_enc = enc.transform(yl_test)

    # ── Classifier (label) ────────────────────────────────────────────────────
    clf = RandomForestClassifier(
        n_estimators=200,
        max_depth=12,
        min_samples_leaf=3,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    clf.fit(X_train, yl_train_enc)
    clf_preds = clf.predict(X_test)
    clf_report = classification_report(yl_test_enc, clf_preds, target_names=enc.classes_, output_dict=True)

    # ── Regressor (score 0–100) ───────────────────────────────────────────────
    reg = GradientBoostingRegressor(
        n_estimators=200,
        learning_rate=0.05,
        max_depth=5,
        subsample=0.8,
        random_state=42,
    )
    reg.fit(X_train, ys_train)
    reg_preds = reg.predict(X_test)
    reg_mae = mean_absolute_error(ys_test, reg_preds)

    # Feature importance
    importance = dict(zip(avail, clf.feature_importances_.tolist()))
    top_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:5]

    # Persist
    joblib.dump(clf, _clf_path(profile))
    joblib.dump(reg, _reg_path(profile))
    joblib.dump(enc, _enc_path(profile))

    return {
        "profile": profile,
        "n_samples": len(X),
        "classifier_accuracy": round(clf_report["accuracy"], 4),
        "regressor_mae": round(reg_mae, 2),
        "top_features": top_features,
        "label_distribution": y_label.value_counts().to_dict(),
    }


# ── Inference ──────────────────────────────────────────────────────────────────

def load_classifier(profile: str):
    p = _clf_path(profile)
    return joblib.load(p) if os.path.exists(p) else None


def load_regressor(profile: str):
    p = _reg_path(profile)
    return joblib.load(p) if os.path.exists(p) else None


def load_encoder(profile: str):
    p = _enc_path(profile)
    return joblib.load(p) if os.path.exists(p) else None


def predict(features: dict, profile: str) -> dict:
    """
    Predict efficiency label + score from a feature dict.
    Falls back to rule-based benchmarks if no model is trained yet.
    """
    clf = load_classifier(profile)
    reg = load_regressor(profile)
    enc = load_encoder(profile)

    avail = [c for c in FEATURE_COLS if c in features]
    X = pd.DataFrame([{c: features.get(c, 0) for c in FEATURE_COLS}])

    if clf and reg and enc:
        label_enc = clf.predict(X)[0]
        label = enc.inverse_transform([label_enc])[0]
        proba = clf.predict_proba(X)[0]
        confidence = float(proba.max())
        score = float(np.clip(reg.predict(X)[0], 0, 100))
    else:
        # Fallback: rule-based from benchmarks
        from app.ai.efficiency.benchmarks import eui_to_label, eui_to_score
        eui = features.get("eui_annual", 200)
        label = eui_to_label(eui, profile)
        score = eui_to_score(eui, profile)
        confidence = 0.60  # lower confidence — no ML model yet

    return {
        "label": label,
        "efficiency_score": round(score, 1),
        "confidence": round(confidence, 3),
        "model_used": "ml" if clf else "rule_based",
        "profile": profile,
    }


def predict_from_df(df: pd.DataFrame, profile: str, floor_area_m2: float | None = None) -> dict:
    """Convenience: compute features from raw readings df, then predict."""
    from app.ai.efficiency.labeler import compute_features
    features = compute_features(df, profile, floor_area_m2)
    if not features:
        return {"label": "unknown", "efficiency_score": 0.0, "confidence": 0.0, "model_used": "none"}
    return predict(features, profile)
