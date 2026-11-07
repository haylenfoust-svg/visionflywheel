"""Aggregate API router — mount all sub-routers here."""

from fastapi import APIRouter

from app.api import (
    api_keys,
    auth,
    batch,
    chat,
    compliance,
    corrections,
    dataset,
    p2,
    rbac,
    security,
    stats,
    system,
    tasks,
)
from app.core.envelope import EnvelopeRoute

api_router = APIRouter(prefix="/api", route_class=EnvelopeRoute)
api_router.include_router(auth.router)
api_router.include_router(security.router)
api_router.include_router(system.router)
api_router.include_router(tasks.router)
api_router.include_router(batch.router)
api_router.include_router(corrections.router)
api_router.include_router(dataset.router)
api_router.include_router(stats.router)
api_router.include_router(chat.router)
api_router.include_router(rbac.router)
api_router.include_router(api_keys.router)
api_router.include_router(p2.router)
api_router.include_router(compliance.router)
