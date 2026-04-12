import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Enum as SAEnum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base


class SuggestionCategory(str, enum.Enum):
    anomaly = "anomaly"
    load_shifting = "load_shifting"
    renewable = "renewable"
    efficiency = "efficiency"
    forecast = "forecast"


class SuggestionPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class SuggestionSource(str, enum.Enum):
    rule_based = "rule_based"
    ml_anomaly = "ml_anomaly"
    ml_forecast = "ml_forecast"
    ml_optimization = "ml_optimization"


class AISuggestion(Base):
    __tablename__ = "ai_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    device_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("devices.id"), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    category: Mapped[SuggestionCategory] = mapped_column(
        SAEnum(SuggestionCategory, name="suggestioncategory"), nullable=False
    )
    priority: Mapped[SuggestionPriority] = mapped_column(
        SAEnum(SuggestionPriority, name="suggestionpriority"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    action_detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    estimated_saving_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_saving_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[SuggestionSource] = mapped_column(
        SAEnum(SuggestionSource, name="suggestionsource"), nullable=False
    )
    is_dismissed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
