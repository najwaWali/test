from fastapi import APIRouter

from app.api.controllers.health import router as health_router
from app.api.controllers.tickets import router as tickets_router

router = APIRouter()

router.include_router(health_router, tags=["health"])
router.include_router(tickets_router)
