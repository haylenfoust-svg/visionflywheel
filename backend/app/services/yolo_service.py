"""YOLO detector — thin wrapper over ultralytics (ADR-002).

Import is lazy so the app still boots when torch/ultralytics is missing;
in that case `YOLODetector.available` is False and the factory in
`detector_factory` falls back to `FallbackDetector`.
"""

from __future__ import annotations

from pathlib import Path

from app.services.detector import RawDetection

_YOLO_AVAILABLE: bool | None = None


def _yolo_available() -> bool:
    global _YOLO_AVAILABLE
    if _YOLO_AVAILABLE is None:
        try:
            import ultralytics  # noqa: F401

            _YOLO_AVAILABLE = True
        except Exception:
            _YOLO_AVAILABLE = False
    return _YOLO_AVAILABLE


class YOLODetector:
    def __init__(self, weight_path: str | None = None) -> None:
        self._model = None
        self._weight_path = weight_path or self._default_weight_path()

    @staticmethod
    def _default_weight_path() -> str | None:
        weights_dir = Path("backend/weights")
        if not weights_dir.exists():
            weights_dir = Path("weights")
        if weights_dir.exists():
            candidates = sorted(weights_dir.glob("*.pt"))
            if candidates:
                return str(candidates[0])
        return None

    @property
    def mode(self) -> str:
        return "yolo"

    @property
    def available(self) -> bool:
        return _yolo_available()

    @property
    def weight_path(self) -> str | None:
        return self._weight_path

    def reload(self, weight_path: str | None = None) -> None:
        if weight_path is not None:
            self._weight_path = weight_path
        self._model = None  # force reload on next detect

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        if not self._yolo_available():
            raise RuntimeError("ultralytics is not installed; run `pip install -r requirements-ml.txt`")
        if not self._weight_path:
            raise RuntimeError("no YOLO weights found under backend/weights/")
        from ultralytics import YOLO

        self._model = YOLO(self._weight_path)
        return self._model

    def detect(self, image_path: str, *, conf: float = 0.5, iou: float = 0.45, imgsz: int = 640) -> list[RawDetection]:
        model = self._ensure_model()
        results = model.predict(
            source=image_path,
            conf=conf,
            iou=iou,
            imgsz=imgsz,
            verbose=False,
        )
        output: list[RawDetection] = []
        for result in results:
            names = result.names or {}
            boxes = result.boxes
            if boxes is None:
                continue
            for box in boxes:
                cls_id = int(box.cls.item())
                xyxy = box.xyxy[0].tolist()
                output.append(
                    RawDetection(
                        class_id=cls_id,
                        class_name=str(names.get(cls_id, f"class_{cls_id}")),
                        confidence=float(box.conf.item()),
                        x1=float(xyxy[0]),
                        y1=float(xyxy[1]),
                        x2=float(xyxy[2]),
                        y2=float(xyxy[3]),
                    )
                )
        return output
