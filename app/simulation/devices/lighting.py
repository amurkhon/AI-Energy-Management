import random
from datetime import datetime


class Lighting:
    """Simulates lighting consumption based on occupancy and daylight availability."""

    def __init__(self, rated_power_kw: float = 0.5):
        self.rated_power_kw = rated_power_kw

    def generate_reading(self, sim_time: datetime, weather: dict, occupancy: float = 1.0, **kwargs) -> dict:
        irradiance = weather.get("solar_irradiance_wm2", 0)
        # Daylight reduces need for artificial lighting
        daylight_factor = max(0.0, 1.0 - irradiance / 600.0)
        power_kw = self.rated_power_kw * occupancy * daylight_factor
        power_kw += random.gauss(0, 0.01)
        power_kw = max(0, power_kw)

        return {
            "power_kw": round(-power_kw, 4),  # negative = consumption
            "temperature_c": weather.get("temperature_c"),
        }
