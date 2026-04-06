"""Time-of-use tariff definitions and cost helpers."""

TOU_RATES = {
    "peak":     {"hours": list(range(8, 22)), "rate_usd_kwh": 0.20},
    "off_peak": {"hours": list(range(0, 8)) + list(range(22, 24)), "rate_usd_kwh": 0.08},
}
FLAT_RATE = 0.12  # USD/kWh


def get_rate(hour: int, tariff: str = "tou") -> float:
    if tariff == "flat":
        return FLAT_RATE
    for period, info in TOU_RATES.items():
        if hour in info["hours"]:
            return info["rate_usd_kwh"]
    return FLAT_RATE


def cheapest_window(duration_hours: float, tariff: str = "tou") -> dict:
    """Find the cheapest consecutive window of given duration."""
    hours = list(range(24))
    duration = int(duration_hours)
    best_cost = float("inf")
    best_start = 0

    for start in range(24):
        window = [(start + i) % 24 for i in range(duration)]
        cost = sum(get_rate(h, tariff) for h in window)
        if cost < best_cost:
            best_cost = cost
            best_start = start

    best_end = (best_start + duration) % 24
    return {
        "start_hour": best_start,
        "end_hour": best_end,
        "estimated_cost_usd_per_kwh": round(best_cost / duration, 4),
    }
