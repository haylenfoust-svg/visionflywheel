"""Aggregated statistics for the dashboard (M5.2)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.correction import Correction
from app.models.dataset import DatasetExport
from app.models.detection import Detection
from app.models.feedback import FeedbackTicket
from app.models.task import Task
from app.models.weight import Weight


def _days_ago(n: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=n)


def dashboard_overview(db: Session) -> dict:
    """Single payload for the dashboard — one query round per section."""
    now = datetime.now(timezone.utc)

    total_tasks = db.query(func.count(Task.id)).scalar() or 0
    total_detections = db.query(func.count(Detection.id)).scalar() or 0
    total_corrections = db.query(func.count(Correction.id)).scalar() or 0
    total_datasets = db.query(func.count(DatasetExport.id)).scalar() or 0
    total_weights = db.query(func.count(Weight.id)).scalar() or 0
    open_tickets = (
        db.query(func.count(FeedbackTicket.id)).filter(FeedbackTicket.status == "open").scalar() or 0
    )

    # Today
    today = now.date()
    today_tasks = (
        db.query(func.count(Task.id)).filter(func.date(Task.created_at) == today).scalar() or 0
    )
    today_detections = (
        db.query(func.count(Detection.id)).filter(func.date(Detection.created_at) == today).scalar() or 0
    )
    today_corrections = (
        db.query(func.count(Correction.id)).filter(func.date(Correction.created_at) == today).scalar() or 0
    )

    # Detections by status
    status_rows = db.query(Detection.status, func.count(Detection.id)).group_by(Detection.status).all()
    by_status = dict(status_rows)

    # Class distribution (top 10)
    class_rows = (
        db.query(Detection.class_name, Detection.class_name_zh, func.count(Detection.id))
        .group_by(Detection.class_name, Detection.class_name_zh)
        .order_by(func.count(Detection.id).desc())
        .limit(10)
        .all()
    )
    by_class = [
        {"class_name": n, "class_name_zh": zh, "count": c} for n, zh, c in class_rows
    ]

    # Detections per day (last 14 days) — bucketed by date
    per_day_rows = (
        db.query(func.date(Detection.created_at).label("d"), func.count(Detection.id))
        .filter(Detection.created_at >= _days_ago(14))
        .group_by("d")
        .order_by("d")
        .all()
    )
    per_day = [{"date": str(d), "count": c} for d, c in per_day_rows]

    # Corrections per day (last 14)
    corr_per_day_rows = (
        db.query(func.date(Correction.created_at).label("d"), func.count(Correction.id))
        .filter(Correction.created_at >= _days_ago(14))
        .group_by("d")
        .order_by("d")
        .all()
    )
    corr_per_day = [{"date": str(d), "count": c} for d, c in corr_per_day_rows]

    # Action breakdown
    action_rows = (
        db.query(Correction.action, func.count(Correction.id))
        .group_by(Correction.action)
        .order_by(func.count(Correction.id).desc())
        .all()
    )
    by_action = dict(action_rows)

    # Average confidence
    avg_conf = db.query(func.avg(Detection.confidence)).scalar() or 0.0

    # Task status breakdown
    task_status_rows = db.query(Task.status, func.count(Task.id)).group_by(Task.status).all()
    by_task_status = dict(task_status_rows)

    # Recent activity (last 10 tasks + corrections)
    recent_tasks = (
        db.query(Task).order_by(Task.id.desc()).limit(5).all()
    )
    recent_corrections = (
        db.query(Correction).order_by(Correction.id.desc()).limit(5).all()
    )

    return {
        "totals": {
            "tasks": total_tasks,
            "detections": total_detections,
            "corrections": total_corrections,
            "datasets": total_datasets,
            "weights": total_weights,
            "open_tickets": open_tickets,
        },
        "today": {
            "tasks": today_tasks,
            "detections": today_detections,
            "corrections": today_corrections,
        },
        "by_status": by_status,
        "by_task_status": by_task_status,
        "by_class": by_class,
        "by_action": by_action,
        "per_day": per_day,
        "corr_per_day": corr_per_day,
        "avg_confidence": round(float(avg_conf), 4),
        "recent_tasks": [
            {
                "id": t.id,
                "type": t.type,
                "status": t.status,
                "detector_mode": t.detector_mode,
                "total_items": t.total_items,
                "detections": len(t.detections),
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in recent_tasks
        ],
        "recent_corrections": [
            {
                "id": c.id,
                "action": c.action,
                "detection_id": c.detection_id,
                "operator": c.operator,
                "comment": c.comment,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in recent_corrections
        ],
    }
