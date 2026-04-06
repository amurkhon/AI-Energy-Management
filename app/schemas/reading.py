import uuid
from datetime import datetime
from pydantic import BaseModel


class ReadingCreate(BaseModel):
    device_id: uuid.UUID
    recorded_at: datetime | None = None
    power_kw: float
    energy_kwh: float
    voltage_v: float | None = None
    current_a: float | None = None
    frequency_hz: float | None = None
    power_factor: float | None = None
    state_of_charge: float | None = None
    temperature_c: float | None = None
    metadata_: dict | None = None


class ReadingOut(BaseModel):
    id: uuid.UUID
    device_id: uuid.UUID
    recorded_at: datetime
    power_kw: float
    energy_kwh: float
    voltage_v: float | None
    current_a: float | None
    state_of_charge: float | None
    temperature_c: float | None

    class Config:
        from_attributes = True


class ReadingLatest(BaseModel):
    device_id: uuid.UUID
    power_kw: float
    energy_kwh: float
    state_of_charge: float | None
    recorded_at: datetime
