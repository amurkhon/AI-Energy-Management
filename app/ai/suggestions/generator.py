import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.device import Device
from app.models.suggestion import AISuggestion, SuggestionCategory, SuggestionPriority, SuggestionSource
from app.models.prediction import AnomalyRecord, AnomalyType
from app.ai.feature_engineering import build_features
from app.ai.anomaly.rules import rule_based_anomalies
from app.ai.anomaly.detector import detect_ml_anomalies
from app.ai.optimization.scheduler import load_shift_suggestion
from app.ai.suggestions.rule_engine import rule_based_suggestions
from app.ai.suggestions.ranker import rank_and_deduplicate


async def generate_for_device(device: Device, user_id: uuid.UUID, db: AsyncSession) -> list[AISuggestion]:
    """Run full AI pipeline for a single device and persist suggestions."""
    df = await build_features(str(device.id), db, hours=24)
    if df.empty:
        return []

    device_dict = {
        "id": str(device.id),
        "name": device.name,
        "device_type": device.device_type.value,
        "rated_capacity": device.rated_capacity,
        "sim_profile": device.sim_profile.value,
    }

    raw_suggestions = []

    # 1. Rule-based anomalies → suggestions
    anomalies = rule_based_anomalies(df, device_dict)
    for a in anomalies:
        raw_suggestions.append({
            "category": "anomaly",
            "priority": "high",
            "title": f"Anomaly detected: {a['rule']}",
            "description": f"Device {device.name} shows {a['anomaly_type']} pattern. Expected {a.get('expected_value', 'N/A'):.2f}, got {a.get('actual_value', 0):.2f}.",
            "estimated_saving_kwh": None,
            "estimated_saving_cost": None,
            "confidence_score": 0.85,
            "source": "rule_based",
            "device_id": str(device.id),
        })
        # Persist anomaly record
        rec = AnomalyRecord(
            device_id=device.id,
            anomaly_type=AnomalyType(a["anomaly_type"]),
            z_score=a.get("z_score"),
            expected_value=a.get("expected_value"),
            actual_value=a.get("actual_value"),
        )
        db.add(rec)

    # 2. ML anomaly detection
    ml_anomalies = detect_ml_anomalies(df, str(device.id))
    for a in ml_anomalies:
        raw_suggestions.append({
            "category": "anomaly",
            "priority": "medium",
            "title": "ML-detected unusual consumption pattern",
            "description": f"Isolation Forest flagged abnormal reading: {a['actual_value']:.2f} kW (score={a['score']:.3f}).",
            "estimated_saving_kwh": None,
            "estimated_saving_cost": None,
            "confidence_score": min(0.9, abs(a["score"]) * 5),
            "source": "ml_anomaly",
            "device_id": str(device.id),
        })

    # 3. Load-shift optimization
    current_hour = datetime.now(timezone.utc).hour
    shift = load_shift_suggestion(device_dict, current_hour, device.rated_capacity)
    if shift:
        raw_suggestions.append({
            "category": "load_shifting",
            "priority": "medium",
            **shift,
            "source": "ml_optimization",
            "device_id": str(device.id),
        })

    # 4. Rule-based efficiency suggestions
    rule_suggs = rule_based_suggestions(df, device_dict)
    for rs in rule_suggs:
        raw_suggestions.append({**rs, "device_id": str(device.id)})

    # 5. Fetch existing suggestions for dedup
    existing_res = await db.execute(
        select(AISuggestion)
        .where(AISuggestion.user_id == user_id, AISuggestion.is_dismissed == False)
        .order_by(AISuggestion.generated_at.desc())
        .limit(50)
    )
    existing = [
        {"category": s.category.value, "device_id": str(s.device_id), "generated_at": s.generated_at}
        for s in existing_res.scalars()
    ]

    ranked = rank_and_deduplicate(raw_suggestions, existing)

    created = []
    for rs in ranked:
        suggestion = AISuggestion(
            user_id=user_id,
            device_id=uuid.UUID(rs["device_id"]) if rs.get("device_id") else None,
            category=SuggestionCategory(rs["category"]),
            priority=SuggestionPriority(rs.get("priority", "medium")),
            title=rs["title"],
            description=rs["description"],
            action_detail=rs.get("action_detail"),
            estimated_saving_kwh=rs.get("estimated_saving_kwh"),
            estimated_saving_cost=rs.get("estimated_saving_cost"),
            confidence_score=rs.get("confidence_score"),
            source=SuggestionSource(rs.get("source", "rule_based")),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=6),
        )
        db.add(suggestion)
        created.append(suggestion)

    await db.flush()
    return created
