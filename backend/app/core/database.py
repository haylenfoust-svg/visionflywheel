"""SQLAlchemy engine / session / Base — sync ORM for simplicity at M1.

Endpoints using `def` run in FastAPI's threadpool; SQLite is configured
with `check_same_thread=False` for that reason.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _build_engine():
    settings = get_settings()
    kwargs: dict = {"future": True}
    if settings.database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(settings.database_url, **kwargs)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables (idempotent). Alembic will replace this at M2."""
    from app import models  # noqa: F401 — ensure all ORM modules are registered

    Base.metadata.create_all(bind=engine)
