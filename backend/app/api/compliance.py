"""Compliance endpoints (P3.1) — privacy, deletion, audit export, RAG safety."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import AdminUser, CurrentUser
from app.core.envelope import EnvelopeRoute
from app.services.compliance_service import (
    delete_user_data,
    export_audit,
    get_privacy_policy,
    screen_content,
)
from app.services.permission_service import require_permission

router = APIRouter(tags=["compliance"], route_class=EnvelopeRoute)


@router.get("/compliance/privacy")
def privacy_policy() -> dict:
    """Public privacy policy — also linked from the login page footer."""
    return get_privacy_policy()


@router.post("/compliance/safety/screen")
def safety_screen(payload: dict, user: CurrentUser) -> dict:
    """Screen text for PII / banned words before RAG ingestion."""
    text = payload.get("text") or ""
    return screen_content(text)


@router.delete("/compliance/users/{username}")
def delete_account(
    username: str,
    admin: AdminUser,
    db: Session = Depends(get_db),
    _perm: object = Depends(require_permission("user.delete")),
) -> dict:
    """Right to deletion — cascade-delete all data owned by the user."""
    hard = True
    return delete_user_data(db, username, operator=admin.username, hard_delete_user=hard)


@router.get("/compliance/audit/export")
def audit_export(
    _u: CurrentUser,
    db: Session = Depends(get_db),
    entity: str | None = Query(default=None),
    operator: str | None = Query(default=None),
    fmt: str = Query(default="csv", pattern=r"^(csv|json)$"),
    limit: int = Query(10000, ge=1, le=100000),
    _perm: object = Depends(require_permission("audit.read")),
) -> Response:
    """Export the audit trail as CSV or JSON for compliance review."""
    result = export_audit(db, entity=entity, operator=operator, limit=limit, fmt=fmt)
    media = "text/csv" if fmt == "csv" else "application/json"
    return Response(
        content=result["content"],
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{result["filename"]}"'},
    )


@router.get("/compliance/audit/preview")
def audit_preview(
    _u: CurrentUser,
    db: Session = Depends(get_db),
    entity: str | None = Query(default=None),
    operator: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=500),
    _perm: object = Depends(require_permission("audit.read")),
) -> dict:
    """Preview the audit trail in the UI (paginated)."""
    result = export_audit(db, entity=entity, operator=operator, limit=limit, fmt="json")
    import json

    return {
        "format": "json",
        "count": result["count"],
        "items": json.loads(result["content"]),
    }
