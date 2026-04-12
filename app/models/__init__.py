from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import all models so Alembic can discover them via Base.metadata
from app.models.user import User  # noqa: E402, F401
from app.models.device import Device, DeviceGroup  # noqa: E402, F401
from app.models.reading import EnergyReading, EnergyReadingHourly, EnergyReadingDaily  # noqa: E402, F401
from app.models.alert import AlertRule, AlertEvent  # noqa: E402, F401
from app.models.suggestion import AISuggestion  # noqa: E402, F401
from app.models.simulation import SimulationSession  # noqa: E402, F401
from app.models.prediction import AnomalyRecord  # noqa: E402, F401
