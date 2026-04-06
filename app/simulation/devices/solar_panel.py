import random
from datetime import datetime


class SolarPanel:
    """Simulates a PV solar panel based on irradiance."""

    def __init__(self, panel_area_m2: float = 20.0, efficiency: float = 0.18):
        self.panel_area_m2 = panel_area_m2
        self.efficiency = efficiency

    def generate_reading(self, sim_time: datetime, weather: dict, **kwargs) -> dict:
        irradiance = weather.get("solar_irradiance_wm2", 0)
        # P = irradiance * area * efficiency / 1000 (kW)
        power_kw = irradiance * self.panel_area_m2 * self.efficiency / 1000.0
        # Add small noise
        power_kw *= (1 + random.gauss(0, 0.02))
        power_kw = max(0, power_kw)
        return {
            "power_kw": round(power_kw, 4),
            "temperature_c": weather.get("temperature_c"),
        }
