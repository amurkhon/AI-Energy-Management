import random
from datetime import datetime


class EVCharger:
    """Simulates EV charger with schedule-based charging."""

    def __init__(self, charge_power_kw: float = 7.4, charge_start_hour: int = 23, charge_end_hour: int = 6,
                 battery_capacity_kwh: float = 60.0, initial_soc: float = 0.3):
        self.charge_power_kw = charge_power_kw
        self.charge_start_hour = charge_start_hour
        self.charge_end_hour = charge_end_hour
        self.battery_capacity_kwh = battery_capacity_kwh
        self.soc = initial_soc

    def _is_charging_time(self, hour: int) -> bool:
        if self.charge_start_hour > self.charge_end_hour:
            # Overnight schedule (e.g. 23:00 - 06:00)
            return hour >= self.charge_start_hour or hour < self.charge_end_hour
        return self.charge_start_hour <= hour < self.charge_end_hour

    def generate_reading(self, sim_time: datetime, weather: dict, tick_hours: float = 1 / 60, **kwargs) -> dict:
        hour = sim_time.hour
        if self._is_charging_time(hour) and self.soc < 0.95:
            power_kw = self.charge_power_kw
            self.soc += (power_kw * tick_hours) / self.battery_capacity_kwh
            self.soc = min(1.0, self.soc)
        else:
            # During the day, soc decreases as EV is driven
            if not self._is_charging_time(hour) and random.random() < 0.01:
                self.soc = max(0.1, self.soc - random.uniform(0.05, 0.2))
            power_kw = 0.0

        return {
            "power_kw": round(-power_kw, 4),  # negative = consumption
            "state_of_charge": round(self.soc * 100, 1),
            "temperature_c": weather.get("temperature_c"),
        }
