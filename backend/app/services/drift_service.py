"""Model drift monitoring (AI product line, AI-3).

Tracks statistical signals that indicate the live data distribution is
shifting away from what the model was trained on:

  - **Confidence drift**: the mean / p50 / p90 of prediction confidences
    over time. A sustained drop suggests the model is seeing unfamiliar
    inputs.
  - **Class-distribution drift**: the mix of predicted classes changing
    (e.g. one class vanishing, another exploding).
  - **Correction-rate drift**: false-positive / miss rates trending up
    is the *human-confirmed* signal that quality is degrading.

Drift is measured as the Jensen-Shannon divergence between a *reference*
window (the older slice) and a *recent* window (the newer slice) of
predictions. Values close to 0 mean "no drift"; sustained values above
the configured threshold raise an alert.
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.detection import Detection
from app.models.user import User
from app.services.scope_service import visible_task_ids_subquery

# Alert thresholds (tunable via config later)
CONFIDENCE_DROP_THRESHOLD = 0.15   # mean conf drop of 15%
JSD_THRESHOLD = 0.20                # JS divergence above this = drift
MIN_SAMPLES_PER_WINDOW = 20        # need enough data to judge


def _days_ago(n: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=n)


def _js_divergence(p: dict[str, float], q: dict[str, float]) -> float:
    """Jensen-Shannon divergence between two discrete distributions."""
    keys = set(p) | set(q)
    if not keys:
        return 0.0
    # Smooth by adding a tiny epsilon so missing keys don't blow up log()
    eps = 1e-12
    def _norm(d: dict[str, float]) -> dict[str, float]:
        total = sum(d.values()) or 1.0
        return {k: (d.get(k, 0) + eps) / (total + eps * len(keys)) for k in keys}

    p_n = _norm(p)
    q_n = _norm(q)
    m = {k: (p_n[k] + q_n[k]) / 2 for k in keys}

    def _kl(a: dict[str, float], b: dict[str, float]) -> float:
        return sum(a[k] * math.log2(a[k] / b[k]) for k in keys if a[k] > 0)

    return 0.5 * _kl(p_n, m) + 0.5 * _kl(q_n, m)


def _conf_stats(detections: list[Detection]) -> dict[str, float]:
    if not detections:
        return {"mean": 0.0, "p50": 0.0, "p90": 0.0, "n": 0}
    confs = sorted(d.confidence for d in detections)
    n = len(confs)
    return {
        "mean": sum(confs) / n,
        "p50": confs[n // 2],
        "p90": confs[int(n * 0.9)] if n > 1 else confs[-1],
        "n": n,
    }


def _class_dist(detections: list[Detection]) -> dict[str, float]:
    counter: Counter[str] = Counter(d.class_name for d in detections)
    total = sum(counter.values()) or 1
    return {k: v / total for k, v in counter.items()}


def _scoped_detections(db: Session, user: User, start: datetime, end: datetime) -> list[Detection]:
    visible = visible_task_ids_subquery(user, db)
    q = db.query(Detection).filter(Detection.created_at >= start, Detection.created_at < end)
    q = q.filter(Detection.task_id.in_(visible))
    return q.all()


def drift_report(db: Session, user: User, *, days: int = 30) -> dict[str, Any]:
    """Compute the drift dashboard payload."""
    now = datetime.now(timezone.utc)
    mid = now - timedelta(days=days // 2 or 1)
    start = now - timedelta(days=days)

    reference = _scoped_detections(db, user, start, mid)
    recent = _scoped_detections(db, user, mid, now)

    # ---- confidence drift ----
    ref_conf = _conf_stats(reference)
    rec_conf = _conf_stats(recent)
    conf_delta = rec_conf["mean"] - ref_conf["mean"]
    conf_drop_pct = (abs(conf_delta) / ref_conf["mean"] * 100) if ref_conf["mean"] > 0 else 0.0
    conf_drifted = ref_conf["n"] >= MIN_SAMPLES_PER_WINDOW and rec_conf["n"] >= MIN_SAMPLES_PER_WINDOW and conf_delta < -CONFIDENCE_DROP_THRESHOLD * max(ref_conf["mean"], 1e-6)

    # ---- class-distribution drift ----
    ref_classes = _class_dist(reference)
    rec_classes = _class_dist(recent)
    class_jsd = _js_divergence(ref_classes, rec_classes) if (reference and recent) else 0.0
    class_drifted = class_jsd > JSD_THRESHOLD and ref_conf["n"] >= MIN_SAMPLES_PER_WINDOW

    # ---- correction-rate drift (last 7d vs prior 7d) ----
    last7_start = now - timedelta(days=7)
    prior_start = now - timedelta(days=14)

    def _rate(start_d: datetime, end_d: datetime) -> dict[str, Any]:
        dets = _scoped_detections(db, user, start_d, end_d)
        total = len(dets)
        rejected = sum(1 for d in dets if d.status == "rejected")
        corrected = sum(1 for d in dets if d.status == "corrected")
        added = sum(1 for d in dets if d.source == "manual")
        return {
            "total": total,
            "rejected": rejected,
            "corrected": corrected,
            "added": added,
            "fp_rate": (rejected / total) if total else 0.0,
            "correction_rate": (corrected / total) if total else 0.0,
            "miss_proxy": (added / total) if total else 0.0,
        }

    last7 = _rate(last7_start, now)
    prior7 = _rate(prior_start, last7_start)

    fp_delta = last7["fp_rate"] - prior7["fp_rate"]
    corr_delta = last7["correction_rate"] - prior7["correction_rate"]
    correction_drifted = fp_delta > 0.10  # FP rate jumped > 10 percentage points

    # ---- overall verdict ----
    alerts: list[dict[str, Any]] = []
    if conf_drifted:
        alerts.append(
            {
                "kind": "confidence_drop",
                "severity": "warning",
                "message": f"平均置信度下降 {conf_drop_pct:.1f}%（{ref_conf['mean']:.2f} → {rec_conf['mean']:.2f}）",
                "delta": round(conf_delta, 4),
            }
        )
    if class_drifted:
        alerts.append(
            {
                "kind": "class_distribution",
                "severity": "warning",
                "message": f"类别分布漂移（JS 散度 {class_jsd:.3f} > {JSD_THRESHOLD}）",
                "delta": round(class_jsd, 4),
            }
        )
    if correction_drifted:
        alerts.append(
            {
                "kind": "false_positive_rate",
                "severity": "critical",
                "message": f"误检率突增（近 7 天 {last7['fp_rate']:.1%} vs 前 7 天 {prior7['fp_rate']:.1%}）",
                "delta": round(fp_delta, 4),
            }
        )

    status = "drifting" if alerts else "stable"

    return {
        "status": status,
        "window_days": days,
        "reference_window": {
            "start": start.isoformat(),
            "end": mid.isoformat(),
            "samples": ref_conf["n"],
            "confidence": ref_conf,
            "class_distribution": ref_classes,
        },
        "recent_window": {
            "start": mid.isoformat(),
            "end": now.isoformat(),
            "samples": rec_conf["n"],
            "confidence": rec_conf,
            "class_distribution": rec_classes,
        },
        "confidence_drift": {
            "delta": round(conf_delta, 4),
            "drop_pct": round(conf_drop_pct, 2),
            "threshold_pct": CONFIDENCE_DROP_THRESHOLD * 100,
            "drifted": conf_drifted,
        },
        "class_drift": {
            "js_divergence": round(class_jsd, 4),
            "threshold": JSD_THRESHOLD,
            "drifted": class_drifted,
        },
        "correction_drift": {
            "last7": last7,
            "prior7": prior7,
            "fp_rate_delta": round(fp_delta, 4),
            "correction_rate_delta": round(corr_delta, 4),
            "drifted": correction_drifted,
        },
        "alerts": alerts,
    }
