"""Centralized Redis key constants."""


def device_latest(device_id: str) -> str:
    return f"device:latest:{device_id}"


def device_status(device_id: str) -> str:
    return f"device:status:{device_id}"


def user_refresh_token(user_id: str) -> str:
    return f"auth:refresh:{user_id}"


def blacklisted_token(jti: str) -> str:
    return f"auth:blacklist:{jti}"


def sim_session_state(session_id: str) -> str:
    return f"sim:session:{session_id}"


def dashboard_cache(user_id: str) -> str:
    return f"dashboard:{user_id}"


CHANNEL_READINGS = "channel:readings"
CHANNEL_ALERTS = "channel:alerts"
CHANNEL_SIM = "channel:simulation"
