"""Correction / Feedback DTOs (docs/API.md §4-5)."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import BBox

# PRD FR-3.1 ~ FR-3.6
ACTIONS = ("confirm", "relabel", "false_positive", "adjust", "add", "undo")
ActionLiteral = str  # runtime-validated against ACTIONS


class CorrectionCreate(BaseModel):
    action: str = Field(pattern=r"^(confirm|relabel|false_positive|adjust|add|undo)$")
    detection_id: int | None = None
    task_id: int | None = None  # required for action='add'
    new_class_name: str | None = Field(default=None, max_length=64)
    new_bbox: BBox | None = None
    comment: str | None = Field(default=None, max_length=500)
    undo_of: int | None = None  # required for action='undo'


class CorrectionOut(BaseModel):
    id: int
    detection_id: int | None
    task_id: int
    action: str
    old_value: str | None
    new_value: str | None
    undo_of: int | None
    operator: str | None
    comment: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CorrectionResult(BaseModel):
    correction_id: int
    detection_id: int | None
    action: str
    old_value: str | None
    new_value: str | None
    detection_status: str | None
    created_at: datetime


class CorrectionBatchItem(BaseModel):
    action: str = Field(pattern=r"^(confirm|relabel|false_positive|adjust|add)$")
    detection_id: int | None = None
    task_id: int | None = None
    new_class_name: str | None = None
    new_bbox: BBox | None = None
    comment: str | None = None


class CorrectionBatchRequest(BaseModel):
    items: list[CorrectionBatchItem] = Field(min_length=1, max_length=200)


class UndoRequest(BaseModel):
    correction_id: int | None = None  # None = undo the caller's most recent


# ---------- Feedback ----------
class FeedbackCreate(BaseModel):
    detection_id: int | None = None
    task_id: int | None = None
    content: str = Field(min_length=1, max_length=1000)


class FeedbackReply(BaseModel):
    reply: str = Field(min_length=1, max_length=1000)


class FeedbackStatusUpdate(BaseModel):
    status: str = Field(pattern=r"^(open|replied|resolved|rejected)$")


class FeedbackOut(BaseModel):
    id: int
    detection_id: int | None
    task_id: int | None
    username: str | None
    content: str
    status: str
    reply: str | None
    replied_by: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
