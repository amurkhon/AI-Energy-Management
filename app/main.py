from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import HTTPException

from app.config import settings
from app.api.router import api_router
from app.api.websockets.handlers import ws_router
from app.core.exceptions import http_exception_handler, unhandled_exception_handler
from app.core.middleware import RequestIDMiddleware, TimingMiddleware
from app.cache.client import close_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown
    await close_redis()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Smart Energy Management System",
        description="SEMS backend with AI suggestions and real-time simulation",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Middleware — order matters: added last = outermost (runs first on request, last on response)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(TimingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception handlers
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # Routers
    app.include_router(api_router)
    app.include_router(ws_router)

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "1.0.0"}

    return app


app = create_app()
