import random
from datetime import datetime


class HVAC:
    """Simulates HVAC consumption based on temperature difference from setpoint."""

    def __init__(self, setpoint_c: float = 21.0, rated_power_kw: float = 3.5, cop: float = 3.0):
        self.setpoint_c = setpoint_c
        self.rated_power_kw = rated_power_kw
        self.cop = cop  # coefficient of performance

    def generate_reading(self, sim_time: datetime, weather: dict, occupancy: float = 1.0, **kwargs) -> dict:
        outside_temp = weather.get("temperature_c", 15.0)
        delta = abs(outside_temp - self.setpoint_c)

        # Load proportional to temperature difference and occupancy
        load_fraction = min(1.0, delta / 15.0)
        power_kw = self.rated_power_kw * load_fraction * occupancy / self.cop
        power_kw += random.gauss(0, 0.05)
        power_kw = max(0, power_kw)

        return {
            "power_kw": round(-power_kw, 4),  # negative = consumption
            "temperature_c": outside_temp,
        }
