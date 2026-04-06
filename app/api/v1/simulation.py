import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.simulation import SimulationSession, SimSessionStatus
from app.schemas.simulation import SimSessionCreate, SimSessionOut, SimSpeedUpdate
from app.core.exceptions import NotFoundError, ForbiddenError

router = APIRouter(prefix="/simulation", tags=["simulation"])


@router.get("/sessions", response_model=list[SimSessionOut])
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(SimulationSession).where(SimulationSession.user_id == current_user.id))
    return result.scalars().all()


@router.post("/sessions", response_model=SimSessionOut, status_code=201)
async def create_session(
    body: SimSessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = SimulationSession(
        user_id=current_user.id,
        name=body.name,
        sim_start_time=body.sim_start_time or datetime.now(timezone.utc),
        sim_speed=body.sim_speed,
        tick_interval_s=body.tick_interval_s,
        config={"device_ids": [str(d) for d in body.device_ids]},
    )
    db.add(session)
    await db.flush()
    return session


@router.get("/sessions/{session_id}", response_model=SimSessionOut)
async def get_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _get_owned_session(session_id, current_user.id, db)


@router.post("/sessions/{session_id}/pause", response_model=SimSessionOut)
async def pause_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = await _get_owned_session(session_id, current_user.id, db)
    session.status = SimSessionStatus.paused
    session.paused_at = datetime.now(timezone.utc)
    await db.flush()
    return session


@router.post("/sessions/{session_id}/resume", response_model=SimSessionOut)
async def resume_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = await _get_owned_session(session_id, current_user.id, db)
    session.status = SimSessionStatus.running
    session.paused_at = None
    await db.flush()
    return session


@router.post("/sessions/{session_id}/stop", response_model=SimSessionOut)
async def stop_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = await _get_owned_session(session_id, current_user.id, db)
    session.status = SimSessionStatus.stopped
    session.ended_at = datetime.now(timezone.utc)
    await db.flush()
    return session


@router.patch("/sessions/{session_id}/speed", response_model=SimSessionOut)
async def update_speed(
    session_id: uuid.UUID,
    body: SimSpeedUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = await _get_owned_session(session_id, current_user.id, db)
    session.sim_speed = body.sim_speed
    await db.flush()
    return session


@router.get("/status")
async def sim_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(SimulationSession)
        .where(SimulationSession.user_id == current_user.id, SimulationSession.status == SimSessionStatus.running)
        .order_by(SimulationSession.started_at.desc())
        .limit(1)
    )
    session = result.scalar_one_or_none()
    return {"running": session is not None, "session": SimSessionOut.model_validate(session) if session else None}


async def _get_owned_session(session_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> SimulationSession:
    result = await db.execute(select(SimulationSession).where(SimulationSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise NotFoundError("Simulation session not found")
    if session.user_id != user_id:
        raise ForbiddenError()
    return session
