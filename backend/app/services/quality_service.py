"""Quality metrics for the data-flywheel (AI-2).

Computes the signals that tell us whether the flywheel is actually
improving the model:

  - **误检率 (false-positive rate)**:  rejected / total detections
  - **漏检率 (miss rate, proxy)**:     added (manual) / total detections
                                       (a rough proxy — true miss rate needs
                                        a labelled ground-truth set)
  - **人工校正率 (correction rate)**:  corrected / total detections
  - **校正吞吐 (per-day trend)**:      corrections/day over the last N days

All queries honour the caller's org/team scope so each tenant sees only
their own quality signals.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.correction import Correction
from app.models.detection import Detection
from app.models.user import User
from app.services.scope_service import get_user_scope_filter, visible_task_ids_subquery


def _days_ago(n: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=n)


def quality_metrics(db: Session, user: User, *, days: int = 30) -> dict[str, Any]:
    """Compute the flywheel-quality dashboard payload."""
    scope_filter = get_user_scope_filter(db, user)
    visible_tasks = visible_task_ids_subquery(user, db)

    def _scoped(q):
        if scope_filter.is_global:
            return q
        return q.filter(Detection.task_id.in_(visible_tasks))

    def _scoped_corr(q):
        if scope_filter.is_global:
            return q
        return q.filter(Correction.task_id.in_(visible_tasks))

    # ---------- aggregate rates ----------
    total = _scoped(db.query(func.count(Detection.id))).scalar() or 0
    rejected = (
        _scoped(db.query(func.count(Detection.id)).filter(Detection.status == "rejected")).scalar() or 0
    )
    corrected = (
        _scoped(db.query(func.count(Detection.id)).filter(Detection.status == "corrected")).scalar() or 0
    )
    pending = (
        _scoped(db.query(func.count(Detection.id)).filter(Detection.status == "pending")).scalar() or 0
    )
    added = (
        _scoped(db.query(func.count(Detection.id)).filter(Detection.source == "manual")).scalar() or 0
    )

    fp_rate = (rejected / total) if total else 0.0
    miss_rate_proxy = (added / total) if total else 0.0
    correction_rate = (corrected / total) if total else 0.0

    # ---------- per-day trend ----------
    cutoff = _days_ago(days)
    det_trend_rows = (
        _scoped(
            db.query(func.date(Detection.created_at).label("d"), func.count(Detection.id))
            .filter(Detection.created_at >= cutoff)
            .group_by("d")
        )
        .order_by("d")
        .all()
    )
    det_trend = [{"date": str(d), "count": c} for d, c in det_trend_rows]

    corr_trend_rows = (
        _scoped_corr(
            db.query(func.date(Correction.created_at).label("d"), func.count(Correction.id))
            .filter(Correction.created_at >= cutoff)
            .group_by("d")
        )
        .order_by("d")
        .all()
    )
    corr_trend = [{"date": str(d), "count": c} for d, c in corr_trend_rows]

    # ---------- per-action breakdown ----------
    action_rows = (
        _scoped_corr(
            db.query(Correction.action, func.count(Correction.id)).group_by(Correction.action)
        )
        .order_by(func.count(Correction.id).desc())
        .all()
    )
    by_action = dict(action_rows)

    # ---------- rolling 7-day vs prior 7-day ----------
    last7 = _days_ago(7)
    prior_start = _days_ago(14)
    det_last7 = (
        _scoped(db.query(func.count(Detection.id)).filter(Detection.created_at >= last7)).scalar() or 0
    )
    det_prior7 = (
        _scoped(
            db.query(func.count(Detection.id))
            .filter(Detection.created_at >= prior_start, Detection.created_at < last7)
        ).scalar()
        or 0
    )
    corr_last7 = (
        _scoped_corr(db.query(func.count(Correction.id)).filter(Correction.created_at >= last7)).scalar()
        or 0
    )
    corr_prior7 = (
        _scoped_corr(
            db.query(func.count(Correction.id))
            .filter(Correction.created_at >= prior_start, Correction.created_at < last7)
        ).scalar()
        or 0
    )

    def _delta(cur: int, prior: int) -> dict[str, Any]:
        if prior == 0:
            return {"value": cur, "delta": cur if cur else 0, "pct": 100.0 if cur else 0.0}
        pct = ((cur - prior) / prior) * 100.0
        return {"value": cur, "delta": cur - prior, "pct": round(pct, 1)}

    return {
        "totals": {
            "detections": total,
            "rejected": rejected,
            "corrected": corrected,
            "pending": pending,
            "added": added,
        },
        "rates": {
            "false_positive_rate": round(fp_rate, 4),
            "miss_rate_proxy": round(miss_rate_proxy, 4),
            "correction_rate": round(correction_rate, 4),
        },
        "trend": {
            "detections": det_trend,
            "corrections": corr_trend,
        },
        "by_action": by_action,
        "window": {
            "days": days,
            "detections": _delta(det_last7, det_prior7),
            "corrections": _delta(corr_last7, corr_prior7),
        },
    }
