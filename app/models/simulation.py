import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import DateTime, Enum as SAEnum, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base


class SimSessionStatus(str, enum.Enum):
    running = "running"
    paused = "paused"
    stopped = "stopped"
    completed = "completed"


class SimulationSession(Base):
    __tablename__ = "simulation_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[SimSessionStatus] = mapped_column(
        SAEnum(SimSessionStatus, name="simsessionstatus"), nullable=False, default=SimSessionStatus.running
    )
    sim_start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sim_speed: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    tick_interval_s: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
