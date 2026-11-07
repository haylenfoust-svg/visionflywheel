"""Batch upload endpoints (PRD FR-2.2)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.envelope import EnvelopeRoute
from app.core.exceptions import AppError, Err
from app.schemas.detection import BatchUploadResult, DetectParams
from app.services import task_service
from app.services.permission_service import require_permission
from app.utils.files import validate_image_name, validate_image_size

logger = logging.getLogger(__name__)

router = APIRouter(tags=["batch"], route_class=EnvelopeRoute)
MAX_BATCH_FILES = 50  # PRD FR-2.2


@router.post("/tasks/batch", response_model=BatchUploadResult)
async def batch_upload(
    user: CurrentUser,
    db: Session = Depends(get_db),
    _perm: object = Depends(require_permission("task.write")),
    files: list[UploadFile] = File(...),
    conf_threshold: float | None = Form(default=None),
    iou_threshold: float | None = Form(default=None),
    imgsz: int | None = Form(default=None),
) -> BatchUploadResult:
    if not files:
        raise AppError(Err.VALIDATION, "no files supplied", 400)
    if len(files) > MAX_BATCH_FILES:
        raise AppError(Err.VALIDATION, f"too many files (max {MAX_BATCH_FILES})", 400)

    params = DetectParams(conf_threshold=conf_threshold, iou_threshold=iou_threshold, imgsz=imgsz)

    task_ids: list[int] = []
    errors: list[str] = []
    for upload in files:
        if not upload.filename:
            continue
        try:
            validate_image_name(upload.filename)
            data = await upload.read()
            validate_image_size(len(data))
            result = task_service.run_image_task(
                db,
                file_bytes=data,
                filename=upload.filename,
                username=user.username,
                params=params,
            )
            task_ids.append(result["task"].id)
        except Exception as exc:
            logger.warning("batch item failed: %s — %s", upload.filename, exc)
            errors.append(f"{upload.filename}: {exc}")

    if not task_ids:
        raise AppError(Err.VALIDATION, f"all uploads failed: {'; '.join(errors[:3])}", 400)

    return BatchUploadResult(
        task_ids=task_ids,
        status="done" if not errors else "partial",
        total_items=len(task_ids),
    )
