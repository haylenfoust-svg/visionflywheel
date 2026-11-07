"""Weight registry + hot-swap (PRD FR-6.5).

`hot_swap` reloads the active detector without restarting the process.
The `weights` table records provenance (`source`, `dataset_version`,
`holdout_map`) so we can trace a checkpoint back to its training data.
"""

from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AppError, Err
from app.models.weight import Weight

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".pt", ".onnx", ".engine"}


def list_weights(db: Session) -> list[Weight]:
    return db.query(Weight).order_by(Weight.is_default.desc(), Weight.id.desc()).all()


def get_weight(db: Session, weight_id: int) -> Weight:
    row = db.query(Weight).filter(Weight.id == weight_id).first()
    if row is None:
        raise AppError(Err.NOT_FOUND, f"weight not found: {weight_id}", 404)
    return row


def scan_weights_dir(db: Session) -> list[Weight]:
    """Register any `*.pt` sitting in backend/weights but not yet in the DB."""
    settings = get_settings()
    weights_dir = Path(settings.weights_dir)
    if not weights_dir.exists():
        return []
    known_paths = {w.path for w in db.query(Weight).all()}
    registered: list[Weight] = []
    for path in sorted(weights_dir.glob("*.pt")):
        rel = str(path)
        if rel in known_paths:
            continue
        row = Weight(
            filename=path.name,
            path=rel,
            is_default=False,
            source="manual",
            note="auto-registered from weights dir",
        )
        db.add(row)
        registered.append(row)
    if registered:
        db.commit()
        for row in registered:
            db.refresh(row)
    return registered


def upload_weight(
    db: Session,
    *,
    filename: str,
    content: bytes,
    operator: str | None = None,
    note: str | None = None,
) -> Weight:
    settings = get_settings()
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise AppError(Err.UNSUPPORTED_FILE, f"unsupported weight type: {suffix}", 400)
    if len(content) < 1024:
        raise AppError(Err.VALIDATION, "weight file is suspiciously small", 400)

    weights_dir = Path(settings.weights_dir)
    weights_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex[:8]}_{Path(filename).name}"
    target = weights_dir / safe_name
    target.write_bytes(content)

    row = Weight(
        filename=safe_name,
        path=str(target),
        is_default=False,
        source="manual",
        note=note,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("weight uploaded: %s by %s", safe_name, operator)
    return row


def set_default(db: Session, weight_id: int, *, operator: str | None = None) -> dict:
    """Hot-swap the default weight (FR-6.5: no restart, no code change)."""
    row = get_weight(db, weight_id)
    if not Path(row.path).is_file():
        raise AppError(Err.NOT_FOUND, f"weight file missing on disk: {row.path}", 404)

    # Demote the current default
    current = db.query(Weight).filter(Weight.is_default.is_(True)).all()
    for w in current:
        w.is_default = False
    row.is_default = True
    db.commit()
    db.refresh(row)

    # Trigger the detector hot reload (no restart)
    reload_ms = 0.0
    try:
        import time

        from app.services.detector_factory import reload_detector

        started = time.perf_counter()
        reload_detector(row.path)
        reload_ms = (time.perf_counter() - started) * 1000.0
    except Exception:
        logger.exception("detector reload failed; keeping previous weights")

    return {
        "weight_id": row.id,
        "filename": row.filename,
        "is_default": True,
        "reloaded_in_ms": round(reload_ms, 1),
        "requires_restart": False,
    }


def delete_weight(db: Session, weight_id: int) -> None:
    row = get_weight(db, weight_id)
    if row.is_default:
        raise AppError(Err.CONFLICT, "cannot delete the default weight", 409)
    path = Path(row.path)
    if path.is_file():
        path.unlink()
    db.delete(row)
    db.commit()


def register_trained(
    db: Session,
    *,
    filename: str,
    source_path: str,
    dataset_version: str,
    holdout_map: float | None = None,
    class_count: int | None = None,
    operator: str | None = None,
) -> Weight:
    """Register a freshly trained checkpoint (called from train_service)."""
    settings = get_settings()
    weights_dir = Path(settings.weights_dir)
    weights_dir.mkdir(parents=True, exist_ok=True)
    target = weights_dir / filename
    src = Path(source_path)
    if src.resolve() != target.resolve():
        shutil.copy2(src, target)

    row = Weight(
        filename=filename,
        path=str(target),
        is_default=False,
        source="trained",
        dataset_version=dataset_version,
        holdout_map=holdout_map,
        class_count=class_count,
        note=f"trained from {dataset_version}",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
