"""API Key management endpoints (P1.3) — machine-to-machine credentials."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import AdminUser
from app.core.envelope import EnvelopeRoute
from app.services.api_key_service import ApiKeyService
from app.services.permission_service import require_permission

router = APIRouter(tags=["api-keys"], route_class=EnvelopeRoute)


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    scopes: list[str] = Field(default_factory=list)
    expires_at: float | None = Field(default=None, description="unix timestamp (optional)")


@router.post("/api-keys", status_code=201)
def create_key(
    payload: ApiKeyCreate,
    admin: AdminUser,
    db: Session = Depends(get_db),
    _perm: object = Depends(require_permission("system.admin")),
) -> dict:
    """Create an API key. The plaintext key is returned ONCE — store it safely."""
    return ApiKeyService.create_key(
        db,
        name=payload.name,
        owner_user_id=admin.id,
        scopes=payload.scopes,
        expires_at=payload.expires_at,
    )


@router.get("/api-keys")
def list_keys(
    admin: AdminUser,
    db: Session = Depends(get_db),
    _perm: object = Depends(require_permission("system.admin")),
) -> list[dict]:
    return ApiKeyService.list_keys(db)


@router.post("/api-keys/{key_id}/revoke")
def revoke_key(
    key_id: int,
    admin: AdminUser,
    db: Session = Depends(get_db),
    _perm: object = Depends(require_permission("system.admin")),
) -> dict:
    return ApiKeyService.revoke_key(db, key_id)


@router.get("/api-keys/verify")
def verify_key(
    key: str,
    db: Session = Depends(get_db),
) -> dict:
    """Introspect an API key — useful for clients to validate their credential."""
    result = ApiKeyService.verify_key(db, key)
    return {
        "valid": True,
        "key_id": result["key_id"],
        "owner": result["owner"].username,
        "scopes": result["scopes"],
    }
