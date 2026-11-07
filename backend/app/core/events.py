"""Application lifecycle hooks — warm up resources on startup."""

from pathlib import Path

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.database import SessionLocal, init_db


def _ensure_runtime_dirs() -> None:
    settings = get_settings()
    for path in (settings.upload_dir, settings.result_dir, settings.dataset_dir, settings.weights_dir):
        Path(path).mkdir(parents=True, exist_ok=True)


def _seed_rbac() -> None:
    """Idempotently seed permissions + default roles (B端-2)."""
    try:
        from app.services.auth_service import seed_permissions_and_roles

        db = SessionLocal()
        try:
            result = seed_permissions_and_roles(db)
            if result["permissions_created"] or result["roles_created"]:
                print(  # noqa: T201 — startup log
                    f"[rbac] seeded permissions={result['permissions_created']} "
                    f"roles={result['roles_created']}"
                )
        finally:
            db.close()
    except Exception as exc:  # pragma: no cover — best-effort seed
        print(f"[rbac] seed skipped: {exc}")  # noqa: T201 — startup log


def register_lifecycle(app: FastAPI) -> None:
    @app.on_event("startup")
    def _startup() -> None:
        _ensure_runtime_dirs()
        init_db()
        _seed_rbac()

    @app.on_event("shutdown")
    def _shutdown() -> None:
        pass
