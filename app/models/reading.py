import uuid
from datetime import date, datetime, timezone
from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base


class EnergyReading(Base):
    __tablename__ = "energy_readings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id"), nullable=False, index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    power_kw: Mapped[float] = mapped_column(Float, nullable=False)
    energy_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    voltage_v: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_a: Mapped[float | None] = mapped_column(Float, nullable=True)
    frequency_hz: Mapped[float | None] = mapped_column(Float, nullable=True)
    power_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    state_of_charge: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class EnergyReadingHourly(Base):
    __tablename__ = "energy_readings_hourly"

    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id"), nullable=False, primary_key=True)
    hour_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, primary_key=True)
    total_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_power_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    peak_power_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_power_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    reading_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class EnergyReadingDaily(Base):
    __tablename__ = "energy_readings_daily"

    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id"), nullable=False, primary_key=True)
    day_bucket: Mapped[date] = mapped_column(Date, nullable=False, primary_key=True)
    total_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_power_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    peak_power_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    production_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    consumption_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
