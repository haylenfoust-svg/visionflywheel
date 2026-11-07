"""Training metrics extraction (M4 / AI-2 support).

Parses YOLO's `results.csv` (produced by `yolo detect train`) and surfaces
the mAP / precision / recall / loss curves used by the model-comparison UI.
Falls back gracefully when the CSV is missing (e.g. a checkpoint registered
without a training run).
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AppError, Err
from app.models.dataset import TrainingRun
from app.models.weight import Weight

logger = logging.getLogger(__name__)

# Columns we surface — YOLO writes these with a leading space in the header
_METRIC_COLUMNS = {
    "epoch": "epoch",
    "metrics/precision(B)": "precision",
    "metrics/recall(B)": "recall",
    "metrics/mAP50(B)": "map50",
    "metrics/mAP50-95(B)": "map50_95",
    "val/box_loss": "val_box_loss",
    "val/cls_loss": "val_cls_loss",
    "val/dfl_loss": "val_dfl_loss",
    "train/box_loss": "train_box_loss",
    "train/cls_loss": "train_cls_loss",
    "train/dfl_loss": "train_dfl_loss",
}


def _read_results_csv(csv_path: Path) -> list[dict[str, float]]:
    """Read YOLO's results.csv into a list of per-epoch dicts."""
    if not csv_path.is_file():
        return []
    rows: list[dict[str, float]] = []
    try:
        with csv_path.open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for raw in reader:
                # YOLO pads header names with a leading space
                cleaned = {k.strip(): v for k, v in raw.items() if k is not None}
                out: dict[str, float] = {}
                for yolo_key, our_key in _METRIC_COLUMNS.items():
                    raw_val = cleaned.get(yolo_key) or cleaned.get(yolo_key.strip())
                    if raw_val is None or raw_val == "":
                        continue
                    try:
                        out[our_key] = float(raw_val)
                    except ValueError:
                        continue
                if "epoch" in out:
                    rows.append(out)
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("failed to parse %s: %s", csv_path, exc)
    return rows


def _find_results_csv(dataset_version: str, run_name: str | None) -> Path | None:
    """Locate the results.csv produced by a training run."""
    settings = get_settings()
    runtime_root = Path(settings.upload_dir).parent.resolve()
    dataset_root = runtime_root / "datasets" / dataset_version
    candidates = []
    if run_name:
        candidates.append(dataset_root / "runs" / run_name / "results.csv")
    # Fall back to any results.csv under the dataset's runs/ directory
    runs_dir = dataset_root / "runs"
    if runs_dir.is_dir():
        candidates.extend(sorted(runs_dir.rglob("results.csv"), reverse=True))
    for c in candidates:
        if c.is_file():
            return c
    return None


def training_curves(db: Session, weight_id: int) -> dict[str, Any]:
    """Return the training curves + summary for a registered weight."""
    w = db.query(Weight).filter(Weight.id == weight_id).first()
    if w is None:
        raise AppError(Err.NOT_FOUND, f"weight not found: {weight_id}", 404)

    run = None
    if w.dataset_version:
        run = (
            db.query(TrainingRun)
            .filter(TrainingRun.dataset_version == w.dataset_version)
            .order_by(TrainingRun.id.desc())
            .first()
        )

    csv_path = None
    if run is not None and w.dataset_version:
        csv_path = _find_results_csv(w.dataset_version, run.name)

    epochs = _read_results_csv(csv_path) if csv_path else []

    summary: dict[str, Any] = {
        "weight_id": w.id,
        "weight_filename": w.filename,
        "dataset_version": w.dataset_version,
        "holdout_map": w.holdout_map,
        "class_count": w.class_count,
        "has_curves": bool(epochs),
        "total_epochs": len(epochs),
    }
    if epochs:
        # Last-epoch summary
        last = epochs[-1]
        summary.update(
            {
                "final_map50_95": last.get("map50_95"),
                "final_map50": last.get("map50"),
                "final_precision": last.get("precision"),
                "final_recall": last.get("recall"),
                "best_map50_95": max(e.get("map50_95", 0.0) for e in epochs),
            }
        )

    return {"summary": summary, "epochs": epochs}


def training_history(db: Session, weight_id: int, *, limit: int = 5) -> list[dict[str, Any]]:
    """Recent training runs for a given weight's dataset version."""
    w = db.query(Weight).filter(Weight.id == weight_id).first()
    if w is None:
        raise AppError(Err.NOT_FOUND, f"weight not found: {weight_id}", 404)
    if not w.dataset_version:
        return []
    rows = (
        db.query(TrainingRun)
        .filter(TrainingRun.dataset_version == w.dataset_version)
        .order_by(TrainingRun.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "name": r.name,
            "status": r.status,
            "epochs": r.epochs,
            "imgsz": r.imgsz,
            "batch": r.batch,
            "holdout_map": r.holdout_map,
            "best_weight_path": r.best_weight_path,
            "error_message": r.error_message,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
