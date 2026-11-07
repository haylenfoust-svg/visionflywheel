"""Application lifecycle hooks — warm up resources on startup."""

from pathlib import Path

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.database import init_db


def _ensure_runtime_dirs() -> None:
    settings = get_settings()
    for path in (settings.upload_dir, settings.result_dir, settings.dataset_dir, settings.weights_dir):
        Path(path).mkdir(parents=True, exist_ok=True)


def register_lifecycle(app: FastAPI) -> None:
    @app.on_event("startup")
    def _startup() -> None:
        _ensure_runtime_dirs()
        init_db()

    @app.on_event("shutdown")
    def _shutdown() -> None:
        pass
