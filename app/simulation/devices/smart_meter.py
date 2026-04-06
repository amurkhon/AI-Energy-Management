import random
from datetime import datetime


class SmartMeter:
    """Aggregates power from all devices in a group; adds baseline load."""

    def __init__(self, baseline_kw: float = 0.3):
        self.baseline_kw = baseline_kw

    def generate_reading(self, sim_time: datetime, weather: dict, aggregated_power_kw: float = 0.0, **kwargs) -> dict:
        # Add baseline noise
        noise = random.gauss(0, 0.02)
        total = aggregated_power_kw - self.baseline_kw + noise
        return {
            "power_kw": round(total, 4),
            "temperature_c": weather.get("temperature_c"),
        }
