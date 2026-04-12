import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, Float, DateTime, Enum as SAEnum, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base


class DeviceType(str, enum.Enum):
    smart_meter = "smart_meter"
    solar_panel = "solar_panel"
    wind_turbine = "wind_turbine"
    battery = "battery"
    hvac = "hvac"
    lighting = "lighting"
    ev_charger = "ev_charger"
    appliance = "appliance"


class SimProfile(str, enum.Enum):
    residential = "residential"
    commercial = "commercial"
    industrial = "industrial"


class DeviceGroup(Base):
    __tablename__ = "device_groups"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    device_type: Mapped[DeviceType] = mapped_column(SAEnum(DeviceType, name="devicetype"), nullable=False)
    group_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("device_groups.id"), nullable=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rated_capacity: Mapped[float | None] = mapped_column(Float, nullable=True)
    # "metadata" is reserved by SQLAlchemy's DeclarativeBase; map to column name "metadata"
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    sim_profile: Mapped[SimProfile] = mapped_column(
        SAEnum(SimProfile, name="simprofile"), nullable=False, default=SimProfile.residential
    )
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
