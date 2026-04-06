import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.suggestion import AISuggestion, SuggestionCategory, SuggestionPriority
from app.schemas.suggestion import SuggestionOut, SuggestionSummary
from app.core.exceptions import NotFoundError, ForbiddenError

router = APIRouter(prefix="/suggestions", tags=["suggestions"])


@router.get("", response_model=list[SuggestionOut])
async def list_suggestions(
    category: SuggestionCategory | None = None,
    priority: SuggestionPriority | None = None,
    dismissed: bool = Query(False),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conditions = [
        AISuggestion.user_id == current_user.id,
        AISuggestion.is_dismissed == dismissed,
    ]
    if category:
        conditions.append(AISuggestion.category == category)
    if priority:
        conditions.append(AISuggestion.priority == priority)

    result = await db.execute(
        select(AISuggestion)
        .where(and_(*conditions))
        .order_by(AISuggestion.generated_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.post("/generate", status_code=202)
async def generate_suggestions(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    from app.ai.engine import run_ai_analysis
    background_tasks.add_task(run_ai_analysis, str(current_user.id))
    return {"message": "AI analysis triggered", "user_id": str(current_user.id)}


@router.get("/summary", response_model=SuggestionSummary)
async def suggestions_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conditions = [AISuggestion.user_id == current_user.id, AISuggestion.is_dismissed == False]
    result = await db.execute(
        select(
            func.count(AISuggestion.id).label("total"),
            func.sum(AISuggestion.estimated_saving_kwh).label("kwh"),
            func.sum(AISuggestion.estimated_saving_cost).label("cost"),
        ).where(and_(*conditions))
    )
    row = result.one()

    counts = {}
    for p in SuggestionPriority:
        cr = await db.execute(
            select(func.count(AISuggestion.id)).where(
                and_(*conditions, AISuggestion.priority == p)
            )
        )
        counts[p.value] = cr.scalar() or 0

    return SuggestionSummary(
        total_active=row.total or 0,
        critical=counts.get("critical", 0),
        high=counts.get("high", 0),
        medium=counts.get("medium", 0),
        low=counts.get("low", 0),
        estimated_total_saving_kwh=round(row.kwh or 0, 3),
        estimated_total_saving_cost=round(row.cost or 0, 2),
    )


@router.patch("/{suggestion_id}/dismiss", response_model=SuggestionOut)
async def dismiss_suggestion(
    suggestion_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = await _get_owned_suggestion(suggestion_id, current_user.id, db)
    s.is_dismissed = True
    s.dismissed_at = datetime.now(timezone.utc)
    await db.flush()
    return s


@router.patch("/{suggestion_id}/apply", response_model=SuggestionOut)
async def apply_suggestion(
    suggestion_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = await _get_owned_suggestion(suggestion_id, current_user.id, db)
    s.is_applied = True
    s.applied_at = datetime.now(timezone.utc)
    await db.flush()
    return s


async def _get_owned_suggestion(suggestion_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> AISuggestion:
    result = await db.execute(select(AISuggestion).where(AISuggestion.id == suggestion_id))
    s = result.scalar_one_or_none()
    if not s:
        raise NotFoundError("Suggestion not found")
    if s.user_id != user_id:
        raise ForbiddenError()
    return s
