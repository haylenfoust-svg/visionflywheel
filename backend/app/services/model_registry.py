"""Model version comparison & rollback (AI-1).

Compares two weight entries on their recorded training metadata
(holdout_map, class_count, dataset_version, training time) and exposes
a one-click rollback to any previously-registered checkpoint.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import AppError, Err
from app.models.weight import Weight
from app.services import weight_manager


def _weight_snapshot(w: Weight) -> dict[str, Any]:
    return {
        "id": w.id,
        "filename": w.filename,
        "source": w.source,
        "dataset_version": w.dataset_version,
        "holdout_map": w.holdout_map,
        "class_count": w.class_count,
        "note": w.note,
        "is_default": w.is_default,
        "created_at": w.created_at.isoformat() if w.created_at else None,
        "path": w.path,
    }


def compare_weights(db: Session, base_id: int, target_id: int) -> dict[str, Any]:
    """Side-by-side comparison of two registered weights."""
    base = db.query(Weight).filter(Weight.id == base_id).first()
    target = db.query(Weight).filter(Weight.id == target_id).first()
    if base is None:
        raise AppError(Err.NOT_FOUND, f"base weight not found: {base_id}", 404)
    if target is None:
        raise AppError(Err.NOT_FOUND, f"target weight not found: {target_id}", 404)

    base_map = base.holdout_map
    target_map = target.holdout_map
    delta_map = (
        round(target_map - base_map, 4) if (base_map is not None and target_map is not None) else None
    )

    return {
        "base": _weight_snapshot(base),
        "target": _weight_snapshot(target),
        "delta": {
            "holdout_map": delta_map,
            "improved": (delta_map is not None and delta_map > 0),
            "regressed": (delta_map is not None and delta_map < 0),
            "same_dataset": base.dataset_version == target.dataset_version,
            "same_classes": base.class_count == target.class_count,
        },
    }


def list_weight_history(db: Session, *, limit: int = 50) -> list[dict[str, Any]]:
    """All registered weights, newest first — supports the rollback picker."""
    rows = (
        db.query(Weight)
        .order_by(Weight.is_default.desc(), Weight.id.desc())
        .limit(limit)
        .all()
    )
    return [_weight_snapshot(w) for w in rows]


def rollback_to(db: Session, weight_id: int, *, operator: str | None = None) -> dict[str, Any]:
    """Set a previously-registered weight as the new default (hot-swap)."""
    result = weight_manager.set_default(db, weight_id, operator=operator)
    w = db.query(Weight).filter(Weight.id == weight_id).first()
    result["dataset_version"] = w.dataset_version if w else None
    result["holdout_map"] = w.holdout_map if w else None
    result["rolled_back"] = True
    return result


def training_summary(db: Session, weight_id: int) -> dict[str, Any]:
    """Best-effort training context for a weight (used in the compare UI)."""
    from app.models.dataset import TrainingRun

    w = db.query(Weight).filter(Weight.id == weight_id).first()
    if w is None:
        raise AppError(Err.NOT_FOUND, f"weight not found: {weight_id}", 404)

    runs = []
    if w.dataset_version:
        rows = (
            db.query(TrainingRun)
            .filter(TrainingRun.dataset_version == w.dataset_version)
            .order_by(TrainingRun.id.desc())
            .limit(5)
            .all()
        )
        runs = [
            {
                "id": r.id,
                "status": r.status,
                "epochs": r.epochs,
                "imgsz": r.imgsz,
                "batch": r.batch,
                "holdout_map": r.holdout_map,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    return {
        "weight": _weight_snapshot(w),
        "training_runs": runs,
    }
