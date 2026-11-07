"""Detection / Task DTOs (docs/API.md §2-3)."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import BBox


class DetectionOut(BaseModel):
    id: int
    task_id: int
    item_index: int
    image_path: str
    result_path: str | None
    class_id: int
    class_name: str
    class_name_zh: str | None
    confidence: float
    bbox: BBox
    status: str
    source: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskOut(BaseModel):
    id: int
    type: str
    status: str
    created_by: str | None
    conf_threshold: float
    iou_threshold: float
    imgsz: int
    weight_id: int | None
    detector_mode: str
    total_items: int
    done_items: int
    inference_ms: float | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UploadResult(BaseModel):
    task_id: int
    status: str
    image_url: str
    result_url: str | None
    detector_mode: str
    inference_ms: float
    detections: list[DetectionOut]


class BatchUploadResult(BaseModel):
    task_ids: list[int]
    status: str
    total_items: int


class TaskProgress(BaseModel):
    task_id: int
    status: str
    total_items: int
    done_items: int
    percent: float


class DetectParams(BaseModel):
    """Inference knobs — all optional; None means "use the configured default"."""

    conf_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    iou_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    imgsz: int | None = Field(default=None, ge=32, le=2048)


class DetectionStats(BaseModel):
    total: int
    by_status: dict[str, int]
    by_class: list[dict]
    today: dict[str, int]
    avg_confidence: float
