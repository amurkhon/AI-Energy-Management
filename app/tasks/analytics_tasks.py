import asyncio
from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.analytics_tasks.hourly_rollup")
def hourly_rollup():
    asyncio.run(_hourly_rollup())


@celery_app.task(name="app.tasks.analytics_tasks.daily_rollup")
def daily_rollup():
    asyncio.run(_daily_rollup())


async def _hourly_rollup():
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select, func, text
    from app.db.session import AsyncSessionLocal
    from app.models.reading import EnergyReading, EnergyReadingHourly
    from app.models.device import Device

    async with AsyncSessionLocal() as db:
        last_hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)

        result = await db.execute(
            select(
                EnergyReading.device_id,
                func.date_trunc("hour", EnergyReading.recorded_at).label("hour_bucket"),
                func.sum(EnergyReading.energy_kwh).label("total_kwh"),
                func.avg(EnergyReading.power_kw).label("avg_power_kw"),
                func.max(EnergyReading.power_kw).label("peak_power_kw"),
                func.min(EnergyReading.power_kw).label("min_power_kw"),
                func.count(EnergyReading.id).label("reading_count"),
            )
            .where(func.date_trunc("hour", EnergyReading.recorded_at) == last_hour)
            .group_by(EnergyReading.device_id, "hour_bucket")
        )

        for row in result.all():
            rollup = EnergyReadingHourly(
                device_id=row.device_id,
                hour_bucket=row.hour_bucket,
                total_kwh=row.total_kwh,
                avg_power_kw=row.avg_power_kw,
                peak_power_kw=row.peak_power_kw,
                min_power_kw=row.min_power_kw,
                reading_count=row.reading_count,
            )
            await db.merge(rollup)

        await db.commit()


async def _daily_rollup():
    from datetime import datetime, timezone, timedelta, date
    from sqlalchemy import select, func
    from app.db.session import AsyncSessionLocal
    from app.models.reading import EnergyReading, EnergyReadingDaily

    async with AsyncSessionLocal() as db:
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()

        result = await db.execute(
            select(
                EnergyReading.device_id,
                func.sum(EnergyReading.energy_kwh).label("total_kwh"),
                func.avg(EnergyReading.power_kw).label("avg_power_kw"),
                func.max(EnergyReading.power_kw).label("peak_power_kw"),
                func.sum(func.greatest(EnergyReading.energy_kwh, 0)).label("production_kwh"),
                func.sum(func.abs(func.least(EnergyReading.energy_kwh, 0))).label("consumption_kwh"),
            )
            .where(func.date(EnergyReading.recorded_at) == yesterday)
            .group_by(EnergyReading.device_id)
        )

        for row in result.all():
            net = (row.production_kwh or 0) - (row.consumption_kwh or 0)
            rollup = EnergyReadingDaily(
                device_id=row.device_id,
                day_bucket=yesterday,
                total_kwh=row.total_kwh,
                avg_power_kw=row.avg_power_kw,
                peak_power_kw=row.peak_power_kw,
                production_kwh=row.production_kwh,
                consumption_kwh=row.consumption_kwh,
                net_kwh=net,
            )
            await db.merge(rollup)

        await db.commit()
