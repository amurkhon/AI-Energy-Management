import pandas as pd
from datetime import datetime, timezone


def rule_based_suggestions(df: pd.DataFrame, device: dict) -> list[dict]:
    """
    Pure rule-based suggestions from energy patterns.
    Returns list of suggestion dicts.
    """
    suggestions = []
    if df.empty:
        return suggestions

    device_type = device.get("device_type", "")
    rated = device.get("rated_capacity") or 5.0

    # 1. High consumption during peak hours
    if not df.empty:
        recent = df.tail(12)  # last 12 readings (~12 min)
        avg_consumption = recent["power_kw"].mean()
        hour = datetime.now(timezone.utc).hour
        if avg_consumption < -rated * 0.8 and 8 <= hour < 22:
            suggestions.append({
                "category": "efficiency",
                "priority": "high",
                "title": "High energy consumption during peak hours",
                "description": f"Average consumption of {abs(avg_consumption):.2f} kW during peak tariff window. Consider deferring non-essential loads.",
                "estimated_saving_kwh": abs(avg_consumption) * 2,
                "estimated_saving_cost": abs(avg_consumption) * 2 * 0.12,
                "confidence_score": 0.80,
                "source": "rule_based",
            })

    # 2. Low renewable utilization
    if device_type in ("solar_panel", "wind_turbine"):
        recent_prod = df.tail(60)["power_kw"].mean() if len(df) >= 60 else 0
        if recent_prod < rated * 0.1 and 10 <= datetime.now(timezone.utc).hour <= 16:
            suggestions.append({
                "category": "renewable",
                "priority": "medium",
                "title": "Low renewable energy production",
                "description": f"Solar/wind output is only {recent_prod:.2f} kW ({recent_prod/rated*100:.0f}% of capacity). Check for shading or maintenance needs.",
                "estimated_saving_kwh": None,
                "estimated_saving_cost": None,
                "confidence_score": 0.65,
                "source": "rule_based",
            })

    return suggestions
