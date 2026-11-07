"""Detector protocol and shared result type (ADR-002).

Both `yolo_detector` and `fallback_detector` implement `Detector` so the
business layer is agnostic to which one is actually running.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(slots=True)
class RawDetection:
    """A single detection before persistence / Chinese mapping."""

    class_id: int
    class_name: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float

    def as_dict(self) -> dict:
        return {
            "class_id": self.class_id,
            "class_name": self.class_name,
            "confidence": self.confidence,
            "x1": self.x1,
            "y1": self.y1,
            "x2": self.x2,
            "y2": self.y2,
        }


@runtime_checkable
class Detector(Protocol):
    """Pluggable detector — see ADR-002 for the fallback contract."""

    @property
    def mode(self) -> str: ...

    @property
    def available(self) -> bool: ...

    def detect(self, image_path: str, *, conf: float = 0.5, iou: float = 0.45, imgsz: int = 640) -> list[RawDetection]: ...

    def reload(self, weight_path: str | None = None) -> None: ...
