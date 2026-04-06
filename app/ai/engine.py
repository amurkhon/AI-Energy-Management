import uuid
from sqlalchemy import select
from app.models.device import Device
from app.models.user import User


async def run_ai_analysis(user_id: str):
    """
    Entry point for on-demand AI analysis.
    Called from FastAPI BackgroundTasks or Celery.
    """
    from app.db.session import AsyncSessionLocal
    from app.ai.suggestions.generator import generate_for_device

    async with AsyncSessionLocal() as db:
        uid = uuid.UUID(user_id)
        result = await db.execute(
            select(Device).where(Device.user_id == uid, Device.is_active == True)
        )
        devices = result.scalars().all()

        all_suggestions = []
        for device in devices:
            try:
                suggestions = await generate_for_device(device, uid, db)
                all_suggestions.extend(suggestions)
            except Exception as e:
                # Log and continue — don't fail entire analysis for one device
                print(f"AI analysis failed for device {device.id}: {e}")

        await db.commit()
        return len(all_suggestions)
