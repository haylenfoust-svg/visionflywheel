"""Task orchestration — upload → detect → persist → visualise (PRD FR-2)."""

from __future__ import annotations

import logging
import time

from sqlalchemy.orm import Session

from app.models.detection import Detection
from app.models.task import Task
from app.schemas.detection import DetectParams
from app.services.config_service import get_config_service
from app.services.detector_factory import get_detector
from app.services.label_mapper import LabelMapper
from app.utils.files import (
    image_upload_path,
    relative_to_runtime,
    result_image_path,
    safe_filename,
    validate_image_name,
    validate_image_size,
)
from app.utils.imaging import BoxToDraw, draw_boxes

logger = logging.getLogger(__name__)


def _resolve_params(db: Session, params: DetectParams | None) -> tuple[float, float, int]:
    cfg = get_config_service()
    conf = params.conf_threshold if params and params.conf_threshold is not None else float(cfg.get(db, "default_conf_threshold"))
    iou = params.iou_threshold if params and params.iou_threshold is not None else float(cfg.get(db, "default_iou_threshold"))
    imgsz = params.imgsz if params and params.imgsz is not None else int(cfg.get(db, "default_imgsz"))
    return conf, iou, imgsz


def run_image_task(
    db: Session,
    *,
    file_bytes: bytes,
    filename: str,
    username: str | None,
    params: DetectParams | None = None,
) -> dict:
    """Full loop for one image. Raises ValueError on invalid input."""
    validate_image_name(filename)
    validate_image_size(len(file_bytes))

    conf, iou, imgsz = _resolve_params(db, params)
    detector = get_detector()

    task = Task(
        type="image",
        status="running",
        created_by=username,
        conf_threshold=conf,
        iou_threshold=iou,
        imgsz=imgsz,
        detector_mode=detector.mode,
        total_items=1,
        done_items=0,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    try:
        # Persist the upload under runtime_data/uploads/<task_id>/<safe name>
        upload_path = image_upload_path(task.id, filename)
        upload_path.write_bytes(file_bytes)
        image_rel = relative_to_runtime(upload_path)
        # Store image path on the task so `action=add` can work even when
        # the model produced zero detections (PRD FR-3.5).
        task.meta = {
            "image_path": image_rel,
            "result_path": None,
            "filename": safe_filename(filename),
        }

        # Run detection
        started = time.perf_counter()
        raw = detector.detect(str(upload_path), conf=conf, iou=iou, imgsz=imgsz)
        elapsed_ms = (time.perf_counter() - started) * 1000.0

        # Map English → Chinese for display (PRD FR-2.6)
        mapper = LabelMapper(db)
        enriched = [
            (r, mapper.to_zh(r.class_name))
            for r in raw
        ]

        # Visualise
        result_path = result_image_path(task.id, f"result_{safe_filename(filename)}")
        draw_boxes(
            upload_path,
            [
                BoxToDraw(
                    x1=r.x1,
                    y1=r.y1,
                    x2=r.x2,
                    y2=r.y2,
                    label=zh or r.class_name,
                    confidence=r.confidence,
                )
                for r, zh in enriched
            ],
            result_path,
        )
        result_rel = relative_to_runtime(result_path)
        if task.meta is None:
            task.meta = {}
        task.meta["result_path"] = result_rel

        # Persist detections
        for r, zh in enriched:
            db.add(
                Detection(
                    task_id=task.id,
                    item_index=0,
                    image_path=image_rel,
                    result_path=result_rel,
                    class_id=r.class_id,
                    class_name=r.class_name,
                    class_name_zh=zh,
                    confidence=r.confidence,
                    x1=r.x1,
                    y1=r.y1,
                    x2=r.x2,
                    y2=r.y2,
                    status="pending",
                    source="model",
                )
            )

        task.status = "done"
        task.done_items = 1
        task.inference_ms = round(elapsed_ms, 2)
        db.commit()
        db.refresh(task)

        return {
            "task": task,
            "image_url": f"/api/files/{image_rel}",
            "result_url": f"/api/files/{result_rel}",
            "detections": list(task.detections),
        }
    except Exception as exc:
        logger.exception("run_image_task failed")
        task.status = "failed"
        task.error_message = str(exc)
        db.commit()
        raise


def list_tasks(db: Session, *, username: str | None = None, page: int = 1, page_size: int = 20) -> dict:
    q = db.query(Task)
    if username:
        q = q.filter(Task.created_by == username)
    total = q.count()
    rows = q.order_by(Task.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    pages = (total + page_size - 1) // page_size if total else 0
    return {"items": rows, "total": total, "page": page, "page_size": page_size, "pages": pages}


def get_task(db: Session, task_id: int) -> Task | None:
    return db.query(Task).filter(Task.id == task_id).first()


def get_detections(db: Session, task_id: int) -> list[Detection]:
    return db.query(Detection).filter(Detection.task_id == task_id).order_by(Detection.id).all()


def detection_stats(db: Session) -> dict:
    from sqlalchemy import func

    total = db.query(func.count(Detection.id)).scalar() or 0

    by_status_rows = db.query(Detection.status, func.count(Detection.id)).group_by(Detection.status).all()
    by_status = dict(by_status_rows)

    by_class_rows = (
        db.query(Detection.class_name, Detection.class_name_zh, func.count(Detection.id))
        .group_by(Detection.class_name, Detection.class_name_zh)
        .order_by(func.count(Detection.id).desc())
        .all()
    )
    by_class = [
        {"class_name": name, "class_name_zh": zh, "count": count}
        for name, zh, count in by_class_rows
    ]

    today = {
        "detected": db.query(func.count(Detection.id))
        .filter(func.date(Detection.created_at) == func.date(func.now()))
        .scalar()
        or 0,
        "corrected": db.query(func.count(Detection.id))
        .filter(func.date(Detection.created_at) == func.date(func.now()), Detection.status == "corrected")
        .scalar()
        or 0,
    }

    avg_conf = db.query(func.avg(Detection.confidence)).scalar() or 0.0

    return {
        "total": total,
        "by_status": by_status,
        "by_class": by_class,
        "today": today,
        "avg_confidence": round(float(avg_conf), 4),
    }
