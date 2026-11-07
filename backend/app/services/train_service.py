"""Training service — wraps `yolo detect train` (PRD FR-6).

Training is gated on `detector_mode == 'yolo'` (ADR-002); if ultralytics is
missing we refuse with 403 FALLBACK_NO_TRAIN rather than silently failing.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.exceptions import AppError, Err
from app.models.dataset import DatasetExport, TrainingRun
from app.services import weight_manager
from app.services.detector_factory import detector_mode

logger = logging.getLogger(__name__)


def _check_trainable() -> None:
    if detector_mode() != "yolo":
        raise AppError(
            Err.FALLBACK_NO_TRAIN,
            "training requires the YOLO detector (install requirements-ml.txt)",
            403,
        )


def create_training(
    db: Session,
    *,
    dataset_version: str,
    base_weight: str = "yolov8n.pt",
    epochs: int = 100,
    imgsz: int = 640,
    batch: int = 16,
    name: str | None = None,
    operator: str | None = None,
) -> TrainingRun:
    _check_trainable()

    export = db.query(DatasetExport).filter(DatasetExport.dataset_version == dataset_version).first()
    if export is None:
        raise AppError(Err.NOT_FOUND, f"dataset not found: {dataset_version}", 404)
    if export.status != "done":
        raise AppError(Err.CONFLICT, f"dataset {dataset_version} is not ready", 409)

    run = TrainingRun(
        dataset_version=dataset_version,
        base_weight=base_weight,
        name=name or f"run-{uuid.uuid4().hex[:6]}",
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        status="pending",
        progress=0.0,
        started_by=operator,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # Kick off training in a background thread (non-blocking)
    thread = threading.Thread(target=_run_training, args=(run.id,), daemon=True)
    thread.start()
    return run


def _run_training(run_id: int) -> None:
    """Worker thread — opens its own session because the caller's is gone."""
    db = SessionLocal()
    try:
        run = db.query(TrainingRun).filter(TrainingRun.id == run_id).first()
        if run is None:
            return
        export = db.query(DatasetExport).filter(DatasetExport.dataset_version == run.dataset_version).first()
        if export is None:
            run.status = "failed"
            run.error_message = "dataset disappeared"
            db.commit()
            return

        settings = get_settings()
        runtime_root = Path(settings.upload_dir).parent.resolve()
        dataset_dir = runtime_root / export.path
        data_yaml = dataset_dir / "data.yaml"
        if not data_yaml.is_file():
            run.status = "failed"
            run.error_message = f"data.yaml missing: {data_yaml}"
            db.commit()
            return

        run.status = "running"
        db.commit()

        work_dir = dataset_dir / "runs"
        work_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            "yolo",
            "detect",
            "train",
            f"model={run.base_weight}",
            f"data={data_yaml}",
            f"epochs={run.epochs}",
            f"imgsz={run.imgsz}",
            f"batch={run.batch}",
            f"project={work_dir}",
            f"name={run.name}",
            "exist_ok=True",
            "verbose=False",
        ]
        logger.info("training start: %s", " ".join(cmd))
        started = time.perf_counter()
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=6 * 60 * 60,
        )
        elapsed = time.perf_counter() - started

        run.log_tail = (proc.stdout or "")[-4000:]
        if proc.returncode != 0:
            run.status = "failed"
            run.error_message = (proc.stderr or proc.stdout or "training failed")[-1000:]
            db.commit()
            return

        best = work_dir / run.name / "weights" / "best.pt"
        if not best.is_file():
            run.status = "failed"
            run.error_message = "training produced no best.pt"
            db.commit()
            return

        # Register the checkpoint and record the mAP from results.csv if present
        map_value = _read_map(work_dir / run.name / "results.csv")
        class_count = len(__import__("json").loads(export.class_names or "[]"))
        weight = weight_manager.register_trained(
            db,
            filename=f"best_{run.dataset_version}_{run.name}.pt",
            source_path=str(best),
            dataset_version=run.dataset_version,
            holdout_map=map_value,
            class_count=class_count,
            operator=run.started_by,
        )

        run.status = "done"
        run.progress = 1.0
        run.best_weight_path = weight.path
        run.holdout_map = map_value
        run.log_tail = f"{run.log_tail}\n---\ntrained in {elapsed:.1f}s"
        db.commit()
        logger.info("training done: run=%s weight=%s", run.id, weight.filename)
    except Exception as exc:
        logger.exception("training crashed")
        run = db.query(TrainingRun).filter(TrainingRun.id == run_id).first()
        if run is not None:
            run.status = "failed"
            run.error_message = str(exc)
            db.commit()
    finally:
        db.close()


def _read_map(results_csv: Path) -> float | None:
    """Best-effort mAP50-95 extraction from YOLO's results.csv."""
    if not results_csv.is_file():
        return None
    try:
        import csv

        best: float | None = None
        with results_csv.open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                for key in ("metrics/mAP50-95(B)", "metrics/mAP50-95"):
                    raw = (row.get(key) or "").strip()
                    if raw:
                        value = float(raw)
                        if best is None or value > best:
                            best = value
        return best
    except Exception:
        return None


def list_runs(db: Session, page: int = 1, page_size: int = 20) -> dict:
    q = db.query(TrainingRun)
    total = q.count()
    rows = q.order_by(TrainingRun.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    pages = (total + page_size - 1) // page_size if total else 0
    return {"items": rows, "total": total, "page": page, "page_size": page_size, "pages": pages}


def get_run(db: Session, run_id: int) -> TrainingRun:
    row = db.query(TrainingRun).filter(TrainingRun.id == run_id).first()
    if row is None:
        raise AppError(Err.NOT_FOUND, f"training run not found: {run_id}", 404)
    return row


def cancel_run(db: Session, run_id: int) -> TrainingRun:
    row = get_run(db, run_id)
    if row.status not in ("pending", "running"):
        raise AppError(Err.CONFLICT, f"cannot cancel run in status {row.status}", 409)
    row.status = "cancelled"
    db.commit()
    db.refresh(row)
    return row
