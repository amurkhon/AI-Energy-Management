from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_env: str = "development"
    app_secret_key: str = "dev-secret-key-change-in-production"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # Database
    database_url: str = "postgresql+asyncpg://zem@localhost:5432/energy_db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # Simulation
    sim_tick_interval_seconds: int = 60
    sim_default_speed: float = 1.0

    # AI
    ai_suggestion_interval_minutes: int = 5
    ai_anomaly_scan_interval_minutes: int = 1
    ai_retrain_interval_days: int = 7

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
