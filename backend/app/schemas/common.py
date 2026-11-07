"""Shared response / pagination envelopes (docs/API.md §0.3-0.4)."""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiSuccess(BaseModel, Generic[T]):
    code: int = 0
    message: str = "ok"
    data: T | None = None


class ApiFailure(BaseModel):
    code: int
    message: str
    data: Any = None
    request_id: str | None = None


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


class BBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
