import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.alert import AlertRule, AlertEvent, AlertSeverity
from app.schemas.alert import AlertRuleCreate, AlertRuleUpdate, AlertRuleOut, AlertEventOut
from app.core.exceptions import NotFoundError, ForbiddenError

router = APIRouter(prefix="/alerts", tags=["alerts"])
rules_router = APIRouter(prefix="/alert-rules", tags=["alert-rules"])


@router.get("", response_model=list[AlertEventOut])
async def list_alerts(
    severity: AlertSeverity | None = None,
    acknowledged: bool | None = None,
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Get user's rule IDs
    rule_ids_res = await db.execute(select(AlertRule.id).where(AlertRule.user_id == current_user.id))
    rule_ids = list(rule_ids_res.scalars())

    conditions = [AlertEvent.rule_id.in_(rule_ids)]
    if severity:
        conditions.append(AlertEvent.severity == severity)
    if acknowledged is not None:
        conditions.append(AlertEvent.is_acknowledged == acknowledged)

    result = await db.execute(
        select(AlertEvent)
        .where(and_(*conditions))
        .order_by(AlertEvent.triggered_at.desc())
        .limit(limit).offset(offset)
    )
    return result.scalars().all()


@router.patch("/{event_id}/acknowledge", response_model=AlertEventOut)
async def acknowledge_alert(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(AlertEvent).where(AlertEvent.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise NotFoundError("Alert event not found")
    event.is_acknowledged = True
    event.acknowledged_by = current_user.id
    await db.flush()
    return event


# ── Alert Rules ───────────────────────────────────────────────────────────────

@rules_router.get("", response_model=list[AlertRuleOut])
async def list_rules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(AlertRule).where(AlertRule.user_id == current_user.id))
    return result.scalars().all()


@rules_router.post("", response_model=AlertRuleOut, status_code=201)
async def create_rule(
    body: AlertRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = body.model_dump()
    data['cooldown_mins'] = data.pop('cooldown_minutes', 60)
    rule = AlertRule(user_id=current_user.id, **data)
    db.add(rule)
    await db.flush()
    return rule


@rules_router.patch("/{rule_id}", response_model=AlertRuleOut)
async def update_rule(
    rule_id: uuid.UUID,
    body: AlertRuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rule = await _get_owned_rule(rule_id, current_user.id, db)
    data = body.model_dump(exclude_none=True)
    if 'cooldown_minutes' in data:
        data['cooldown_mins'] = data.pop('cooldown_minutes')
    for key, value in data.items():
        setattr(rule, key, value)
    await db.flush()
    return rule


@rules_router.delete("/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rule = await _get_owned_rule(rule_id, current_user.id, db)
    await db.delete(rule)
    await db.flush()


async def _get_owned_rule(rule_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> AlertRule:
    result = await db.execute(select(AlertRule).where(AlertRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise NotFoundError("Alert rule not found")
    if rule.user_id != user_id:
        raise ForbiddenError()
    return rule
