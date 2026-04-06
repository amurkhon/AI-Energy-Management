import time
import uuid
from starlette.types import ASGIApp, Receive, Send, Scope


class RequestIDMiddleware:
    """Pure ASGI middleware — does NOT wrap/buffer the request body."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "http":
            scope.setdefault("state", {})
            scope["state"]["request_id"] = str(uuid.uuid4())

            async def send_with_header(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append((b"x-request-id", scope["state"]["request_id"].encode()))
                    message = {**message, "headers": headers}
                await send(message)

            await self.app(scope, receive, send_with_header)
        else:
            await self.app(scope, receive, send)


class TimingMiddleware:
    """Pure ASGI middleware — does NOT wrap/buffer the request body."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "http":
            start = time.perf_counter()

            async def send_with_timing(message):
                if message["type"] == "http.response.start":
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    headers = list(message.get("headers", []))
                    headers.append((b"x-response-time", f"{elapsed_ms:.2f}ms".encode()))
                    message = {**message, "headers": headers}
                await send(message)

            await self.app(scope, receive, send_with_timing)
        else:
            await self.app(scope, receive, send)
