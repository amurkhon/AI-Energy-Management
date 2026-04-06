from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.devices import router as devices_router, groups_router
from app.api.v1.readings import router as readings_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.alerts import router as alerts_router, rules_router
from app.api.v1.suggestions import router as suggestions_router
from app.api.v1.simulation import router as simulation_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.efficiency import router as efficiency_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(devices_router)
api_router.include_router(groups_router)
api_router.include_router(readings_router)
api_router.include_router(analytics_router)
api_router.include_router(alerts_router)
api_router.include_router(rules_router)
api_router.include_router(suggestions_router)
api_router.include_router(simulation_router)
api_router.include_router(dashboard_router)
api_router.include_router(efficiency_router)
