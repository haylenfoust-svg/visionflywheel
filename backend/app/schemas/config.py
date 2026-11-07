"""Config DTOs (docs/API.md §9, ADR-003)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ConfigValueOut(BaseModel):
    value: Any
    source: str  # db | env | default
    default: Any = None


class ConfigMapOut(BaseModel):
    values: dict[str, ConfigValueOut]


class ConfigUpdate(BaseModel):
    value: Any
    note: str | None = Field(default=None, max_length=255)


class AuditOut(BaseModel):
    id: int
    entity: str
    entity_key: str
    old_value: str | None
    new_value: str | None
    operator: str | None
    action: str
    created_at: datetime

    model_config = {"from_attributes": True}


class HealthOut(BaseModel):
    status: str
    version: str
    detector_mode: str
    db: str


class SystemInfoOut(BaseModel):
    version: str
    detector_mode: str
    default_weight_id: int | None
    enable_fallback_detector: bool
    role: str
