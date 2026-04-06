import uuid
import json
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.db.session import get_db
from app.cache.client import get_redis
from app.cache.keys import device_latest
from app.dependencies import get_current_user
from app.models.user import User
from app.models.reading import EnergyReading
from app.models.device import Device
from app.schemas.reading import ReadingCreate, ReadingOut, ReadingLatest
from app.core.exceptions import NotFoundError
import redis.asyncio as aioredis

router = APIRouter(prefix="/readings", tags=["readings"])


@router.get("", response_model=list[ReadingOut])
async def list_readings(
    device_id: uuid.UUID | None = Query(None),
    from_dt: datetime | None = Query(None, alias="from"),
    to_dt: datetime | None = Query(None, alias="to"),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conditions = []
    if device_id:
        # Verify ownership
        res = await db.execute(select(Device).where(Device.id == device_id, Device.user_id == current_user.id))
        if not res.scalar_one_or_none():
            raise NotFoundError("Device not found")
        conditions.append(EnergyReading.device_id == device_id)
    else:
        # Only readings for user's devices
        user_devices = await db.execute(select(Device.id).where(Device.user_id == current_user.id))
        device_ids = [r for r in user_devices.scalars()]
        conditions.append(EnergyReading.device_id.in_(device_ids))

    if from_dt:
        conditions.append(EnergyReading.recorded_at >= from_dt)
    if to_dt:
        conditions.append(EnergyReading.recorded_at <= to_dt)

    result = await db.execute(
        select(EnergyReading)
        .where(and_(*conditions))
        .order_by(EnergyReading.recorded_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


@router.post("", response_model=ReadingOut, status_code=201)
async def create_reading(
    body: ReadingCreate,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    current_user: User = Depends(get_current_user),
):
    res = await db.execute(select(Device).where(Device.id == body.device_id, Device.user_id == current_user.id))
    if not res.scalar_one_or_none():
        raise NotFoundError("Device not found")

    reading = EnergyReading(**body.model_dump(exclude_none=True))
    db.add(reading)
    await db.flush()

    # Cache latest reading
    await redis.set(
        device_latest(str(body.device_id)),
        json.dumps({
            "device_id": str(body.device_id),
            "power_kw": body.power_kw,
            "energy_kwh": body.energy_kwh,
            "state_of_charge": body.state_of_charge,
            "recorded_at": (body.recorded_at or datetime.utcnow()).isoformat(),
        }),
        ex=3600,
    )
    return reading


@router.get("/latest", response_model=list[ReadingLatest])
async def latest_readings(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    current_user: User = Depends(get_current_user),
):
    user_devices = await db.execute(
        select(Device.id).where(Device.user_id == current_user.id, Device.is_active == True)
    )
    device_ids = list(user_devices.scalars())
    results = []
    for did in device_ids:
        raw = await redis.get(device_latest(str(did)))
        if raw:
            data = json.loads(raw)
            results.append(ReadingLatest(**data))
    return results
