"""Video frame extraction + inference (M6 / 可选项).

Splits an uploaded video into frames at a configurable FPS, runs each
frame through the detector, and aggregates results per frame.

Currently synchronous (small videos). For long videos, delegate to
`inference_queue.submit_job` (P2.2) so the HTTP request returns immediately.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

import cv2

from app.services.detector_factory import get_detector

logger = logging.getLogger(__name__)

DEFAULT_FPS = 2  # sample 2 frames per second
MAX_FRAMES = 300  # safety cap


def extract_frames(
    video_path: str | Path,
    *,
    fps: int = DEFAULT_FPS,
    max_frames: int = MAX_FRAMES,
    output_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Sample frames from a video and return per-frame metadata.

    Returns a list of {"index": int, "path": str, "timestamp_ms": int}.
    """
    video_path = Path(video_path)
    if not video_path.is_file():
        raise FileNotFoundError(f"video not found: {video_path}")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"cannot open video: {video_path}")

    try:
        video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        _total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        interval = max(1, int(round(video_fps / max(1, fps))))

        out_dir = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="vf_frames_"))
        out_dir.mkdir(parents=True, exist_ok=True)

        frames: list[dict[str, Any]] = []
        idx = 0
        saved = 0
        while saved < max_frames:
            ret, frame = cap.read()
            if not ret:
                break
            if idx % interval == 0:
                ts_ms = int(idx / video_fps * 1000)
                fname = out_dir / f"frame_{saved:04d}_{ts_ms}ms.jpg"
                cv2.imwrite(str(fname), frame)
                frames.append({"index": saved, "path": str(fname), "timestamp_ms": ts_ms})
                saved += 1
            idx += 1

        return frames
    finally:
        cap.release()


def detect_video(
    video_path: str | Path,
    *,
    fps: int = DEFAULT_FPS,
    conf: float = 0.5,
    iou: float = 0.45,
    imgsz: int = 640,
    max_frames: int = MAX_FRAMES,
    progress_callback=None,
) -> dict[str, Any]:
    """Extract frames and run detection on each.

    Returns {"frames": [{"index", "timestamp_ms", "detections"}], "total": int,
             "detector_mode": str, "elapsed_ms": float}.
    """
    import time

    started = time.perf_counter()
    detector = get_detector()

    frames = extract_frames(video_path, fps=fps, max_frames=max_frames)
    results = []
    for i, fr in enumerate(frames):
        try:
            dets = detector.detect(fr["path"], conf=conf, iou=iou, imgsz=imgsz)
            results.append(
                {
                    "index": fr["index"],
                    "timestamp_ms": fr["timestamp_ms"],
                    "frame_path": fr["path"],
                    "detections": [
                        {
                            "class_id": d.class_id,
                            "class_name": d.class_name,
                            "confidence": d.confidence,
                            "bbox": {"x1": d.x1, "y1": d.y1, "x2": d.x2, "y2": d.y2},
                        }
                        for d in dets
                    ],
                }
            )
        except Exception as exc:
            logger.warning("frame %d detect failed: %s", fr["index"], exc)
            results.append({"index": fr["index"], "timestamp_ms": fr["timestamp_ms"], "detections": []})

        if progress_callback:
            progress_callback((i + 1) / max(1, len(frames)))

    elapsed = (time.perf_counter() - started) * 1000.0
    return {
        "frames": results,
        "total": len(results),
        "detector_mode": detector.mode,
        "elapsed_ms": round(elapsed, 1),
    }
