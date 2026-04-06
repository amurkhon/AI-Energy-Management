import random
from datetime import datetime


class GenericAppliance:
    """Simulates generic appliances (washer, dishwasher, fridge, etc.)."""

    # Typical usage windows per appliance type
    USAGE_PROFILES = {
        "washer":     {"peak_hours": [8, 9, 10, 18, 19], "rated_kw": 2.0, "duty_cycle": 0.3},
        "dishwasher": {"peak_hours": [19, 20, 21], "rated_kw": 1.8, "duty_cycle": 0.4},
        "fridge":     {"peak_hours": list(range(24)), "rated_kw": 0.15, "duty_cycle": 0.35},
        "oven":       {"peak_hours": [11, 12, 17, 18, 19], "rated_kw": 2.5, "duty_cycle": 0.25},
        "generic":    {"peak_hours": list(range(8, 22)), "rated_kw": 0.5, "duty_cycle": 0.2},
    }

    def __init__(self, appliance_type: str = "generic", rated_power_kw: float | None = None):
        profile = self.USAGE_PROFILES.get(appliance_type, self.USAGE_PROFILES["generic"])
        self.peak_hours = profile["peak_hours"]
        self.rated_kw = rated_power_kw or profile["rated_kw"]
        self.duty_cycle = profile["duty_cycle"]
        self._on = False

    def generate_reading(self, sim_time: datetime, weather: dict, occupancy: float = 1.0, **kwargs) -> dict:
        hour = sim_time.hour
        in_peak = hour in self.peak_hours

        # Transition on/off stochastically
        if in_peak and occupancy > 0.3:
            if not self._on and random.random() < self.duty_cycle / len(self.peak_hours):
                self._on = True
            elif self._on and random.random() < 0.1:
                self._on = False
        else:
            if self._on and random.random() < 0.3:
                self._on = False

        power_kw = self.rated_kw * (1 + random.gauss(0, 0.05)) if self._on else 0.0
        power_kw = max(0, power_kw)

        return {
            "power_kw": round(-power_kw, 4),  # negative = consumption
            "temperature_c": weather.get("temperature_c"),
        }
