"""Dataset / Weight / Training DTOs (docs/API.md §6-8)."""

from datetime import datetime

from pydantic import BaseModel, Field


class DatasetExportRequest(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    val_ratio: float | None = Field(default=None, ge=0.05, le=0.5)
    include_rejected: bool = True
    seed: int | None = None


class DatasetExportOut(BaseModel):
    dataset_version: str
    path: str
    train_images: int
    val_images: int
    holdout_images: int
    total_labels: int
    class_names: list[str]


class DatasetExportRow(BaseModel):
    id: int
    dataset_version: str
    name: str | None
    total_images: int
    total_labels: int
    train_images: int
    val_images: int
    holdout_images: int
    class_names: str  # JSON-encoded list
    val_ratio: float
    seed: int
    status: str
    path: str
    created_by: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DatasetPendingOut(BaseModel):
    pending_images: int
    holdout_images: int
    sample_preview: list[str]


class DatasetSampleOut(BaseModel):
    id: int
    image_path: str
    split: str
    dataset_version: str | None
    is_frozen: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class WeightOut(BaseModel):
    id: int
    filename: str
    path: str
    is_default: bool
    source: str
    dataset_version: str | None
    holdout_map: float | None
    class_count: int | None
    note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class WeightHotSwapOut(BaseModel):
    weight_id: int
    filename: str
    is_default: bool
    reloaded_in_ms: float
    requires_restart: bool


class TrainRequest(BaseModel):
    dataset_version: str
    base_weight: str = Field(default="yolov8n.pt", max_length=255)
    epochs: int = Field(default=100, ge=1, le=1000)
    imgsz: int = Field(default=640, ge=128, le=2048)
    batch: int = Field(default=16, ge=1, le=256)
    name: str | None = Field(default=None, max_length=64)


class TrainRunOut(BaseModel):
    id: int
    dataset_version: str
    base_weight: str
    name: str | None
    epochs: int
    imgsz: int
    batch: int
    status: str
    progress: float
    best_weight_path: str | None
    holdout_map: float | None
    error_message: str | None
    started_by: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TrainRunDetail(TrainRunOut):
    log_tail: str | None
