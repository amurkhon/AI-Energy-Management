import random
from datetime import datetime


class Battery:
    """Simulates a battery with charge/discharge logic based on net grid power."""

    def __init__(self, capacity_kwh: float = 13.5, charge_rate_kw: float = 5.0, initial_soc: float | None = None):
        self.capacity_kwh = capacity_kwh
        self.charge_rate_kw = charge_rate_kw
        self.soc = initial_soc if initial_soc is not None else 0.5  # 0.0 - 1.0

    def generate_reading(self, sim_time: datetime, weather: dict, net_grid_kw: float = 0.0, tick_hours: float = 1 / 60, **kwargs) -> dict:
        """
        net_grid_kw: positive = surplus (charge), negative = deficit (discharge)
        """
        if net_grid_kw > 0 and self.soc < 1.0:
            # Charge
            charge_kw = min(net_grid_kw, self.charge_rate_kw, (1.0 - self.soc) * self.capacity_kwh / tick_hours)
            self.soc += (charge_kw * tick_hours) / self.capacity_kwh
            power_kw = -charge_kw  # negative = consuming from grid perspective
        elif net_grid_kw < 0 and self.soc > 0.05:
            # Discharge
            discharge_kw = min(abs(net_grid_kw), self.charge_rate_kw, self.soc * self.capacity_kwh / tick_hours)
            self.soc -= (discharge_kw * tick_hours) / self.capacity_kwh
            power_kw = discharge_kw  # positive = producing
        else:
            power_kw = 0.0

        self.soc = max(0.0, min(1.0, self.soc))
        noise = random.gauss(0, 0.01)

        return {
            "power_kw": round(power_kw + noise, 4),
            "state_of_charge": round(self.soc * 100, 1),
            "temperature_c": weather.get("temperature_c"),
        }
