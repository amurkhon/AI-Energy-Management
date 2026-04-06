import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.suggestion import SuggestionCategory, SuggestionPriority, SuggestionSource


class SuggestionOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    device_id: uuid.UUID | None
    generated_at: datetime
    expires_at: datetime | None
    category: SuggestionCategory
    priority: SuggestionPriority
    title: str
    description: str
    action_detail: dict | None
    estimated_saving_kwh: float | None
    estimated_saving_cost: float | None
    confidence_score: float | None
    source: SuggestionSource
    is_dismissed: bool
    is_applied: bool

    class Config:
        from_attributes = True


class SuggestionSummary(BaseModel):
    total_active: int
    critical: int
    high: int
    medium: int
    low: int
    estimated_total_saving_kwh: float
    estimated_total_saving_cost: float
