"""Image utilities — draw detection boxes on a copy of the source image."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(slots=True)
class BoxToDraw:
    x1: float
    y1: float
    x2: float
    y2: float
    label: str
    confidence: float
    color_bgr: tuple[int, int, int] = (54, 162, 235)  # medium blue


# BGR palette — flat fills per the design system
_PALETTE = [
    (54, 162, 235),   # blue
    (75, 192, 192),   # teal
    (255, 159, 64),   # orange
    (153, 102, 255),  # purple
    (255, 99, 132),   # red-ish
    (255, 205, 86),   # yellow
]


def draw_boxes(
    image_path: str | Path,
    boxes: list[BoxToDraw],
    output_path: str | Path,
    *,
    thickness: int = 2,
    font_scale: float = 0.55,
) -> Path:
    """Render `boxes` onto a copy of `image_path`, save to `output_path`."""
    src = str(image_path)
    image = cv2.imread(src)
    if image is None:
        raise ValueError(f"cannot read image: {src}")

    for index, box in enumerate(boxes):
        color = box.color_bgr if box.color_bgr != (54, 162, 235) else _PALETTE[index % len(_PALETTE)]
        p1 = (int(round(box.x1)), int(round(box.y1)))
        p2 = (int(round(box.x2)), int(round(box.y2)))
        cv2.rectangle(image, p1, p2, color, thickness)

        text = f"{box.label} {box.confidence:.2f}"
        (tw, th), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
        ty1 = max(0, p1[1] - th - baseline - 4)
        cv2.rectangle(image, (p1[0], ty1), (p1[0] + tw + 6, ty1 + th + baseline + 4), color, -1)
        cv2.putText(
            image,
            text,
            (p1[0] + 3, ty1 + th + 1),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(out), image):
        raise OSError(f"cannot write image: {out}")
    return out


def image_size(image_path: str | Path) -> tuple[int, int]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"cannot read image: {image_path}")
    h, w = image.shape[:2]
    return w, h


def make_test_image(output_path: str | Path, *, width: int = 640, height: int = 480) -> Path:
    """Deterministic test image with a few distinct blobs — used in tests."""
    canvas = np.full((height, width, 3), 240, dtype=np.uint8)
    cv2.rectangle(canvas, (80, 60), (240, 220), (40, 40, 200), -1)   # red block
    cv2.circle(canvas, (450, 300), 90, (40, 180, 60), -1)            # green disc
    cv2.rectangle(canvas, (300, 340), (420, 430), (200, 120, 40), -1)  # blue block
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), canvas)
    return out
