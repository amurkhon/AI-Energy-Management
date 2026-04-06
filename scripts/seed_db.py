"""
Seed the database with demo users, devices, and historical simulation data.
Usage: python scripts/seed_db.py
"""
import asyncio
import sys
import os
import uuid
from datetime import datetime, timezone, timedelta
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import AsyncSessionLocal, engine
from app.models import Base
from app.models.user import User, UserRole
from app.models.device import Device, DeviceGroup, DeviceType, SimProfile
from app.models.reading import EnergyReading
from app.models.alert import AlertRule, AlertMetric, AlertOperator, AlertSeverity
from app.models.simulation import SimulationSession, SimSessionStatus
from app.core.security import hash_password
from app.simulation.weather import WeatherSimulator
from app.simulation.occupancy import OccupancySimulator
from app.simulation.devices.solar_panel import SolarPanel
from app.simulation.devices.wind_turbine import WindTurbine
from app.simulation.devices.battery import Battery
from app.simulation.devices.hvac import HVAC
from app.simulation.devices.lighting import Lighting
from app.simulation.devices.ev_charger import EVCharger
from app.simulation.devices.appliance import GenericAppliance


DEMO_DEVICES = [
    {"name": "Rooftop Solar Array", "device_type": DeviceType.solar_panel, "rated_capacity": 5.0,
     "metadata_": {"panel_area_m2": 28.0, "efficiency": 0.18}},
    {"name": "Home Battery Pack", "device_type": DeviceType.battery, "rated_capacity": 5.0,
     "metadata_": {"capacity_kwh": 13.5, "charge_rate_kw": 5.0}},
    {"name": "HVAC System", "device_type": DeviceType.hvac, "rated_capacity": 3.5,
     "metadata_": {"setpoint_c": 21.0, "rated_power_kw": 3.5}},
    {"name": "Smart Lighting", "device_type": DeviceType.lighting, "rated_capacity": 0.5,
     "metadata_": {"rated_power_kw": 0.5}},
    {"name": "EV Charger", "device_type": DeviceType.ev_charger, "rated_capacity": 7.4,
     "metadata_": {"charge_power_kw": 7.4}},
    {"name": "Washing Machine", "device_type": DeviceType.appliance, "rated_capacity": 2.0,
     "metadata_": {"appliance_type": "washer"}},
    {"name": "Smart Meter", "device_type": DeviceType.smart_meter, "rated_capacity": 20.0,
     "metadata_": {}},
]

SIM_DEVICE_MAP = {
    DeviceType.solar_panel: lambda m: SolarPanel(**{k: v for k, v in m.items() if k in SolarPanel.__init__.__code__.co_varnames}),
    DeviceType.battery: lambda m: Battery(**{k: v for k, v in m.items() if k in Battery.__init__.__code__.co_varnames}),
    DeviceType.hvac: lambda m: HVAC(**{k: v for k, v in m.items() if k in HVAC.__init__.__code__.co_varnames}),
    DeviceType.lighting: lambda m: Lighting(**{k: v for k, v in m.items() if k in Lighting.__init__.__code__.co_varnames}),
    DeviceType.ev_charger: lambda m: EVCharger(**{k: v for k, v in m.items() if k in EVCharger.__init__.__code__.co_varnames}),
    DeviceType.appliance: lambda m: GenericAppliance(**{k: v for k, v in m.items() if k in GenericAppliance.__init__.__code__.co_varnames}),
}


