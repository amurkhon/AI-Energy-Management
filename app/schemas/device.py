import uuid
from pydantic import BaseModel
from app.models.device import DeviceType, SimProfile


class DeviceGroupCreate(BaseModel):
    name: str
    location: str | None = None


class DeviceGroupOut(BaseModel):
    id: uuid.UUID
    name: str
    location: str | None
    user_id: uuid.UUID

    class Config:
        from_attributes = True


class DeviceCreate(BaseModel):
    name: str
    device_type: DeviceType
    group_id: uuid.UUID | None = None
    rated_capacity: float | None = None
    metadata_: dict | None = None
    sim_profile: SimProfile = SimProfile.residential
    latitude: float | None = None
    longitude: float | None = None


class DeviceUpdate(BaseModel):
    name: str | None = None
    group_id: uuid.UUID | None = None
    rated_capacity: float | None = None
    metadata_: dict | None = None
    sim_profile: SimProfile | None = None
    is_active: bool | None = None


class DeviceOut(BaseModel):
    id: uuid.UUID
    name: str
    device_type: DeviceType
    group_id: uuid.UUID | None
    user_id: uuid.UUID
    is_active: bool
    is_simulated: bool
    rated_capacity: float | None
    sim_profile: SimProfile
    latitude: float | None
    longitude: float | None

    class Config:
        from_attributes = True
