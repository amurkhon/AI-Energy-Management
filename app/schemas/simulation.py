import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.simulation import SimSessionStatus


class SimSessionCreate(BaseModel):
    name: str | None = None
    sim_start_time: datetime | None = None
    sim_speed: float = 1.0
    tick_interval_s: int = 60
    device_ids: list[uuid.UUID] = []


class SimSessionOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str | None
    status: SimSessionStatus
    sim_start_time: datetime | None
    sim_speed: float
    tick_interval_s: int
    started_at: datetime
    paused_at: datetime | None
    ended_at: datetime | None

    class Config:
        from_attributes = True


class SimSpeedUpdate(BaseModel):
    sim_speed: float