async def seed():
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        # ── Admin user ────────────────────────────────────────────────────────
        admin = User(
            email="admin@sems.dev",
            hashed_password=hash_password("admin123"),
            full_name="Admin User",
            role=UserRole.admin,
        )
        db.add(admin)

        demo = User(
            email="demo@sems.dev",
            hashed_password=hash_password("demo123"),
            full_name="Demo User",
            role=UserRole.operator,
        )
        db.add(demo)
        await db.flush()

        # ── Device group ──────────────────────────────────────────────────────
        group = DeviceGroup(
            user_id=demo.id,
            name="Home Energy Hub",
            location="123 Demo Street",
        )
        db.add(group)
        await db.flush()

        # ── Devices ───────────────────────────────────────────────────────────
        created_devices = []
        for d in DEMO_DEVICES:
            device = Device(
                user_id=demo.id,
                group_id=group.id,
                name=d["name"],
                device_type=d["device_type"],
                rated_capacity=d["rated_capacity"],
                metadata_=d["metadata_"],
                sim_profile=SimProfile.residential,
                latitude=40.7128,
                longitude=-74.0060,
            )
            db.add(device)
            created_devices.append(device)
        await db.flush()

        # ── Alert rules ───────────────────────────────────────────────────────
        for device in created_devices:
            if device.device_type == DeviceType.battery:
                db.add(AlertRule(
                    user_id=demo.id,
                    device_id=device.id,
                    name="Battery Critical SoC",
                    metric=AlertMetric.state_of_charge,
                    operator=AlertOperator.lt,
                    threshold=15.0,
                    severity=AlertSeverity.critical,
                    cooldown_mins=30,
                ))
            elif device.device_type in (DeviceType.hvac, DeviceType.ev_charger):
                db.add(AlertRule(
                    user_id=demo.id,
                    device_id=device.id,
                    name=f"{device.name} High Consumption",
                    metric=AlertMetric.power_kw,
                    operator=AlertOperator.lt,
                    threshold=-(device.rated_capacity * 1.1),
                    severity=AlertSeverity.warning,
                    cooldown_mins=60,
                ))

        # ── Simulation session ────────────────────────────────────────────────
        sim_start = datetime.now(timezone.utc) - timedelta(days=3)
        session = SimulationSession(
            user_id=demo.id,
            name="3-Day Historical Sim",
            status=SimSessionStatus.running,
            sim_start_time=sim_start,
            sim_speed=1.0,
            tick_interval_s=300,  # 5-minute readings
            config={"device_ids": [str(d.id) for d in created_devices]},
        )
        db.add(session)
        await db.flush()

        # ── Historical readings (3 days × 5-min intervals) ────────────────────
        print("Generating 3 days of historical data (~864 ticks)...")
        weather_sim = WeatherSimulator(latitude=40.7128)
        occupancy_sim = OccupancySimulator("residential")

        sim_devices_instances = {}
        for device in created_devices:
            meta = device.metadata_ or {}
            builder = SIM_DEVICE_MAP.get(device.device_type)
            if builder:
                try:
                    sim_devices_instances[device.id] = (device, builder(meta))
                except Exception:
                    sim_devices_instances[device.id] = (device, None)

        tick_hours = 300 / 3600  # 5 min in hours
        ticks = int(3 * 24 * 60 / 5)  # 3 days of 5-min ticks = 864

        readings_batch = []
        current_time = sim_start
        battery_inst = next(
            (inst for dev, inst in sim_devices_instances.values() if isinstance(inst, Battery)), None
        )

        for _ in range(ticks):
            weather = weather_sim.get_conditions(current_time)
            occupancy = occupancy_sim.occupancy_fraction(current_time)

            net_power = 0.0
            tick_readings = {}

            for dev_id, (device, sim_dev) in sim_devices_instances.items():
                if sim_dev is None or isinstance(sim_dev, Battery):
                    continue
                try:
                    rd = sim_dev.generate_reading(
                        sim_time=current_time,
                        weather=weather,
                        occupancy=occupancy,
                        tick_hours=tick_hours,
                    )
                    net_power += rd.get("power_kw", 0)
                    tick_readings[dev_id] = rd
                except Exception:
                    pass

            if battery_inst:
                for dev_id, (device, sim_dev) in sim_devices_instances.items():
                    if isinstance(sim_dev, Battery):
                        rd = sim_dev.generate_reading(
                            sim_time=current_time,
                            weather=weather,
                            net_grid_kw=net_power,
                            tick_hours=tick_hours,
                        )
                        tick_readings[dev_id] = rd

            for device in created_devices:
                if device.id not in tick_readings:
                    continue
                rd = tick_readings[device.id]
                power_kw = rd.get("power_kw", 0)
                readings_batch.append({
                    "device_id": device.id,
                    "recorded_at": current_time,
                    "power_kw": power_kw,
                    "energy_kwh": power_kw * tick_hours,
                    "state_of_charge": rd.get("state_of_charge"),
                    "temperature_c": rd.get("temperature_c"),
                    "metadata_": {"weather": weather},
                })

            current_time += timedelta(minutes=5)

            # Batch insert every 200 readings
            if len(readings_batch) >= 200:
                db.add_all([EnergyReading(**r) for r in readings_batch])
                await db.flush()
                readings_batch.clear()
                print(f"  → {(_ + 1)} ticks processed...")

        if readings_batch:
            db.add_all([EnergyReading(**r) for r in readings_batch])
            await db.flush()

        await db.commit()
        print("\n✓ Seed complete!")
        print("  Admin:  admin@sems.dev / admin123")
        print("  Demo:   demo@sems.dev  / demo123")
        print(f"  Devices: {len(created_devices)} created")
        print(f"  Readings: ~{ticks * len(created_devices)} rows inserted")


if __name__ == "__main__":
    asyncio.run(seed())
