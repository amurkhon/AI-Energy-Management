import random
from datetime import datetime


class WindTurbine:
    """Simulates a wind turbine using a power curve."""

    def __init__(self, rated_power_kw: float = 10.0, cut_in_ms: float = 3.0, rated_ms: float = 12.0, cut_out_ms: float = 25.0):
        self.rated_power_kw = rated_power_kw
        self.cut_in_ms = cut_in_ms
        self.rated_ms = rated_ms
        self.cut_out_ms = cut_out_ms

    def generate_reading(self, sim_time: datetime, weather: dict, **kwargs) -> dict:
        wind_speed = weather.get("wind_speed_ms", 0)

        if wind_speed < self.cut_in_ms or wind_speed > self.cut_out_ms:
            power_kw = 0.0
        elif wind_speed >= self.rated_ms:
            power_kw = self.rated_power_kw
        else:
            # Cubic interpolation between cut-in and rated speed
            ratio = (wind_speed - self.cut_in_ms) / (self.rated_ms - self.cut_in_ms)
            power_kw = self.rated_power_kw * (ratio ** 3)

        power_kw *= (1 + random.gauss(0, 0.03))
        power_kw = max(0, power_kw)

        return {
            "power_kw": round(power_kw, 4),
            "temperature_c": weather.get("temperature_c"),
        }
