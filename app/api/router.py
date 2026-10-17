"""Root API router: every feature router is registered here, and main.py includes only this one."""

from fastapi import APIRouter

from app.api.user.user import router as user_router

api_router = APIRouter(prefix="/portfolio/v1", tags=["portfolio"])
api_router.include_router(user_router)
