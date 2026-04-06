from datetime import datetime, timezone, timedelta

PRIORITY_WEIGHTS = {"critical": 4, "high": 3, "medium": 2, "low": 1}
MAX_SUGGESTIONS = 5
DEDUP_WINDOW_HOURS = 2


def score_suggestion(s: dict) -> float:
    base = PRIORITY_WEIGHTS.get(s.get("priority", "low"), 1)
    confidence = s.get("confidence_score") or 0.5
    saving = min(s.get("estimated_saving_kwh") or 0, 50) / 50  # normalize to 0-1
    return base * confidence * (1 + saving)


def rank_and_deduplicate(suggestions: list[dict], existing: list[dict]) -> list[dict]:
    """
    Rank suggestions by score and remove duplicates vs. existing active suggestions.
    existing: list of {category, device_id, generated_at} from DB
    """
    now = datetime.now(timezone.utc)
    dedup_cutoff = now - timedelta(hours=DEDUP_WINDOW_HOURS)

    # Build dedup set from existing recent suggestions
    recent_keys = set()
    for e in existing:
        if e.get("generated_at") and e["generated_at"] > dedup_cutoff:
            key = (e.get("category"), str(e.get("device_id")))
            recent_keys.add(key)

    filtered = []
    for s in suggestions:
        key = (s.get("category"), str(s.get("device_id")))
        if key not in recent_keys:
            filtered.append(s)

    # Sort by score descending
    filtered.sort(key=score_suggestion, reverse=True)

    return filtered[:MAX_SUGGESTIONS]
