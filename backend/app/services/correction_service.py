"""Correction service — the flywheel's power source (PRD FR-3).

Every user action on a detection is recorded in `corrections` as an
**append-only** row (FR-3.7). `Detection` is updated in place so downstream
consumers (export, training) see the current effective state.

Undo (FR-3.6) is modelled as its own append-only row (`action='undo'`,
`undo_of=<id>`) that reverts the `Detection` to the pre-action snapshot.
The original correction stays in the log for audit.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.core.exceptions import AppError, Err
from app.models.correction import ACTIONS, Correction
from app.models.detection import Detection
from app.models.task import Task
from app.schemas.correction import BBox, CorrectionBatchItem, CorrectionCreate

logger = logging.getLogger(__name__)


def _dump(value) -> str | None:
    return None if value is None else json.dumps(value, ensure_ascii=False)


def _load(value: str | None):
    return None if value is None else json.loads(value)


def _snapshot_detection(det: Detection) -> dict:
    return {
        "class_id": det.class_id,
        "class_name": det.class_name,
        "class_name_zh": det.class_name_zh,
        "confidence": det.confidence,
        "bbox": {"x1": det.x1, "y1": det.y1, "x2": det.x2, "y2": det.y2},
        "status": det.status,
        "source": det.source,
    }


def _apply_snapshot(det: Detection, snap: dict) -> None:
    det.class_id = snap["class_id"]
    det.class_name = snap["class_name"]
    det.class_name_zh = snap.get("class_name_zh")
    det.confidence = snap["confidence"]
    bbox = snap["bbox"]
    det.x1 = float(bbox["x1"])
    det.y1 = float(bbox["y1"])
    det.x2 = float(bbox["x2"])
    det.y2 = float(bbox["y2"])
    det.status = snap["status"]
    det.source = snap["source"]


def _validate_bbox(bbox: BBox) -> None:
    if bbox.x2 <= bbox.x1 or bbox.y2 <= bbox.y1:
        raise AppError(Err.CORRECTION_INVALID, "bbox must have positive area", 422)
    if min(bbox.x1, bbox.y1) < 0:
        raise AppError(Err.CORRECTION_INVALID, "bbox coordinates must be non-negative", 422)


def apply_correction(
    db: Session,
    payload: CorrectionCreate,
    *,
    operator: str | None = None,
) -> Correction:
    """Apply one correction. Raises AppError on invalid input / state."""
    action = payload.action
    if action not in ACTIONS:
        raise AppError(Err.CORRECTION_INVALID, f"unknown action: {action}", 422)

    if action == "undo":
        return undo_correction(db, target_id=payload.undo_of, operator=operator, comment=payload.comment)

    # Resolve the target detection (except for action='add')
    detection: Detection | None = None
    if action != "add":
        if not payload.detection_id:
            raise AppError(Err.CORRECTION_INVALID, f"detection_id is required for action={action}", 422)
        detection = db.query(Detection).filter(Detection.id == payload.detection_id).first()
        if detection is None:
            raise AppError(Err.NOT_FOUND, f"detection not found: {payload.detection_id}", 404)

    # Build the before/after snapshots
    old_snapshot: dict | None = _snapshot_detection(detection) if detection is not None else None
    new_snapshot: dict | None = None

    if action == "confirm":
        if detection is not None and detection.status == "corrected":
            raise AppError(Err.CONFLICT, "detection already confirmed", 409)
        detection.status = "corrected"
        new_snapshot = _snapshot_detection(detection)

    elif action == "relabel":
        if not payload.new_class_name:
            raise AppError(Err.CORRECTION_INVALID, "new_class_name is required for action=relabel", 422)
        detection.class_name = payload.new_class_name
        detection.class_name_zh = payload.new_class_name  # already a display name from UI
        detection.status = "corrected"
        new_snapshot = _snapshot_detection(detection)

    elif action == "false_positive":
        detection.status = "rejected"
        new_snapshot = _snapshot_detection(detection)

    elif action == "adjust":
        if payload.new_bbox is None:
            raise AppError(Err.CORRECTION_INVALID, "new_bbox is required for action=adjust", 422)
        _validate_bbox(payload.new_bbox)
        detection.x1 = payload.new_bbox.x1
        detection.y1 = payload.new_bbox.y1
        detection.x2 = payload.new_bbox.x2
        detection.y2 = payload.new_bbox.y2
        detection.status = "corrected"
        new_snapshot = _snapshot_detection(detection)

    elif action == "add":
        if payload.task_id is None:
            raise AppError(Err.CORRECTION_INVALID, "task_id is required for action=add", 422)
        if payload.new_bbox is None:
            raise AppError(Err.CORRECTION_INVALID, "new_bbox is required for action=add", 422)
        if not payload.new_class_name:
            raise AppError(Err.CORRECTION_INVALID, "new_class_name is required for action=add", 422)
        _validate_bbox(payload.new_bbox)

        task = db.query(Task).filter(Task.id == payload.task_id).first()
        if task is None:
            raise AppError(Err.NOT_FOUND, f"task not found: {payload.task_id}", 404)

        # Anchor the new box to the image path. Prefer an existing detection's
        # image (which also carries item_index), else fall back to task.meta.
        anchor = task.detections[0] if task.detections else None
        if anchor is not None:
            image_rel = anchor.image_path
            result_rel = anchor.result_path
            item_index = anchor.item_index
            class_id = anchor.class_id
        else:
            meta = task.meta or {}
            image_rel = meta.get("image_path")
            result_rel = meta.get("result_path")
            if not image_rel:
                raise AppError(Err.CORRECTION_INVALID, "task has no image to anchor an add", 422)
            item_index = 0
            class_id = 0

        detection = Detection(
            task_id=payload.task_id,
            item_index=item_index,
            image_path=image_rel,
            result_path=result_rel,
            class_id=class_id,
            class_name=payload.new_class_name,
            class_name_zh=payload.new_class_name,
            confidence=1.0,
            x1=payload.new_bbox.x1,
            y1=payload.new_bbox.y1,
            x2=payload.new_bbox.x2,
            y2=payload.new_bbox.y2,
            status="corrected",
            source="manual",
        )
        db.add(detection)
        db.flush()  # assign id
        new_snapshot = _snapshot_detection(detection)

    # Persist the audit row (append-only)
    correction = Correction(
        detection_id=detection.id if detection is not None else None,
        task_id=detection.task_id if detection is not None else payload.task_id,
        action=action,
        old_value=_dump(old_snapshot),
        new_value=_dump(new_snapshot),
        undo_of=None,
        operator=operator,
        comment=payload.comment,
    )
    db.add(correction)
    db.commit()
    db.refresh(correction)
    return correction


def undo_correction(
    db: Session,
    *,
    target_id: int | None = None,
    operator: str | None = None,
    comment: str | None = None,
) -> Correction:
    """Revert the referenced correction (or the caller's most recent).

    The `corrections` table stays append-only: undo adds a new row of
    `action='undo'` and the detection is restored from the original
    `old_value` snapshot.
    """
    if target_id is not None:
        target = db.query(Correction).filter(Correction.id == target_id).first()
    else:
        target = (
            db.query(Correction)
            .filter(Correction.operator == operator, Correction.action != "undo")
            .order_by(Correction.id.desc())
            .first()
        )
    if target is None:
        raise AppError(Err.NOT_FOUND, "nothing to undo", 404)
    if target.action == "undo":
        raise AppError(Err.CONFLICT, "target is itself an undo entry", 409)

    original_snapshot = _load(target.old_value)
    detection: Detection | None = None
    if target.detection_id is not None:
        detection = db.query(Detection).filter(Detection.id == target.detection_id).first()

    if detection is not None and original_snapshot is not None:
        _apply_snapshot(detection, original_snapshot)
    elif target.action == "add" and detection is not None:
        # Undoing an "add" removes the box again
        db.delete(detection)

    undo_row = Correction(
        detection_id=target.detection_id,
        task_id=target.task_id,
        action="undo",
        old_value=target.new_value,
        new_value=target.old_value,
        undo_of=target.id,
        operator=operator,
        comment=comment,
    )
    db.add(undo_row)
    db.commit()
    db.refresh(undo_row)
    return undo_row


def apply_batch(
    db: Session,
    items: list[CorrectionBatchItem],
    *,
    operator: str | None = None,
) -> list[Correction]:
    """Apply several corrections in one transaction (one Annotate session)."""
    results: list[Correction] = []
    for item in items:
        payload = CorrectionCreate(
            action=item.action,
            detection_id=item.detection_id,
            task_id=item.task_id,
            new_class_name=item.new_class_name,
            new_bbox=item.new_bbox,
            comment=item.comment,
        )
        results.append(apply_correction(db, payload, operator=operator))
    return results


def list_corrections(
    db: Session,
    *,
    task_id: int | None = None,
    detection_id: int | None = None,
    operator: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    q = db.query(Correction)
    if task_id is not None:
        q = q.filter(Correction.task_id == task_id)
    if detection_id is not None:
        q = q.filter(Correction.detection_id == detection_id)
    if operator is not None:
        q = q.filter(Correction.operator == operator)
    total = q.count()
    rows = q.order_by(Correction.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    pages = (total + page_size - 1) // page_size if total else 0
    return {"items": rows, "total": total, "page": page, "page_size": page_size, "pages": pages}


def latest_undoable(db: Session, operator: str) -> Correction | None:
    return (
        db.query(Correction)
        .filter(Correction.operator == operator, Correction.action != "undo")
        .order_by(Correction.id.desc())
        .first()
    )
