"""P2 endpoints — weight gate, async inference, drift action loop."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.envelope import EnvelopeRoute
from app.core.exceptions import AppError, Err
from app.services.inference_queue import (
    cancel_job,
    get_job,
    job_to_dict,
    list_jobs,
    submit_job,
)
from app.services.permission_service import require_permission
from app.services.weight_gate import evaluate_switch, gated_set_default

router = APIRouter(tags=["p2"], route_class=EnvelopeRoute)


# ---------- P2.1 Weight regression gate ----------
class GateSwitchRequest(BaseModel):
    force: bool = False


@router.get("/weights/{weight_id}/gate")
def gate_evaluate(
    weight_id: int,
    _u: CurrentUser,
    db: Session = Depends(get_db),
    _perm: object = Depends(require_permission("weight.read")),
) -> dict:
    """Evaluate whether a weight may become the new default."""
    gate = evaluate_switch(db, weight_id)
    return {
        "allowed": gate.allowed,
        "policy": gate.policy,
        "baseline_map": gate.baseline_map,
        "target_map": gate.target_map,
        "delta": gate.delta,
        "message": gate.message,
        "warnings": gate.warnings,
    }



@router.post("/weights/{weight_id}/switch-gated")
def gate_switch(
    weight_id: int,
    payload: GateSwitchRequest,
    admin: CurrentUser,
    db: Session = Depends(get_db),
    _perm: object = Depends(require_permission("weight.switch")),
) -> dict:
    """Switch default weight with the regression gate applied."""
    return gated_set_default(db, weight_id, operator=admin.username, force=payload.force)


# ---------- P2.2 Async inference queue ----------
@router.get("/tasks/jobs")
def jobs_list(
    _u: CurrentUser,
    kind: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
) -> list[dict]:
    jobs = list_jobs(kind=kind, limit=limit)
    return [job_to_dict(j) for j in jobs]


@router.get("/tasks/jobs/{job_id}")
def job_get(
    job_id: str,
    _u: CurrentUser,
) -> dict:
    job = get_job(job_id)
    if job is None:
        raise AppError(Err.NOT_FOUND, f"job not found: {job_id}", 404)
    return job_to_dict(job)


@router.post("/tasks/jobs/{job_id}/cancel")
def job_cancel(
    job_id: str,
    _u: CurrentUser,
    _perm: object = Depends(require_permission("task.write")),
) -> dict:
    ok = cancel_job(job_id)
    return {"cancelled": ok}


@router.post("/tasks/submit-async")
def submit_async(
    _u: CurrentUser,
    db: Session = Depends(get_db),
    _perm: object = Depends(require_permission("task.write")),
) -> dict:
    """Demonstration endpoint — submits a no-op async job to exercise the queue."""

    def _noop(progress_callback=None, **kwargs):
        if progress_callback:
            for p in (0.25, 0.5, 0.75, 1.0):
                progress_callback(p)
        return {"ok": True}

    job = submit_job("demo", _noop, meta={"submitted_by": _u.username})
    return job_to_dict(job)


# ---------- P2.3 Drift action loop ----------
@router.post("/stats/drift/action")
def drift_action(
    user: CurrentUser,
    db: Session = Depends(get_db),
    days: int = 30,
    notify: bool = True,
    auto_retrain: bool = False,
    _perm: object = Depends(require_permission("detection.read")),
) -> dict:
    """Run the drift detection → alert → rollback → optional retrain loop."""
    from app.services.drift_action_service import run_drift_action_loop

    return run_drift_action_loop(
        db,
        user,
        days=days,
        notify=notify,
        auto_retrain=auto_retrain,
    )
