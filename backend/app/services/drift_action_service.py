"""Drift → action loop (P2.3).

When drift is detected, the loop:
  1. Sends an alert via the configured channels (email / webhook).
  2. Emits a **rollback recommendation** — the most recent checkpoint that
     is *not* drifting (best holdout_map among the non-default weights).
  3. Optionally triggers a retraining job (admin-gated; off by default).

The action report is returned to the caller and surfaced on the Dashboard
so an operator can accept the recommendation with one click.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.task import Task
from app.models.user import User
from app.models.weight import Weight
from app.services.drift_service import drift_report
from app.services.observability import send_alert

logger = logging.getLogger(__name__)


def _recommend_rollback(db: Session) -> dict[str, Any]:
    """Pick the best non-default checkpoint as a rollback candidate."""
    candidates = (
        db.query(Weight)
        .filter(Weight.is_default.is_(False), Weight.holdout_map.is_not(None))
        .order_by(Weight.holdout_map.desc())
        .limit(3)
        .all()
    )
    if not candidates:
        return {"available": False, "message": "no non-default checkpoints with holdout_map"}
    best = candidates[0]
    return {
        "available": True,
        "weight_id": best.id,
        "filename": best.filename,
        "holdout_map": best.holdout_map,
        "dataset_version": best.dataset_version,
        "message": f"rollback candidate: {best.filename} (holdout_map={best.holdout_map:.4f})",
        "alternatives": [
            {"weight_id": c.id, "filename": c.filename, "holdout_map": c.holdout_map}
            for c in candidates[1:]
        ],
    }


def _trigger_retrain(db: Session, *, dataset_version: str | None = None, operator: str | None = None) -> dict[str, Any]:
    """Submit a retraining job (admin-only; off by default)."""
    try:
        from app.services.train_service import create_training

        run = create_training(
            db,
            dataset_version=dataset_version or "",
            epochs=10,
            operator=operator,
        )
        return {"triggered": True, "run_id": run.id, "status": run.status}
    except Exception as exc:
        logger.warning("retrain trigger failed: %s", exc)
        return {"triggered": False, "error": str(exc)}


def run_drift_action_loop(
    db: Session,
    user: User,
    *,
    days: int = 30,
    notify: bool = True,
    auto_retrain: bool = False,
) -> dict[str, Any]:
    """End-to-end drift detection → alert → recommendation → optional retrain."""
    report = drift_report(db, user, days=days)
    actions: list[dict[str, Any]] = []

    # 1) Alert
    if notify and report["status"] == "drifting":
        alert_body = "\n".join(f"- [{a['severity']}] {a['message']}" for a in report["alerts"])
        context = {
            "window_days": days,
            "confidence_delta": report["confidence_drift"]["delta"],
            "class_jsd": report["class_drift"]["js_divergence"],
            "fp_rate_delta": report["correction_drift"]["fp_rate_delta"],
        }
        alert_result = send_alert(
            subject="模型漂移检测",
            body=f"VisionFlywheel 检测到模型漂移：\n{alert_body}",
            severity="critical",
            context=context,
        )
        actions.append({"type": "alert", "result": alert_result})

    # 2) Rollback recommendation
    rollback = _recommend_rollback(db)
    actions.append({"type": "rollback_recommendation", "result": rollback})

    # 3) Optional auto-retrain (admin-gated)
    retrain = {"triggered": False, "skipped": "auto_retrain disabled"}
    if auto_retrain and report["status"] == "drifting":
        # Use the most recent dataset version
        latest = (
            db.query(Task)
            .order_by(Task.id.desc())
            .first()
        )
        dataset_version = None
        if latest is not None:
            # Find any DatasetExport for this dataset
            from app.models.dataset import DatasetExport

            export = (
                db.query(DatasetExport)
                .order_by(DatasetExport.id.desc())
                .first()
            )
            if export is not None:
                dataset_version = export.dataset_version
        if dataset_version:
            retrain = _trigger_retrain(db, dataset_version=dataset_version, operator=user.username)
            actions.append({"type": "auto_retrain", "result": retrain})

    return {
        "report": report,
        "actions": actions,
        "summary": {
            "drifting": report["status"] == "drifting",
            "alerted": any(a["type"] == "alert" for a in actions),
            "rollback_available": rollback.get("available", False),
            "retrained": retrain.get("triggered", False),
        },
    }
