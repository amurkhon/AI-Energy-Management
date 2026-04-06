import asyncio
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        # Maps channel_name -> set of websockets
        self._channels: dict[str, set[WebSocket]] = {}
        # Maps websocket -> set of subscribed device_ids
        self._subscriptions: dict[WebSocket, set[str]] = {}

    async def connect(self, websocket: WebSocket, channel: str):
        await websocket.accept()
        if channel not in self._channels:
            self._channels[channel] = set()
        self._channels[channel].add(websocket)
        self._subscriptions[websocket] = set()

    def disconnect(self, websocket: WebSocket, channel: str):
        self._channels.get(channel, set()).discard(websocket)
        self._subscriptions.pop(websocket, None)

    def subscribe(self, websocket: WebSocket, device_ids: list[str]):
        if websocket in self._subscriptions:
            self._subscriptions[websocket].update(device_ids)

    def unsubscribe(self, websocket: WebSocket, device_ids: list[str]):
        if websocket in self._subscriptions:
            self._subscriptions[websocket].difference_update(device_ids)

    async def broadcast(self, channel: str, message: dict, device_id: str | None = None):
        """Broadcast to all clients in channel (optionally filtered by device subscription)."""
        dead = set()
        for ws in list(self._channels.get(channel, set())):
            if device_id:
                subs = self._subscriptions.get(ws, set())
                if subs and device_id not in subs:
                    continue
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.disconnect(ws, channel)

    async def send_personal(self, websocket: WebSocket, message: dict):
        try:
            await websocket.send_json(message)
        except Exception:
            pass


manager = ConnectionManager()
