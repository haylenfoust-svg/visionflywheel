"""Pydantic DTOs — re-exported for convenience."""

from app.schemas.auth import LoginRequest, TokenOut, UserCreate, UserOut, UserUpdate
from app.schemas.common import ApiFailure, ApiSuccess, BBox, Page
from app.schemas.config import (
    AuditOut,
    ConfigMapOut,
    ConfigUpdate,
    ConfigValueOut,
    HealthOut,
    SystemInfoOut,
)
from app.schemas.detection import (
    BatchUploadResult,
    DetectionOut,
    DetectionStats,
    DetectParams,
    TaskOut,
    TaskProgress,
    UploadResult,
)

__all__ = [
    "ApiFailure",
    "ApiSuccess",
    "BBox",
    "Page",
    "LoginRequest",
    "TokenOut",
    "UserCreate",
    "UserOut",
    "UserUpdate",
    "ConfigValueOut",
    "ConfigMapOut",
    "ConfigUpdate",
    "AuditOut",
    "HealthOut",
    "SystemInfoOut",
    "DetectionOut",
    "TaskOut",
    "UploadResult",
    "BatchUploadResult",
    "TaskProgress",
    "DetectParams",
    "DetectionStats",
]
