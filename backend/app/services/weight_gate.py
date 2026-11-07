"""Weight-switch regression gate (P2.1).

Before a new checkpoint becomes the default, the gate compares its
`holdout_map` (and optionally mAP50 / precision / recall from the
training curves) against the current default. A switch is allowed only
when the target is **not worse** than the baseline — a strict regression
guard for the data flywheel.

Policy (configurable via `weight_gate_policy`):
  - `block`:   403 when the target regresses
  - `warn`:    allow the switch but flag the response
  - `off`:     allow any switch (legacy behavior)

Delta thresholds:
  - `min_map_delta`: target - baseline must be >= this (default 0.0,
    i.e. target must be at least as good)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import AppError, Err
from app.models.weight import Weight
from app.services import weight_manager

logger = logging.getLogger(__name__)

ALLOWED_POLICIES = ("block", "warn", "off")


@dataclass
class GateResult:
    allowed: bool
    policy: str
    baseline_map: float | None
    target_map: float | None
    delta: float | None
    message: str
    warnings: list[str]


def _get_policy(db: Session) -> str:
    try:
        from app.services.config_service import get_config_service

        policy = get_config_service().get(db, "weight_gate_policy")
        return str(policy) if policy in ALLOWED_POLICIES else "block"
    except Exception:
        return "block"


def _get_min_delta(db: Session) -> float:
    try:
        from app.services.config_service import get_config_service

        delta = get_config_service().get(db, "weight_gate_min_map_delta")
        return float(delta) if delta is not None else 0.0
    except Exception:
        return 0.0


def evaluate_switch(db: Session, target_id: int) -> GateResult:
    """Evaluate whether `target_id` may replace the current default."""
    target = db.query(Weight).filter(Weight.id == target_id).first()
    if target is None:
        raise AppError(Err.NOT_FOUND, f"weight not found: {target_id}", 404)

    baseline = db.query(Weight).filter(Weight.is_default.is_(True)).first()
    policy = _get_policy(db)
    min_delta = _get_min_delta(db)

    # No current default -> always allow
    if baseline is None or baseline.id == target_id:
        return GateResult(
            allowed=True,
            policy=policy,
            baseline_map=None,
            target_map=target.holdout_map,
            delta=None,
            message="no current default — switch allowed",
            warnings=[],
        )

    baseline_map = baseline.holdout_map
    target_map = target.holdout_map

    # If either side lacks a holdout metric we cannot judge — allow with warning
    if baseline_map is None or target_map is None:
        return GateResult(
            allowed=True,
            policy=policy,
            baseline_map=baseline_map,
            target_map=target_map,
            delta=None,
            message="holdout metric missing on one or both sides — switch allowed with warning",
            warnings=[
                f"baseline holdout_map={baseline_map}, target holdout_map={target_map} — comparison skipped"
            ],
        )

    delta = target_map - baseline_map
    passed = delta >= min_delta

    if passed:
        return GateResult(
            allowed=True,
            policy=policy,
            baseline_map=baseline_map,
            target_map=target_map,
            delta=round(delta, 4),
            message=f"regression gate passed (delta {delta:+.4f} >= {min_delta:+.4f})",
            warnings=[],
        )

    # Regression detected
    message = (
        f"regression gate FAILED: target holdout_map {target_map:.4f} is "
        f"{abs(delta):.4f} below baseline {baseline_map:.4f} "
        f"(threshold {min_delta:+.4f})"
    )
    # Regression detected — evaluate_switch reports allowed=False
    # (gated_set_default raises 409 when policy=block).
    return GateResult(
        allowed=False,
        policy=policy,
        baseline_map=baseline_map,
        target_map=target_map,
        delta=round(delta, 4),
        message=message,
        warnings=[message],
    )


def gated_set_default(
    db: Session,
    weight_id: int,
    *,
    operator: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Set the default weight, applying the regression gate first.

    `force=True` bypasses the gate (admin override) and records it in the
    result so the audit trail shows the override.
    """
    if force:
        result = weight_manager.set_default(db, weight_id, operator=operator)
        result["gate"] = {"allowed": True, "policy": "bypassed", "forced": True,
                          "message": "force flag set — regression gate bypassed"}
        return result

    gate = evaluate_switch(db, weight_id)
    if not gate.allowed and _get_policy(db) == "block":
        raise AppError(Err.CONFLICT, gate.message, 409)
    result = weight_manager.set_default(db, weight_id, operator=operator)
    result["gate"] = {
        "allowed": gate.allowed,
        "policy": gate.policy,
        "baseline_map": gate.baseline_map,
        "target_map": gate.target_map,
        "delta": gate.delta,
        "message": gate.message,
        "warnings": gate.warnings,
    }
    return result
