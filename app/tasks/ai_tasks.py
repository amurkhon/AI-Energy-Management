import asyncio
from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.ai_tasks.run_ai_for_all_users")
def run_ai_for_all_users():
    asyncio.run(_run_ai_for_all_users())


async def _run_ai_for_all_users():
    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal
    from app.models.user import User
    from app.ai.engine import run_ai_analysis

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User.id).where(User.is_active == True))
        user_ids = [str(uid) for uid in result.scalars()]

    for user_id in user_ids:
        try:
            await run_ai_analysis(user_id)
        except Exception as e:
            print(f"AI task failed for user {user_id}: {e}")


@celery_app.task(name="app.tasks.ai_tasks.retrain_models_for_device")
def retrain_models_for_device(device_id: str):
    asyncio.run(_retrain(device_id))


async def _retrain(device_id: str):
    from app.db.session import AsyncSessionLocal
    from app.ai.feature_engineering import build_features
    from app.ai.anomaly.detector import train_isolation_forest
    from app.ai.forecasting.load_forecaster import train_forecaster

    async with AsyncSessionLocal() as db:
        df = await build_features(device_id, db, hours=720)  # 30 days
        if df.empty:
            return
        train_isolation_forest(df, device_id)
        for horizon in ["1h", "6h", "24h", "7d"]:
            train_forecaster(df, device_id, horizon)
