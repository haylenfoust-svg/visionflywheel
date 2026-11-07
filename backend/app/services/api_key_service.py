"""API Key service (P1.3) — machine-to-machine credentials for B2B integration.

Design:
  - Keys are opaque `vf_<32 hex>` strings. Only the SHA-256 hash is stored.
  - Each key carries a `scopes` list (subset of the 36 permission codes).
  - A key is bound to an owner user for audit attribution; if the user is
    deactivated, the key stops working.
  - Every use is recorded in `api_key_calls` for rate accounting + audit.

The `Depends(get_api_key_user)` dependency drops the resolved user into
`request.state` so downstream code can attribute actions to the key's
owner without changing the existing permission decorator.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import AppError, Err
from app.models.rbac import Permission
from app.models.user import User

logger = logging.getLogger(__name__)

KEY_PREFIX = "vf_"
KEY_LENGTH = 32  # hex chars


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_api_key() -> tuple[str, str]:
    """Return (plaintext_key, hash). Store only the hash."""
    raw = f"{KEY_PREFIX}{secrets.token_hex(KEY_LENGTH)}"
    return raw, _hash_key(raw)


def _validate_scopes(db: Session, scopes: list[str]) -> list[str]:
    if not scopes:
        return []
    known = {p.code for p in db.query(Permission).all()}
    unknown = [s for s in scopes if s not in known]
    if unknown:
        raise AppError(Err.VALIDATION, f"unknown permission codes: {unknown}", 400)
    return scopes


class ApiKeyService:
    """Create / list / revoke API keys, verify inbound keys."""

    @staticmethod
    def create_key(
        db: Session,
        *,
        name: str,
        owner_user_id: int,
        scopes: list[str] | None = None,
        expires_at: float | None = None,
    ) -> dict[str, Any]:
        from app.models.api_key import ApiKey

        scopes = _validate_scopes(db, scopes or [])
        raw, key_hash = generate_api_key()
        row = ApiKey(
            name=name,
            key_hash=key_hash,
            owner_user_id=owner_user_id,
            scopes=",".join(scopes),
            expires_at=expires_at,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {
            "id": row.id,
            "name": row.name,
            "key": raw,  # shown once
            "scopes": scopes,
            "expires_at": expires_at,
        }

    @staticmethod
    def list_keys(db: Session, owner_user_id: int | None = None) -> list[dict[str, Any]]:
        from app.models.api_key import ApiKey

        q = db.query(ApiKey).filter(ApiKey.revoked_at.is_(None))
        if owner_user_id is not None:
            q = q.filter(ApiKey.owner_user_id == owner_user_id)
        rows = q.order_by(ApiKey.id.desc()).all()
        return [
            {
                "id": r.id,
                "name": r.name,
                "key_hint": r.key_hint,
                "owner_user_id": r.owner_user_id,
                "scopes": r.scope_list,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "expires_at": r.expires_at,
                "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
                "call_count": r.call_count,
            }
            for r in rows
        ]

    @staticmethod
    def revoke_key(db: Session, key_id: int) -> dict[str, Any]:
        from app.models.api_key import ApiKey

        row = db.query(ApiKey).filter(ApiKey.id == key_id).first()
        if row is None:
            raise AppError(Err.NOT_FOUND, f"API key not found: {key_id}", 404)
        if row.revoked_at is not None:
            raise AppError(Err.CONFLICT, "API key is already revoked", 409)
        from datetime import datetime, timezone

        row.revoked_at = datetime.now(timezone.utc)
        db.commit()
        return {"id": row.id, "revoked": True}

    @staticmethod
    def verify_key(db: Session, raw_key: str) -> dict[str, Any]:
        """Resolve a plaintext key to its owner + scopes. Raises 401 on failure."""
        import time

        from app.models.api_key import ApiKey

        key_hash = _hash_key(raw_key)
        row = db.query(ApiKey).filter(ApiKey.key_hash == key_hash).first()
        if row is None:
            raise AppError(Err.TOKEN_INVALID, "invalid API key", 401)
        if row.revoked_at is not None:
            raise AppError(Err.TOKEN_INVALID, "API key revoked", 401)
        if row.expires_at is not None and row.expires_at < time.time():
            raise AppError(Err.TOKEN_EXPIRED, "API key expired", 401)
        owner = db.query(User).filter(User.id == row.owner_user_id).first()
        if owner is None or not owner.is_active:
            raise AppError(Err.TOKEN_INVALID, "API key owner disabled", 401)
        row.call_count = (row.call_count or 0) + 1
        from datetime import datetime, timezone
        row.last_used_at = datetime.now(timezone.utc)
        db.commit()
        return {"key_id": row.id, "owner": owner, "scopes": row.scope_list}
