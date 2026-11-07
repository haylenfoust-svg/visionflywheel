"""Detector factory — picks the best available implementation (ADR-002).

Resolution order:
  1. Explicitly requested mode (config `force_detector_mode`)
  2. YOLO if ultralytics is importable and weights exist
  3. Fallback detector

`get_detector()` is a module-level singleton; `reload_detector()` swaps it
when the admin changes the default weight or forces a mode.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.services.config_service import get_config_service
from app.services.detector import Detector
from app.services.fallback_detector import FallbackDetector
from app.services.yolo_service import YOLODetector

logger = logging.getLogger(__name__)

_detector: Detector | None = None
_force_fallback = False


def _build() -> Detector:
    yolo = YOLODetector()
    if _force_fallback:
        logger.info("detector forced to fallback (ADR-002)")
        return FallbackDetector()
    if yolo.available and yolo.weight_path:
        logger.info("detector: yolo (weight=%s)", yolo.weight_path)
        return yolo
    logger.warning("detector: fallback — ultralytics unavailable or no weights (ADR-002)")
    return FallbackDetector()


def get_detector() -> Detector:
    global _detector
    if _detector is None:
        _detector = _build()
    return _detector


def reload_detector(weight_path: str | None = None) -> Detector:
    """Swap the active detector — used by the config/weight hooks."""
    global _detector
    _detector = None
    if weight_path:
        yolo = YOLODetector(weight_path)
        if yolo.available:
            _detector = yolo
            return _detector
    _detector = _build()
    return _detector


def force_fallback(enabled: bool) -> None:
    """Flip the fallback switch (config `enable_fallback_detector`)."""
    global _force_fallback, _detector
    _force_fallback = bool(enabled)
    _detector = None


def sync_from_config(db: Session | None) -> Detector:
    """Read config knobs and rebuild the detector accordingly."""
    if db is None:
        return get_detector()
    try:
        cfg = get_config_service()
        if not bool(cfg.get(db, "enable_fallback_detector")):
            force_fallback(False)
        weight_id = cfg.get(db, "default_weight_id")
        if weight_id:
            from app.models.weight import Weight  # local import to avoid cycles

            row = db.query(Weight).filter(Weight.id == weight_id).first()
            if row is not None:
                return reload_detector(row.path)
    except Exception:
        logger.exception("detector sync_from_config failed; keeping current detector")
    return get_detector()


def detector_mode() -> str:
    return get_detector().mode
