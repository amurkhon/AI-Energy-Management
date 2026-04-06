import math
import random
from datetime import datetime


class WeatherSimulator:
    """Generates realistic weather data based on time of day and season."""

    def __init__(self, latitude: float = 40.0, noise_factor: float = 0.1):
        self.latitude = latitude
        self.noise_factor = noise_factor

    def get_conditions(self, sim_time: datetime) -> dict:
        hour = sim_time.hour + sim_time.minute / 60.0
        day_of_year = sim_time.timetuple().tm_yday

        temperature_c = self._temperature(hour, day_of_year)
        irradiance = self._solar_irradiance(hour, day_of_year)
        wind_speed = self._wind_speed(hour)
        cloud_cover = self._cloud_cover()

        # Cloud cover reduces irradiance
        irradiance *= (1.0 - cloud_cover * 0.8)

        return {
            "temperature_c": round(temperature_c, 1),
            "solar_irradiance_wm2": round(max(0, irradiance), 1),
            "wind_speed_ms": round(max(0, wind_speed), 1),
            "cloud_cover": round(cloud_cover, 2),
        }

    def _temperature(self, hour: float, day_of_year: int) -> float:
        # Seasonal: peaks ~summer (day 172), troughs ~winter (day 355)
        seasonal = 10 * math.sin(2 * math.pi * (day_of_year - 80) / 365)
        # Diurnal: warmest ~14:00, coolest ~06:00
        diurnal = 8 * math.sin(2 * math.pi * (hour - 6) / 24)
        base = 15.0
        noise = random.gauss(0, self.noise_factor * 2)
        return base + seasonal + diurnal + noise

    def _solar_irradiance(self, hour: float, day_of_year: int) -> float:
        # Sunrise/sunset depend on latitude + season
        declination = 23.45 * math.sin(math.radians(360 / 365 * (day_of_year - 81)))
        lat_rad = math.radians(self.latitude)
        decl_rad = math.radians(declination)
        # Hour angle
        hour_angle = 15 * (hour - 12)
        cos_zenith = (
            math.sin(lat_rad) * math.sin(decl_rad)
            + math.cos(lat_rad) * math.cos(decl_rad) * math.cos(math.radians(hour_angle))
        )
        if cos_zenith <= 0:
            return 0.0
        # Max irradiance at zenith ~1000 W/m²
        irradiance = 1000 * cos_zenith
        noise = random.gauss(0, self.noise_factor * 50)
        return max(0, irradiance + noise)

    def _wind_speed(self, hour: float) -> float:
        # Generally windier midday
        base = 4.0 + 2.0 * math.sin(2 * math.pi * (hour - 6) / 24)
        noise = random.gauss(0, 1.0)
        return max(0, base + noise)

    def _cloud_cover(self) -> float:
        return max(0.0, min(1.0, random.betavariate(2, 5)))
