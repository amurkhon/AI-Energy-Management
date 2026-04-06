import random
from datetime import datetime


class OccupancySimulator:
    """Simulates building/home occupancy based on time of day and profile."""

    RESIDENTIAL_PATTERN = {
        # hour -> base occupancy probability
        0: 0.95, 1: 0.95, 2: 0.95, 3: 0.95, 4: 0.95, 5: 0.80,
        6: 0.70, 7: 0.60, 8: 0.30, 9: 0.20, 10: 0.15, 11: 0.15,
        12: 0.25, 13: 0.20, 14: 0.15, 15: 0.20, 16: 0.35, 17: 0.55,
        18: 0.75, 19: 0.85, 20: 0.90, 21: 0.90, 22: 0.90, 23: 0.95,
    }

    COMMERCIAL_PATTERN = {
        0: 0.02, 1: 0.02, 2: 0.02, 3: 0.02, 4: 0.02, 5: 0.05,
        6: 0.15, 7: 0.40, 8: 0.80, 9: 0.95, 10: 0.95, 11: 0.90,
        12: 0.70, 13: 0.85, 14: 0.95, 15: 0.90, 16: 0.80, 17: 0.50,
        18: 0.20, 19: 0.10, 20: 0.05, 21: 0.03, 22: 0.02, 23: 0.02,
    }

    def __init__(self, profile: str = "residential"):
        self.pattern = self.RESIDENTIAL_PATTERN if profile == "residential" else self.COMMERCIAL_PATTERN

    def is_occupied(self, sim_time: datetime) -> bool:
        hour = sim_time.hour
        is_weekend = sim_time.weekday() >= 5
        prob = self.pattern.get(hour, 0.5)
        if is_weekend:
            # Residential: more home on weekends; Commercial: less
            if self.pattern is self.RESIDENTIAL_PATTERN:
                prob = min(1.0, prob + 0.15)
            else:
                prob *= 0.3
        return random.random() < prob

    def occupancy_fraction(self, sim_time: datetime) -> float:
        """Returns 0.0-1.0 occupancy level (useful for lighting etc.)."""
        hour = sim_time.hour
        prob = self.pattern.get(hour, 0.5)
        noise = random.gauss(0, 0.05)
        return max(0.0, min(1.0, prob + noise))
