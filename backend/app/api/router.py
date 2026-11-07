"""Aggregate API router — mount all sub-routers here."""

from fastapi import APIRouter

from app.api import auth, corrections, system, tasks
from app.core.envelope import EnvelopeRoute

api_router = APIRouter(prefix="/api", route_class=EnvelopeRoute)
api_router.include_router(auth.router)
api_router.include_router(system.router)
api_router.include_router(tasks.router)
api_router.include_router(corrections.router)
