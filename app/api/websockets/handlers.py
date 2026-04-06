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
    try:
        while True:
            # Listen for client subscription messages (non-blocking)
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
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

            # Forward any queued Redis pub/sub messages
            await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, "realtime")


@ws_router.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket):
    await manager.connect(websocket, "alerts")
    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                msg = json.loads(raw)
                if msg.get("action") == "ping":
                    await manager.send_personal(websocket, {"type": "pong"})
            except asyncio.TimeoutError:
                pass
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, "alerts")


@ws_router.websocket("/ws/simulation")
async def ws_simulation(websocket: WebSocket):
    await manager.connect(websocket, "simulation")
    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                msg = json.loads(raw)
                if msg.get("action") == "ping":
                    await manager.send_personal(websocket, {"type": "pong"})
            except asyncio.TimeoutError:
                pass
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, "simulation")
