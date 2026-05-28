import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from app.models.alert import AlertMetric, AlertOperator, AlertSeverity


class AlertRuleCreate(BaseModel):
    device_id: uuid.UUID | None = None
    name: str
    description: str | None = None
    metric: AlertMetric
    operator: AlertOperator
    threshold: float
    window_minutes: int = 5
    severity: AlertSeverity = AlertSeverity.warning
    cooldown_minutes: int = 60


class AlertRuleUpdate(BaseModel):
    name: str | None = None
    threshold: float | None = None
    severity: AlertSeverity | None = None
    is_active: bool | None = None
    cooldown_minutes: int | None = None


class AlertRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    user_id: uuid.UUID
    device_id: uuid.UUID | None
    name: str
    metric: AlertMetric
    operator: AlertOperator
    threshold: float
    severity: AlertSeverity
    is_active: bool
    window_minutes: int
    cooldown_minutes: int = Field(validation_alias='cooldown_mins')


class AlertEventOut(BaseModel):
    id: uuid.UUID
    rule_id: uuid.UUID
    device_id: uuid.UUID
    triggered_at: datetime
    resolved_at: datetime | None
    actual_value: float | None
    severity: AlertSeverity
    message: str | None
    is_acknowledged: bool

    class Config:
        from_attributes = True
