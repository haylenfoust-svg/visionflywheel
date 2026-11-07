"""Task / detection endpoints (docs/API.md §2-3, PRD FR-2).

Every route now declares its required permission (B端-1) and, where relevant,
applies org/team scope filtering (B端-2).
"""

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.envelope import EnvelopeRoute
from app.core.exceptions import AppError, Err
from app.models.detection import Detection
from app.models.task import Task
from app.schemas.common import BBox, Page
from app.schemas.detection import (
    DetectionOut,
    DetectionStats,
    DetectParams,
    TaskOut,
    UploadResult,
)
from app.services import task_service
from app.services.detector_factory import detector_mode
from app.services.permission_service import require_permission
from app.services.scope_service import apply_scope_filter
from app.utils.files import validate_image_name, validate_image_size

router = APIRouter(tags=["tasks"], route_class=EnvelopeRoute)


def _to_detection_out(row: Detection) -> DetectionOut:
    return DetectionOut(
        id=row.id,
        task_id=row.task_id,
        item_index=row.item_index,
        image_path=row.image_path,
        result_path=row.result_path,
        class_id=row.class_id,
        class_name=row.class_name,
        class_name_zh=row.class_name_zh,
        confidence=row.confidence,
        bbox=BBox(x1=row.x1, y1=row.y1, x2=row.x2, y2=row.y2),
        status=row.status,
        source=row.source,
        created_at=row.created_at,
    )


@router.post("/tasks/upload", response_model=UploadResult)
async def upload_and_detect(
    user: CurrentUser,
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
    conf_threshold: float | None = Form(default=None),
    iou_threshold: float | None = Form(default=None),
    imgsz: int | None = Form(default=None),
    org_id: int | None = Form(default=None),
    team_id: int | None = Form(default=None),
    _perm: object = Depends(require_permission("task.write")),
) -> UploadResult:
    if not file.filename:
        raise AppError(Err.VALIDATION, "filename is required", 400)
    try:
        validate_image_name(file.filename)
    except ValueError as exc:
        raise AppError(Err.UNSUPPORTED_FILE, str(exc), 400) from exc

    data = await file.read()
    try:
        validate_image_size(len(data))
    except ValueError as exc:
        code = Err.FILE_TOO_LARGE if "exceeds" in str(exc) else Err.VALIDATION
        raise AppError(code, str(exc), 400) from exc

    params = DetectParams(conf_threshold=conf_threshold, iou_threshold=iou_threshold, imgsz=imgsz)

    try:
        result = task_service.run_image_task(
            db,
            file_bytes=data,
            filename=file.filename,
            username=user.username,
            params=params,
            org_id=org_id,
            team_id=team_id,
        )
    except ValueError as exc:
        raise AppError(Err.VALIDATION, str(exc), 400) from exc
    except Exception as exc:
        raise AppError(Err.INTERNAL, f"detection failed: {exc}", 500) from exc

    return UploadResult(
        task_id=result["task"].id,
        status=result["task"].status,
        image_url=result["image_url"],
        result_url=result["result_url"],
        detector_mode=result["task"].detector_mode,
        inference_ms=result["task"].inference_ms or 0.0,
        detections=[_to_detection_out(d) for d in result["detections"]],
    )


@router.get("/tasks", response_model=Page[TaskOut])
def list_tasks(
    user: CurrentUser,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    mine: bool = Query(False, description="Filter to tasks I created"),
    _perm: object = Depends(require_permission("task.read")),
) -> Page[TaskOut]:
    q = db.query(Task)
    if mine:
        q = q.filter(Task.created_by == user.username)
    else:
        q = apply_scope_filter(q, user, Task, db)
    total = q.count()
    rows = q.order_by(Task.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    pages = (total + page_size - 1) // page_size if total else 0
    return Page[TaskOut](
        items=[TaskOut.model_validate(t) for t in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(
    task_id: int,
    user: CurrentUser,
    db: Session = Depends(get_db),
    _perm: object = Depends(require_permission("task.read")),
) -> TaskOut:
    q = db.query(Task).filter(Task.id == task_id)
    q = apply_scope_filter(q, user, Task, db)
    task = q.first()
    if task is None:
        raise AppError(Err.NOT_FOUND, f"task not found: {task_id}", 404)
    return TaskOut.model_validate(task)


@router.get("/tasks/{task_id}/detections", response_model=list[DetectionOut])
def get_task_detections(
    task_id: int,
    user: CurrentUser,
    db: Session = Depends(get_db),
    _perm: object = Depends(require_permission("detection.read")),
) -> list[DetectionOut]:
    q = db.query(Task).filter(Task.id == task_id)
    q = apply_scope_filter(q, user, Task, db)
    if q.first() is None:
        raise AppError(Err.NOT_FOUND, f"task not found: {task_id}", 404)
    rows = db.query(Detection).filter(Detection.task_id == task_id).order_by(Detection.id).all()
    return [_to_detection_out(r) for r in rows]


@router.get("/detections/stats", response_model=DetectionStats)
def get_stats(
    user: CurrentUser,
    db: Session = Depends(get_db),
    _perm: object = Depends(require_permission("detection.read")),
) -> DetectionStats:
    # Scope the underlying stats to visible tasks
    visible_tasks = apply_scope_filter(db.query(Task.id), user, Task, db).subquery()
    return DetectionStats(**task_service.detection_stats(db, task_ids_subquery=visible_tasks))


@router.get("/detections/{detection_id}", response_model=DetectionOut)
def get_detection(
    detection_id: int,
    user: CurrentUser,
    db: Session = Depends(get_db),
    _perm: object = Depends(require_permission("detection.read")),
) -> DetectionOut:
    q = db.query(Detection).filter(Detection.id == detection_id)
    # Scope via parent task
    task_q = apply_scope_filter(db.query(Task.id), user, Task, db).subquery()
    q = q.filter(Detection.task_id.in_(task_q))
    row = q.first()
    if row is None:
        raise AppError(Err.NOT_FOUND, f"detection not found: {detection_id}", 404)
    return _to_detection_out(row)


@router.get("/files/{file_path:path}")
def read_file(
    file_path: str,
    user: CurrentUser,
    _perm: object = Depends(require_permission("task.read")),
):
    """Serve a runtime file (uploads / results). Weights are never served (NFR-11)."""
    settings = get_settings()
    if file_path.startswith("weights") or file_path.endswith(".pt"):
        raise AppError(Err.FORBIDDEN, "weights are not downloadable", 403)

    runtime_root = Path(settings.upload_dir).parent.resolve()
    target = (runtime_root / file_path).resolve()
    if not str(target).startswith(str(runtime_root)):
        raise AppError(Err.FORBIDDEN, "path traversal rejected", 403)
    if not target.is_file():
        raise AppError(Err.NOT_FOUND, f"file not found: {file_path}", 404)
    return FileResponse(target)


def detector_info() -> dict:
    return {"detector_mode": detector_mode()}
