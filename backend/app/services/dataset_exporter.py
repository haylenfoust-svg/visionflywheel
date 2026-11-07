"""Dataset exporter — produces an ultralytics-standard training set.

Directory layout (PRD FR-5.2):

    runtime_data/datasets/{dataset_version}/
    ├── data.yaml
    ├── images/{train,val}/
    └── labels/{train,val}/

Label lines are `class cx cy w h`, all normalised to 0..1 (PRD FR-5.4).
Images assigned to `holdout` are frozen forever and never written into
train/val (PRD §8.2).
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AppError, Err
from app.models.dataset import DatasetExport, DatasetSample
from app.models.detection import Detection

logger = logging.getLogger(__name__)


def _new_version(name: str | None, image_paths: list[str]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    digest = hashlib.sha1("|".join(sorted(image_paths)).encode("utf-8")).hexdigest()[:6]
    slug = (name or "dataset").replace(" ", "_")[:24]
    return f"{slug}-{stamp}-{digest}"


def _upsert_sample(
    db: Session,
    *,
    image_path: str,
    split: str,
    dataset_version: str | None,
    is_frozen: bool,
    cache: dict[str, DatasetSample] | None = None,
) -> DatasetSample:
    """Update-or-insert by `image_path` (UNIQUE but not the PK).

    `cache` holds rows we've already created in this transaction — needed
    because `query().first()` does not see pending (unflushed) inserts.
    """
    if cache is not None and image_path in cache:
        row = cache[image_path]
        row.dataset_version = dataset_version or row.dataset_version
        return row
    row = db.query(DatasetSample).filter(DatasetSample.image_path == image_path).first()
    if row is None:
        row = DatasetSample(
            image_path=image_path,
            split=split,
            dataset_version=dataset_version,
            is_frozen=is_frozen,
        )
        db.add(row)
    else:
        row.split = split
        row.dataset_version = dataset_version or row.dataset_version
        row.is_frozen = is_frozen or row.is_frozen
    if cache is not None:
        cache[image_path] = row
    return row


def _split_of(image_path: str, train_paths: list[str], val_paths: list[str]) -> str:
    return "train" if image_path in train_paths else "val"


def _read_image_size(image_abs: Path) -> tuple[int, int]:
    """Return (width, height) for label normalisation."""
    try:
        import cv2

        image = cv2.imread(str(image_abs))
        if image is None:
            raise ValueError(f"cannot read image: {image_abs}")
        h, w = image.shape[:2]
        return w, h
    except Exception:
        # Fallback: Pillow
        from PIL import Image

        with Image.open(image_abs) as im:
            return im.size  # (w, h)


def export_dataset(
    db: Session,
    *,
    name: str | None = None,
    val_ratio: float | None = None,
    include_rejected: bool = True,
    seed: int | None = None,
    operator: str | None = None,
) -> dict:
    """Export every corrected-but-not-yet-exported image to a YOLO dataset.

    Raises AppError(409) when there is nothing to export.
    """
    settings = get_settings()
    cfg_val_ratio = val_ratio if val_ratio is not None else 0.2
    cfg_seed = seed if seed is not None else 42

    # --- 1. Collect eligible detections -----------------------------------
    # Eligible = the image has at least one non-pending detection and the
    # image has not already been exported.
    exported_images = {
        row.image_path
        for row in db.query(DatasetSample.image_path).filter(DatasetSample.dataset_version.isnot(None)).all()
    }

    all_detections = db.query(Detection).filter(Detection.status != "pending").all()
    by_image: dict[str, list[Detection]] = {}
    for det in all_detections:
        by_image.setdefault(det.image_path, []).append(det)

    candidate_images = [p for p in by_image if p not in exported_images]
    if not candidate_images:
        raise AppError(Err.CONFLICT, "no corrected-but-unexported images to export", 409)

    # --- 2. Split: holdout first (frozen), then train/val -----------------
    rng = random.Random(cfg_seed)
    rng.shuffle(candidate_images)

    holdout_paths: list[str] = []
    fresh: list[str] = []
    for image_path in candidate_images:
        existing = db.query(DatasetSample).filter(DatasetSample.image_path == image_path).first()
        if existing is not None:
            # Already assigned (incl. holdout) — keep the assignment
            if existing.split == "holdout":
                holdout_paths.append(image_path)
            else:
                fresh.append(image_path)
        else:
            fresh.append(image_path)

    # New images: 10% (default) go to holdout
    holdout_ratio = 0.1
    n_holdout = int(round(len(fresh) * holdout_ratio))
    if n_holdout > 0 and len(fresh) > 3:
        new_holdout = fresh[:n_holdout]
        fresh = fresh[n_holdout:]
    else:
        new_holdout = []

    sample_cache: dict[str, DatasetSample] = {}
    for p in new_holdout:
        _upsert_sample(db, image_path=p, split="holdout", dataset_version=None, is_frozen=True, cache=sample_cache)

    # Remaining fresh images: train / val split
    rng.shuffle(fresh)
    n_val = int(round(len(fresh) * cfg_val_ratio))
    val_paths = fresh[:n_val]
    train_paths = fresh[n_val:]

    # Pin the split on the sample record (only for newly assigned images)
    for p in train_paths:
        _upsert_sample(db, image_path=p, split="train", dataset_version=None, is_frozen=True, cache=sample_cache)
    for p in val_paths:
        _upsert_sample(db, image_path=p, split="val", dataset_version=None, is_frozen=True, cache=sample_cache)

    # --- 3. Class vocabulary --------------------------------------------
    class_names: list[str] = []
    seen: set[str] = set()
    for det in all_detections:
        if det.image_path not in set(train_paths + val_paths):
            continue
        if det.status == "rejected" and not include_rejected:
            continue
        if det.class_name not in seen:
            seen.add(det.class_name)
            class_names.append(det.class_name)
    class_names.sort()
    if not class_names:
        class_names = ["object"]
    class_to_id = {name: i for i, name in enumerate(class_names)}

    # --- 4. Write dataset tree ------------------------------------------
    dataset_version = _new_version(name, candidate_images)
    runtime_root = Path(settings.upload_dir).parent.resolve()
    datasets_root = (runtime_root / "datasets").resolve()
    datasets_root.mkdir(parents=True, exist_ok=True)
    root = (datasets_root / dataset_version).resolve()
    if root.exists():
        shutil.rmtree(root)
    for split in ("train", "val"):
        (root / "images" / split).mkdir(parents=True, exist_ok=True)
        (root / "labels" / split).mkdir(parents=True, exist_ok=True)

    written_images = 0
    written_labels = 0

    def _write_split(image_paths: list[str], split: str) -> None:
        nonlocal written_images, written_labels
        for image_rel in image_paths:
            image_abs = (runtime_root / image_rel).resolve()
            if not image_abs.is_file():
                logger.warning("image missing, skipping: %s", image_rel)
                continue
            width, height = _read_image_size(image_abs)
            if width <= 0 or height <= 0:
                continue

            stem = f"{written_images:06d}_{Path(image_rel).stem}"
            dst_img = root / "images" / split / f"{stem}{Path(image_rel).suffix.lower()}"
            shutil.copy2(image_abs, dst_img)
            written_images += 1

            # Label file: one line per CORRECTED detection.
            # Rejected boxes are NOT written — the image becomes a negative
            # sample (empty label file) which YOLO handles natively.
            lines: list[str] = []
            for det in by_image.get(image_rel, []):
                if det.status != "corrected":
                    continue
                cls_id = class_to_id.get(det.class_name, 0)
                cx = ((det.x1 + det.x2) / 2.0) / width
                cy = ((det.y1 + det.y2) / 2.0) / height
                bw = (det.x2 - det.x1) / width
                bh = (det.y2 - det.y1) / height
                cx = min(max(cx, 0.0), 1.0)
                cy = min(max(cy, 0.0), 1.0)
                bw = min(max(bw, 0.0), 1.0)
                bh = min(max(bh, 0.0), 1.0)
                lines.append(f"{cls_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")

            dst_lbl = root / "labels" / split / f"{stem}.txt"
            dst_lbl.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
            written_labels += 1

    _write_split(train_paths, "train")
    _write_split(val_paths, "val")

    # --- 5. data.yaml ----------------------------------------------------
    data_yaml = "\n".join(
        [
            f"path: {root.as_posix()}",
            "train: images/train",
            "val: images/val",
            "names:",
            *[f"  {i}: {name}" for i, name in enumerate(class_names)],
            "",
        ]
    )
    (root / "data.yaml").write_text(data_yaml, encoding="utf-8")

    # --- 6. Persist export record --------------------------------------
    version_row = DatasetExport(
        dataset_version=dataset_version,
        name=name,
        total_images=written_images,
        total_labels=written_labels,
        train_images=len(train_paths),
        val_images=len(val_paths),
        holdout_images=len(new_holdout),
        class_names=json.dumps(class_names, ensure_ascii=False),
        val_ratio=cfg_val_ratio,
        seed=cfg_seed,
        status="done",
        path=str(root.relative_to(runtime_root)),
        created_by=operator,
    )
    db.add(version_row)
    for p in train_paths + val_paths:
        _upsert_sample(
            db,
            image_path=p,
            split=_split_of(p, train_paths, val_paths),
            dataset_version=dataset_version,
            is_frozen=True,
            cache=sample_cache,
        )
    db.commit()
    db.refresh(version_row)

    return {
        "dataset_version": dataset_version,
        "path": version_row.path,
        "train_images": written_images - version_row.val_images,
        "val_images": version_row.val_images,
        "holdout_images": version_row.holdout_images,
        "total_labels": written_labels,
        "class_names": class_names,
    }


def pending_count(db: Session) -> dict:
    """How many corrected-but-unexported images await export."""
    exported = {
        row.image_path
        for row in db.query(DatasetSample.image_path).filter(DatasetSample.dataset_version.isnot(None)).all()
    }
    rows = db.query(Detection.image_path).filter(Detection.status != "pending").distinct().all()
    all_images = {r[0] for r in rows}
    pending = [p for p in all_images if p not in exported]

    holdout = db.query(DatasetSample).filter(DatasetSample.split == "holdout").count()
    return {
        "pending_images": len(pending),
        "holdout_images": holdout,
        "sample_preview": pending[:10],
    }


def list_exports(db: Session, page: int = 1, page_size: int = 20) -> dict:
    q = db.query(DatasetExport)
    total = q.count()
    rows = q.order_by(DatasetExport.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    pages = (total + page_size - 1) // page_size if total else 0
    return {"items": rows, "total": total, "page": page, "page_size": page_size, "pages": pages}


def get_export(db: Session, dataset_version: str) -> DatasetExport:
    row = db.query(DatasetExport).filter(DatasetExport.dataset_version == dataset_version).first()
    if row is None:
        raise AppError(Err.NOT_FOUND, f"dataset not found: {dataset_version}", 404)
    return row


def holdout_list(db: Session, page: int = 1, page_size: int = 50) -> dict:
    q = db.query(DatasetSample).filter(DatasetSample.split == "holdout")
    total = q.count()
    rows = q.order_by(DatasetSample.id).offset((page - 1) * page_size).limit(page_size).all()
    pages = (total + page_size - 1) // page_size if total else 0
    return {"items": rows, "total": total, "page": page, "page_size": page_size, "pages": pages}
