from app.ai.optimization.tariff import get_rate, cheapest_window

DEFERRABLE_TYPES = {"ev_charger", "appliance"}
MIN_SAVING_FRACTION = 0.15  # Only suggest if saving >= 15%


def load_shift_suggestion(device: dict, current_hour: int, rated_kw: float | None = None) -> dict | None:
    """
    Suggest shifting a deferrable load to off-peak hours.
    Returns suggestion dict or None if no significant saving.
    """
    device_type = device.get("device_type", "")
    if device_type not in DEFERRABLE_TYPES:
        return None

    rated = rated_kw or device.get("rated_capacity") or 2.0
    current_rate = get_rate(current_hour)
    best_window = cheapest_window(duration_hours=2.0)
    best_rate = best_window["estimated_cost_usd_per_kwh"]

    saving_fraction = (current_rate - best_rate) / current_rate if current_rate > 0 else 0

    if saving_fraction < MIN_SAVING_FRACTION:
        return None

    kwh_per_run = rated * 2.0
    saving_usd = (current_rate - best_rate) * kwh_per_run
    saving_kwh = kwh_per_run * saving_fraction

    start = best_window["start_hour"]
    end = best_window["end_hour"]
    end_str = f"{end:02d}:00" if end != 0 else "00:00"

    return {
        "title": f"Shift {device.get('name', device_type)} to off-peak hours",
        "description": (
            f"Running this device during peak hours costs ${current_rate:.2f}/kWh. "
            f"Shifting to {start:02d}:00–{end_str} reduces cost by {saving_fraction*100:.0f}%. "
            f"Estimated saving: ${saving_usd:.2f} per run."
        ),
        "estimated_saving_kwh": round(saving_kwh, 3),
        "estimated_saving_cost": round(saving_usd, 2),
        "action_detail": {
            "recommended_start_hour": start,
            "recommended_end_hour": end,
            "current_rate": current_rate,
            "off_peak_rate": best_rate,
        },
        "confidence_score": min(0.95, 0.6 + saving_fraction),
    }
