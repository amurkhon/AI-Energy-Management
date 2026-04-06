from celery import Celery
from celery.schedules import crontab
from app.config import settings

celery_app = Celery(
    "sems",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.simulation_tasks",
        "app.tasks.ai_tasks",
        "app.tasks.alert_tasks",
        "app.tasks.analytics_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)

celery_app.conf.beat_schedule = {
    "simulation-tick": {
        "task": "app.tasks.simulation_tasks.run_all_active_sessions",
        "schedule": settings.sim_tick_interval_seconds,
    },
    "ai-suggestions": {
        "task": "app.tasks.ai_tasks.run_ai_for_all_users",
        "schedule": settings.ai_suggestion_interval_minutes * 60,
    },
    "alert-scan": {
        "task": "app.tasks.alert_tasks.evaluate_all_alert_rules",
        "schedule": settings.ai_anomaly_scan_interval_minutes * 60,
    },
    "hourly-rollup": {
        "task": "app.tasks.analytics_tasks.hourly_rollup",
        "schedule": crontab(minute=5),  # 5 minutes past each hour
    },
    "daily-rollup": {
        "task": "app.tasks.analytics_tasks.daily_rollup",
        "schedule": crontab(hour=0, minute=10),  # 00:10 UTC daily
    },
}
