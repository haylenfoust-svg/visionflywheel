"""Dashboard / Admin statistics endpoints (M5.2)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import AdminUser, CurrentUser
from app.core.envelope import EnvelopeRoute
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.auth import UserOut
from app.schemas.config import AuditOut
from app.services import stats_service
from app.services.permission_service import require_permission
from app.services.quality_service import quality_metrics

router = APIRouter(tags=["stats"], route_class=EnvelopeRoute)


@router.get("/stats/overview")
def overview(user: CurrentUser, db: Session = Depends(get_db), _perm: object = Depends(require_permission("task.read"))) -> dict:
    return stats_service.dashboard_overview(db)


@router.get("/stats/quality")
def quality(
    user: CurrentUser,
    db: Session = Depends(get_db),
    days: int = 30,
    _perm: object = Depends(require_permission("detection.read")),
) -> dict:
    """Flywheel quality metrics: FP rate, miss proxy, correction rate, trend."""
    return quality_metrics(db, user, days=days)


@router.get("/stats/health-detail")
def health_detail(user: CurrentUser, db: Session = Depends(get_db), _perm: object = Depends(require_permission("system.admin"))) -> dict:
    """Richer health info for the admin panel."""
    from app.core.config import get_settings
    from app.services.detector_factory import detector_mode, get_detector

    settings = get_settings()
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    detector = get_detector()
    return {
        "app": settings.app_name,
        "version": settings.version,
        "db": db_status,
        "detector_mode": detector_mode(),
        "detector_available": detector.available,
        "fallback_enabled": settings.enable_fallback_detector,
        "database_url_scheme": settings.database_url.split("://")[0],
        "user_count": db.query(User).count(),
    }


# ---------- Admin-only: audit log ----------
@router.get("/admin/audit", response_model=list[AuditOut])
def admin_audit(
    _: AdminUser,
    db: Session = Depends(get_db),
    entity: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=1000),
) -> list[AuditOut]:
    q = db.query(AuditLog)
    if entity:
        q = q.filter(AuditLog.entity == entity)
    rows = q.order_by(AuditLog.id.desc()).limit(limit).all()
    return [AuditOut.model_validate(r) for r in rows]


@router.get("/admin/users", response_model=list[UserOut])
def admin_users(_: AdminUser, db: Session = Depends(get_db)) -> list[UserOut]:
    return [UserOut.model_validate(u) for u in db.query(User).order_by(User.id).all()]
