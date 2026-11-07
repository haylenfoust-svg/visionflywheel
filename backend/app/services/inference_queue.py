"""Async inference queue (P2.2).

Long-running inferences (batch uploads, video frames, large images) run
in a background thread pool so the HTTP request returns immediately with
a `job_id`. The frontend polls `/api/tasks/jobs/{job_id}` for progress
or subscribes via SSE (future). When the queue is empty the system
degrades gracefully to synchronous execution.

Design:
  - `InferenceJob` is an in-process job record (id, status, progress,
    result, error). For a multi-instance deployment, back this with
    Redis / Celery / RQ — the shape is identical.
  - `submit_job(...)` enqueues a callable; `get_job(id)` returns status.
  - Concurrency is capped by `max_workers` (default 2) to avoid OOM on
    CPU-only hosts.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_MAX_WORKERS = 2


@dataclass
class InferenceJob:
    id: str
    kind: str  # image | batch | video | train
    status: str = "queued"  # queued | running | done | failed | cancelled
    progress: float = 0.0
    result: Any = None
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)

    @property
    def is_terminal(self) -> bool:
        return self.status in ("done", "failed", "cancelled")


_jobs: dict[str, InferenceJob] = {}
_lock = threading.Lock()
_executor: ThreadPoolExecutor | None = None


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="vf-infer")
    return _executor


def submit_job(kind: str, fn: Callable[..., Any], *args: Any, meta: dict[str, Any] | None = None, **kwargs: Any) -> InferenceJob:
    """Enqueue a job and return its record immediately."""
    job = InferenceJob(id=uuid.uuid4().hex[:12], kind=kind, meta=meta or {})
    with _lock:
        _jobs[job.id] = job

    def _runner() -> None:
        job.status = "running"
        try:
            def _progress(p: float) -> None:
                job.progress = max(0.0, min(1.0, p))

            result = fn(*args, progress_callback=_progress, **kwargs)
            if job._cancel.is_set():
                job.status = "cancelled"
                return
            job.result = result
            job.progress = 1.0
            job.status = "done"
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            logger.exception("job %s (%s) failed", job.id, kind)

    _get_executor().submit(_runner)
    return job


def get_job(job_id: str) -> InferenceJob | None:
    with _lock:
        return _jobs.get(job_id)


def list_jobs(*, kind: str | None = None, limit: int = 50) -> list[InferenceJob]:
    with _lock:
        jobs = list(_jobs.values())
    if kind:
        jobs = [j for j in jobs if j.kind == kind]
    jobs.sort(key=lambda j: j.id, reverse=True)
    return jobs[:limit]


def cancel_job(job_id: str) -> bool:
    job = get_job(job_id)
    if job is None or job.is_terminal:
        return False
    job._cancel.set()
    job.status = "cancelled"
    return True


def job_to_dict(job: InferenceJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "progress": round(job.progress, 4),
        "result": job.result,
        "error": job.error,
        "meta": job.meta,
    }
