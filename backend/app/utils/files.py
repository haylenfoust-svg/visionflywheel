"""File handling — safe names, type checks, directory layout (PRD FR-9.3/9.4)."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from app.core.config import get_settings

# PRD FR-2.1
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
# PRD FR-2.3
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv"}

MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB
MAX_VIDEO_BYTES = 500 * 1024 * 1024  # 500 MB

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]")


def safe_filename(original: str) -> str:
    """Strip path separators / traversal and normalise the file name."""
    name = Path(original).name  # drops any directory part
    name = _SAFE_NAME_RE.sub("_", name).lstrip(".")
    return name or f"file-{uuid.uuid4().hex[:8]}"


def ensure_within(base: Path, candidate: Path) -> Path:
    """Resolve `candidate` and reject anything that escapes `base` (path traversal)."""
    base_resolved = base.resolve()
    candidate_resolved = candidate.resolve()
    if not str(candidate_resolved).startswith(str(base_resolved)):
        raise ValueError("path traversal rejected")
    return candidate_resolved


def image_upload_path(task_id: int, filename: str) -> Path:
    settings = get_settings()
    root = Path(settings.upload_dir)
    sub = root / str(task_id)
    sub.mkdir(parents=True, exist_ok=True)
    return ensure_within(root, sub / safe_filename(filename))


def result_image_path(task_id: int, filename: str) -> Path:
    settings = get_settings()
    root = Path(settings.result_dir)
    sub = root / str(task_id)
    sub.mkdir(parents=True, exist_ok=True)
    return ensure_within(root, sub / safe_filename(filename))


def validate_image_name(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError(f"unsupported image type: {ext or '(none)'}")
    return ext


def validate_image_size(size: int) -> None:
    if size <= 0:
        raise ValueError("empty file")
    if size > MAX_IMAGE_BYTES:
        raise ValueError(f"image exceeds {MAX_IMAGE_BYTES // (1024 * 1024)} MB limit")


def relative_to_runtime(path: Path) -> str:
    """Store paths relative to runtime_data/ so the DB stays relocatable."""
    settings = get_settings()
    runtime_root = Path(settings.upload_dir).parent
    try:
        return str(path.resolve().relative_to(runtime_root.resolve()))
    except ValueError:
        return str(path)
