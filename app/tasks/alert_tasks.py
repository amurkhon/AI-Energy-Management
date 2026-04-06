import asyncio
import json
from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.alert_tasks.evaluate_all_alert_rules")
def evaluate_all_alert_rules():
    asyncio.run(_evaluate_all_rules())


async def _evaluate_all_rules():
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select, and_
    from app.db.session import AsyncSessionLocal
    from app.cache.client import get_redis
    from app.cache.keys import device_latest, CHANNEL_ALERTS
    from app.models.alert import AlertRule, AlertEvent, AlertOperator
    from app.models.reading import EnergyReading
    from app.api.websockets.manager import manager

    OPERATORS = {
        "gt": lambda a, b: a > b,
        "lt": lambda a, b: a < b,
        "gte": lambda a, b: a >= b,
        "lte": lambda a, b: a <= b,
        "eq": lambda a, b: abs(a - b) < 0.001,
    }

    async with AsyncSessionLocal() as db:
        redis = await get_redis()
        rules_res = await db.execute(select(AlertRule).where(AlertRule.is_active == True))
        rules = rules_res.scalars().all()

        for rule in rules:
            # Check cooldown
            cooldown_since = datetime.now(timezone.utc) - timedelta(minutes=rule.cooldown_mins)
            recent_event = await db.execute(
                select(AlertEvent).where(
                    AlertEvent.rule_id == rule.id,
                    AlertEvent.triggered_at >= cooldown_since,
                ).limit(1)
            )
            if recent_event.scalar_one_or_none():
                continue

            # Get device IDs to check
            if rule.device_id:
                device_ids = [str(rule.device_id)]
            else:
                from app.models.device import Device
                res = await db.execute(select(Device.id).where(Device.user_id == rule.user_id, Device.is_active == True))
                device_ids = [str(d) for d in res.scalars()]

            metric_field = rule.metric.value  # e.g. "power_kw"
            op_fn = OPERATORS.get(rule.operator.value, lambda a, b: False)

            for did in device_ids:
                cached = await redis.get(device_latest(did))
                if not cached:
                    continue
                data = json.loads(cached)
                actual = data.get(metric_field)
                if actual is None:
                    continue

                if op_fn(actual, rule.threshold):
                    event = AlertEvent(
                        rule_id=rule.id,
                        device_id=rule.device_id or did,
                        severity=rule.severity,
                        actual_value=actual,
                        threshold_value=rule.threshold,
                        message=f"{rule.name}: {metric_field}={actual:.3f} {rule.operator.value} {rule.threshold}",
                    )
                    db.add(event)
                    await db.flush()

                    # Push to WebSocket clients
                    event_data = {
                        "type": "alert",
                        "data": {
                            "id": str(event.id),
                            "device_id": did,
                            "severity": rule.severity.value,
                            "message": event.message,
                            "triggered_at": event.triggered_at.isoformat(),
                        },
                    }
                    await manager.broadcast("alerts", event_data)
                    await redis.publish(CHANNEL_ALERTS, json.dumps(event_data))

        await db.commit()
