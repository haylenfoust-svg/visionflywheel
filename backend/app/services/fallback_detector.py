"""Rule-based fallback detector (ADR-002).

Used when ultralytics / torch is unavailable. The goal is NOT accuracy —
it is to keep the **entire loop** (upload → detect → correct → export) runnable
so users can learn the workflow before installing the ML stack.

Method: grayscale → adaptive threshold → morphological cleanup → contours →
boxes around blobs above a minimum area. Confidence is the blob's area ratio,
which is a crude heuristic, not a calibrated probability.
"""

from __future__ import annotations

import cv2

from app.services.detector import RawDetection

# Keep the fallback class mapping tiny and explicit — PRD G5 says the loop
# must run without torch, not that it must be accurate.
FALLBACK_CLASS_ID = 0
FALLBACK_CLASS_NAME = "object"

# Reject blobs smaller than this fraction of the image (noise) or larger
# than this fraction (background).
_MIN_AREA_RATIO = 0.004
_MAX_AREA_RATIO = 0.60


class FallbackDetector:
    """Deterministic, dependency-light detector."""

    @property
    def mode(self) -> str:
        return "fallback"

    @property
    def available(self) -> bool:
        return True

    def detect(self, image_path: str, *, conf: float = 0.5, iou: float = 0.45, imgsz: int = 640) -> list[RawDetection]:
        del imgsz  # kept for Detector protocol compatibility; unused by the rule-based path
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"cannot read image: {image_path}")

        h, w = image.shape[:2]
        image_area = float(h * w)

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        binary = cv2.adaptiveThreshold(
            blurred,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            blockSize=31,
            C=10,
        )
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        cleaned = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel, iterations=1)

        contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        results: list[RawDetection] = []
        for contour in contours:
            area = float(cv2.contourArea(contour))
            ratio = area / image_area
            if ratio < _MIN_AREA_RATIO or ratio > _MAX_AREA_RATIO:
                continue

            x, y, bw, bh = cv2.boundingRect(contour)
            # Heuristic confidence: favour mid-sized blobs.
            confidence = min(1.0, max(0.0, 0.5 + ratio))
            if confidence < conf:
                continue

            results.append(
                RawDetection(
                    class_id=FALLBACK_CLASS_ID,
                    class_name=FALLBACK_CLASS_NAME,
                    confidence=round(confidence, 4),
                    x1=float(x),
                    y1=float(y),
                    x2=float(x + bw),
                    y2=float(y + bh),
                )
            )

        # Suppress heavy overlaps (crude NMS) so one object is not framed twice.
        return _nms(results, iou)

    def reload(self, weight_path: str | None = None) -> None:
        del weight_path  # kept for Detector protocol compatibility; stateless
        return


def _nms(detections: list[RawDetection], iou_threshold: float) -> list[RawDetection]:
    if not detections:
        return []
    ordered = sorted(detections, key=lambda d: d.confidence, reverse=True)
    kept: list[RawDetection] = []
    for candidate in ordered:
        if all(_iou(candidate, k) < iou_threshold for k in kept):
            kept.append(candidate)
    return kept


def _iou(a: RawDetection, b: RawDetection) -> float:
    ix1 = max(a.x1, b.x1)
    iy1 = max(a.y1, b.y1)
    ix2 = min(a.x2, b.x2)
    iy2 = min(a.y2, b.y2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, a.x2 - a.x1) * max(0.0, a.y2 - a.y1)
    area_b = max(0.0, b.x2 - b.x1) * max(0.0, b.y2 - b.y1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0
