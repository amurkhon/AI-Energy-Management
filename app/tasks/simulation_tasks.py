import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.simulation_tasks.run_all_active_sessions")
def run_all_active_sessions():
    asyncio.run(_run_all_active_sessions())


async def _run_all_active_sessions():
    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal
    from app.cache.client import get_redis
    from app.models.simulation import SimulationSession, SimSessionStatus
    from app.models.device import Device
    from app.models.reading import EnergyReading
    from app.simulation.engine import run_simulation_tick

    async with AsyncSessionLocal() as db:
        redis = await get_redis()

        sessions_res = await db.execute(
            select(SimulationSession).where(SimulationSession.status == SimSessionStatus.running)
        )
        sessions = sessions_res.scalars().all()

        for session in sessions:
            device_ids = session.config.get("device_ids", []) if session.config else []
            if not device_ids:
                continue

            devices_res = await db.execute(
                select(Device).where(Device.id.in_([uuid.UUID(d) for d in device_ids]), Device.is_active == True)
            )
            devices = [
                {
                    "id": str(d.id),
                    "device_type": d.device_type.value,
                    "metadata_": d.metadata_ or {},
                    "sim_profile": d.sim_profile.value,
                    "latitude": d.latitude or 40.0,
                    "longitude": d.longitude or -74.0,
                    "rated_capacity": d.rated_capacity,
                }
                for d in devices_res.scalars()
            ]

            # Advance simulated time
            tick_hours = (session.tick_interval_s * session.sim_speed) / 3600.0
            sim_time = session.sim_start_time + timedelta(
                seconds=session.tick_interval_s * session.sim_speed
            )
            session.sim_start_time = sim_time

            readings_data = await run_simulation_tick(
                session_id=str(session.id),
                sim_time=sim_time,
                devices=devices,
                tick_hours=tick_hours,
                redis=redis,
                db_session=db,
            )

            # Bulk insert readings
            for rd in readings_data:
                reading = EnergyReading(
                    device_id=uuid.UUID(rd["device_id"]),
                    recorded_at=datetime.fromisoformat(rd["recorded_at"]),
                    power_kw=rd["power_kw"],
                    energy_kwh=rd["energy_kwh"],
                    state_of_charge=rd.get("state_of_charge"),
                    temperature_c=rd.get("temperature_c"),
                    metadata_=rd.get("metadata_"),
                )
                db.add(reading)

        await db.commit()

        # Trigger AI analysis for users whose simulation sessions ran
        from app.ai.engine import run_ai_analysis
        user_ids = {str(session.user_id) for session in sessions if session.user_id}
        for uid in user_ids:
            try:
                await run_ai_analysis(uid)
            except Exception as e:
                print(f"AI analysis failed for user {uid} after sim tick: {e}")
