import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.api.websockets.manager import manager
from app.cache.client import get_redis
from app.cache.keys import CHANNEL_READINGS, CHANNEL_ALERTS, CHANNEL_SIM

ws_router = APIRouter()


@ws_router.websocket("/ws/realtime")
async def ws_realtime(websocket: WebSocket):
    await manager.connect(websocket, "realtime")
    redis = await get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(CHANNEL_READINGS)
    try:
        while True:
            # Handle client control messages (subscribe/unsubscribe/ping)
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=0.05)
                msg = json.loads(raw)
                action = msg.get("action")
                if action == "subscribe":
                    manager.subscribe(websocket, msg.get("device_ids", []))
                elif action == "unsubscribe":
                    manager.unsubscribe(websocket, msg.get("device_ids", []))
                elif action == "ping":
                    await manager.send_personal(websocket, {"type": "pong"})
            except asyncio.TimeoutError:
                pass
            except Exception:
                break

            # Forward any Redis pub/sub messages to this client
            message = await pubsub.get_message(ignore_subscribe_messages=True)
            if message and message.get("type") == "message":
                try:
                    data = json.loads(message["data"])
                    # Filter by device subscription if the client subscribed to specific devices
                    subs = manager._subscriptions.get(websocket, set())
                    if subs:
                        readings = data.get("readings", [])
                        filtered = [r for r in readings if r.get("device_id") in subs]
                        if filtered:
                            await manager.send_personal(websocket, {**data, "readings": filtered})
                    else:
                        await manager.send_personal(websocket, data)
                except Exception:
                    pass

            await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(CHANNEL_READINGS)
        await pubsub.aclose()
        manager.disconnect(websocket, "realtime")


@ws_router.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket):
    await manager.connect(websocket, "alerts")
    redis = await get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(CHANNEL_ALERTS)
    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=0.05)
                msg = json.loads(raw)
                if msg.get("action") == "ping":
                    await manager.send_personal(websocket, {"type": "pong"})
            except asyncio.TimeoutError:
                pass
            except Exception:
                break

            message = await pubsub.get_message(ignore_subscribe_messages=True)
            if message and message.get("type") == "message":
                try:
                    data = json.loads(message["data"])
                    await manager.send_personal(websocket, data)
                except Exception:
                    pass

            await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(CHANNEL_ALERTS)
        await pubsub.aclose()
        manager.disconnect(websocket, "alerts")


@ws_router.websocket("/ws/simulation")
async def ws_simulation(websocket: WebSocket):
    await manager.connect(websocket, "simulation")
    redis = await get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(CHANNEL_SIM)
    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=0.05)
                msg = json.loads(raw)
                if msg.get("action") == "ping":
                    await manager.send_personal(websocket, {"type": "pong"})
            except asyncio.TimeoutError:
                pass
            except Exception:
                break

            message = await pubsub.get_message(ignore_subscribe_messages=True)
            if message and message.get("type") == "message":
                try:
                    data = json.loads(message["data"])
                    await manager.send_personal(websocket, data)
                except Exception:
                    pass

            await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(CHANNEL_SIM)
        await pubsub.aclose()
        manager.disconnect(websocket, "simulation")
