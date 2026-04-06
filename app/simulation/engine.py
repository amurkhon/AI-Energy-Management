import uuid
import json
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any
from app.simulation.weather import WeatherSimulator
from app.simulation.occupancy import OccupancySimulator
from app.simulation.devices.solar_panel import SolarPanel
from app.simulation.devices.wind_turbine import WindTurbine
from app.simulation.devices.battery import Battery
from app.simulation.devices.hvac import HVAC
from app.simulation.devices.lighting import Lighting
from app.simulation.devices.ev_charger import EVCharger
from app.simulation.devices.appliance import GenericAppliance
from app.simulation.devices.smart_meter import SmartMeter


DEVICE_CLASS_MAP = {
    "solar_panel": SolarPanel,
    "wind_turbine": WindTurbine,
    "battery": Battery,
    "hvac": HVAC,
    "lighting": Lighting,
    "ev_charger": EVCharger,
    "appliance": GenericAppliance,
    "smart_meter": SmartMeter,
}


def build_sim_device(device_type: str, metadata: dict | None = None) -> Any:
    """Instantiate the correct simulation class for a device type."""
    cls = DEVICE_CLASS_MAP.get(device_type)
    if not cls:
        return None
    meta = metadata or {}
    try:
        return cls(**{k: v for k, v in meta.items() if k in cls.__init__.__code__.co_varnames})
    except Exception:
        return cls()


async def run_simulation_tick(
    session_id: str,
    sim_time: datetime,
    devices: list[dict],  # list of {id, device_type, metadata_, sim_profile, latitude, longitude}
    tick_hours: float,
    redis,
    db_session,
) -> list[dict]:
    """
    Run one simulation tick.
    Returns list of reading dicts ready to be bulk-inserted into energy_readings.
    Also publishes readings to Redis pub/sub for WebSocket broadcasting.
    """
    from app.cache.keys import CHANNEL_READINGS, device_latest

    weather_sim = WeatherSimulator(latitude=devices[0].get("latitude", 40.0) if devices else 40.0)
    weather = weather_sim.get_conditions(sim_time)

    readings = []
    sim_devices: dict[str, Any] = {}

    # Build sim device instances
    for d in devices:
        sim_device = build_sim_device(d["device_type"], d.get("metadata_") or {})
        if sim_device:
            sim_devices[d["id"]] = (d, sim_device)

    # Generate readings (non-battery first, then battery uses net)
    net_power = 0.0
    device_readings = {}

    for did, (dev, sim_dev) in sim_devices.items():
        if dev["device_type"] == "battery":
            continue
        occupancy_sim = OccupancySimulator(dev.get("sim_profile", "residential"))
        occupancy = occupancy_sim.occupancy_fraction(sim_time)
        reading_data = sim_dev.generate_reading(
            sim_time=sim_time,
            weather=weather,
            occupancy=occupancy,
            tick_hours=tick_hours,
        )
        power_kw = reading_data.get("power_kw", 0)
        net_power += power_kw
        device_readings[did] = reading_data

    # Battery uses net grid power
    for did, (dev, sim_dev) in sim_devices.items():
        if dev["device_type"] == "battery":
            reading_data = sim_dev.generate_reading(
                sim_time=sim_time,
                weather=weather,
                net_grid_kw=net_power,
                tick_hours=tick_hours,
            )
            device_readings[did] = reading_data

    # Build reading records
    for dev in devices:
        did = dev["id"]
        if did not in device_readings:
            continue
        rd = device_readings[did]
        power_kw = rd.get("power_kw", 0)
        energy_kwh = power_kw * tick_hours

        reading = {
            "device_id": did,
            "recorded_at": sim_time.isoformat(),
            "power_kw": power_kw,
            "energy_kwh": energy_kwh,
            "state_of_charge": rd.get("state_of_charge"),
            "temperature_c": rd.get("temperature_c"),
            "metadata_": {"weather": weather, "sim_time": sim_time.isoformat()},
        }
        readings.append(reading)

        # Cache latest reading in Redis
        await redis.set(
            device_latest(str(did)),
            json.dumps({
                "device_id": str(did),
                "power_kw": power_kw,
                "energy_kwh": energy_kwh,
                "state_of_charge": rd.get("state_of_charge"),
                "recorded_at": sim_time.isoformat(),
            }),
            ex=3600,
        )

    # Publish to readings channel for WebSocket clients
    await redis.publish(CHANNEL_READINGS, json.dumps({
        "type": "readings",
        "session_id": session_id,
        "sim_time": sim_time.isoformat(),
        "readings": readings,
    }))

    return readings
