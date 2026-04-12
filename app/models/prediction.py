import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Enum as SAEnum, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base


class AnomalyType(str, enum.Enum):
    spike = "spike"
    dropout = "dropout"
    drift = "drift"
    pattern_break = "pattern_break"


class AnomalyRecord(Base):
    __tablename__ = "anomaly_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id"), nullable=False, index=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    reading_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("energy_readings.id"), nullable=True)
    anomaly_type: Mapped[AnomalyType] = mapped_column(SAEnum(AnomalyType, name="anomalytype"), nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    z_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    suggestion_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_suggestions.id"), nullable=True)
