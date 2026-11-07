"""System endpoints: health, info, config (docs/API.md §9, §12)."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import AdminUser, CurrentUser
from app.core.envelope import EnvelopeRoute
from app.models.audit import AuditLog
from app.schemas.config import (
    AuditOut,
    ConfigMapOut,
    ConfigUpdate,
    ConfigValueOut,
    HealthOut,
    SystemInfoOut,
)
from app.services.config_service import get_config_service

router = APIRouter(tags=["system"], route_class=EnvelopeRoute)


@router.get("/system/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)) -> HealthOut:
    settings = get_settings()
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"
    return HealthOut(
        status="healthy" if db_status == "ok" else "degraded",
        version=settings.version,
        detector_mode="yolo",  # M2 起由 yolo_service 决定
        db=db_status,
    )


@router.get("/system/info", response_model=SystemInfoOut)
def info(user: CurrentUser, db: Session = Depends(get_db)) -> SystemInfoOut:
    settings = get_settings()
    cfg = get_config_service()
    weight_id = cfg.get(db, "default_weight_id")
    return SystemInfoOut(
        version=settings.version,
        detector_mode="yolo",
        default_weight_id=weight_id if isinstance(weight_id, int) else None,
        enable_fallback_detector=bool(cfg.get(db, "enable_fallback_detector")),
        role=user.role,
    )


@router.get("/config", response_model=ConfigMapOut)
def read_config(_: CurrentUser, db: Session = Depends(get_db)) -> ConfigMapOut:
    snapshot = get_config_service().snapshot(db)
    values = {k: ConfigValueOut(**v) for k, v in snapshot.items()}
    return ConfigMapOut(values=values)


@router.put("/config/{key}", response_model=ConfigValueOut)
def write_config(key: str, payload: ConfigUpdate, admin: AdminUser, db: Session = Depends(get_db)) -> ConfigValueOut:
    result = get_config_service().set(db, key, payload.value, operator=admin.username, note=payload.note)
    return ConfigValueOut(value=result["value"], source=result["source"], default=get_config_service()._read_default(key))


@router.delete("/config/{key}", response_model=ConfigValueOut)
def reset_config(key: str, admin: AdminUser, db: Session = Depends(get_db)) -> ConfigValueOut:
    result = get_config_service().reset(db, key, operator=admin.username)
    return ConfigValueOut(value=result["value"], source=result["source"], default=get_config_service()._read_default(key))


@router.get("/config/audit", response_model=list[AuditOut])
def config_audit(_: AdminUser, db: Session = Depends(get_db), limit: int = 100) -> list[AuditOut]:
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.entity == "config")
        .order_by(AuditLog.id.desc())
        .limit(min(limit, 500))
        .all()
    )
    return [AuditOut.model_validate(r) for r in rows]
