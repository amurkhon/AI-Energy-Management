import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.device import Device, DeviceGroup
from app.schemas.device import DeviceCreate, DeviceUpdate, DeviceOut, DeviceGroupCreate, DeviceGroupOut
from app.core.exceptions import NotFoundError, ForbiddenError

router = APIRouter(prefix="/devices", tags=["devices"])
groups_router = APIRouter(prefix="/device-groups", tags=["device-groups"])


# ── Devices ──────────────────────────────────────────────────────────────────

@router.get("", response_model=list[DeviceOut])
async def list_devices(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Device).where(Device.user_id == current_user.id))
    return result.scalars().all()


@router.post("", response_model=DeviceOut, status_code=201)
async def create_device(
    body: DeviceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    device = Device(
        user_id=current_user.id,
        name=body.name,
        device_type=body.device_type,
        group_id=body.group_id,
        rated_capacity=body.rated_capacity,
        metadata_=body.metadata_,
        sim_profile=body.sim_profile,
        latitude=body.latitude,
        longitude=body.longitude,
    )
    db.add(device)
    await db.flush()
    return device


@router.get("/{device_id}", response_model=DeviceOut)
async def get_device(
    device_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    device = await _get_owned_device(device_id, current_user.id, db)
    return device


@router.patch("/{device_id}", response_model=DeviceOut)
async def update_device(
    device_id: uuid.UUID,
    body: DeviceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    device = await _get_owned_device(device_id, current_user.id, db)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(device, field, value)
    await db.flush()
    return device


@router.delete("/{device_id}", status_code=204)
async def delete_device(
    device_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    device = await _get_owned_device(device_id, current_user.id, db)
    device.is_active = False
    await db.flush()


@router.post("/{device_id}/toggle", response_model=DeviceOut)
async def toggle_device(
    device_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    device = await _get_owned_device(device_id, current_user.id, db)
    device.is_active = not device.is_active
    await db.flush()
    return device


async def _get_owned_device(device_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> Device:
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise NotFoundError("Device not found")
    if device.user_id != user_id:
        raise ForbiddenError()
    return device


# ── Device Groups ─────────────────────────────────────────────────────────────

@groups_router.get("", response_model=list[DeviceGroupOut])
async def list_groups(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(DeviceGroup).where(DeviceGroup.user_id == current_user.id))
    return result.scalars().all()


@groups_router.post("", response_model=DeviceGroupOut, status_code=201)
async def create_group(
    body: DeviceGroupCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = DeviceGroup(user_id=current_user.id, name=body.name, location=body.location)
    db.add(group)
    await db.flush()
    return group


@groups_router.get("/{group_id}/devices", response_model=list[DeviceOut])
async def list_group_devices(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Device).where(Device.group_id == group_id, Device.user_id == current_user.id)
    )
    return result.scalars().all()
