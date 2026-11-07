"""Fallback detector tests (ADR-002) — the loop must run without torch."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.fallback_detector import FallbackDetector
from app.utils.imaging import make_test_image


@pytest.fixture
def test_image(tmp_path: Path) -> Path:
    return make_test_image(tmp_path / "test.png", width=640, height=480)


def test_fallback_detects_blobs(test_image: Path):
    det = FallbackDetector()
    results = det.detect(str(test_image), conf=0.3, iou=0.45, imgsz=640)
    assert det.mode == "fallback"
    # make_test_image draws 3 distinct shapes; the detector must find at least one
    assert len(results) >= 1
    for r in results:
        assert r.class_name == "object"
        assert 0.0 <= r.confidence <= 1.0
        assert r.x2 > r.x1
        assert r.y2 > r.y1


def test_fallback_respects_conf(test_image: Path):
    det = FallbackDetector()
    low = det.detect(str(test_image), conf=0.0, iou=0.45, imgsz=640)
    high = det.detect(str(test_image), conf=0.95, iou=0.45, imgsz=640)
    assert len(high) <= len(low)


def test_fallback_rejects_unreadable_file(tmp_path: Path):
    det = FallbackDetector()
    with pytest.raises(ValueError, match="cannot read image"):
        det.detect(str(tmp_path / "missing.png"))


def test_fallback_is_deterministic(test_image: Path):
    det = FallbackDetector()
    a = det.detect(str(test_image), conf=0.3, iou=0.45, imgsz=640)
    b = det.detect(str(test_image), conf=0.3, iou=0.45, imgsz=640)
    assert [r.as_dict() for r in a] == [r.as_dict() for r in b]


def test_nms_suppresses_overlap(test_image: Path):
    from app.services.detector import RawDetection
    from app.services.fallback_detector import _nms

    a = RawDetection(0, "object", 0.9, 0, 0, 100, 100)
    b = RawDetection(0, "object", 0.8, 5, 5, 105, 105)  # heavily overlaps a
    c = RawDetection(0, "object", 0.7, 300, 300, 400, 400)  # far from both
    kept = _nms([a, b, c], iou_threshold=0.3)
    assert len(kept) == 2
    assert a in kept
    assert c in kept
    assert b not in kept
