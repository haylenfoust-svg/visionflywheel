"""Shared pytest fixtures — in-memory SQLite, FastAPI TestClient, seeded admin."""

from __future__ import annotations

import os

# Point the test DB at a throwaway file BEFORE importing app modules.
os.environ.setdefault("VF_DATABASE_URL", "sqlite:///./runtime_data/test_app.db")
os.environ.setdefault("VF_SECRET_KEY", "test-secret-key-not-for-production")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import create_app
from app.models.user import User

TEST_USERNAME = "tester"
TEST_PASSWORD = "test-password-123"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin-password-123"


@pytest.fixture
def engine():
    """Fresh in-memory DB per test — keeps tests isolated."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def db_session(engine):
    testing_session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = testing_session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client(engine, db_session):
    """Client with an in-memory DB and the deterministic fallback detector."""
    # Force the fallback detector so tests don't depend on pretrained weights
    from app.services.detector_factory import force_fallback

    force_fallback(True)

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app = create_app()
    app.dependency_overrides[get_db] = _override_get_db

    # seed users once per session via the shared engine
    if not db_session.query(User).filter(User.username == ADMIN_USERNAME).first():
        db_session.add_all(
            [
                User(username=ADMIN_USERNAME, password_hash=hash_password(ADMIN_PASSWORD), role="admin"),
                User(username=TEST_USERNAME, password_hash=hash_password(TEST_PASSWORD), role="user"),
            ]
        )
        db_session.commit()

        # Seed RBAC catalog and give the tester user the `operator` role so
        # non-admin tests exercise the real permission matrix (B端-1).
        from app.services.auth_service import seed_permissions_and_roles

        seed_permissions_and_roles(db_session)
        from app.models.rbac import Role, UserRole

        operator_role = db_session.query(Role).filter(Role.code == "operator").first()
        tester_user = db_session.query(User).filter(User.username == TEST_USERNAME).first()
        if operator_role is not None and tester_user is not None:
            db_session.add(
                UserRole(
                    user_id=tester_user.id,
                    role_id=operator_role.id,
                    scope_type="global",
                    scope_id=None,
                )
            )
            db_session.commit()

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    force_fallback(False)


@pytest.fixture
def admin_token(client) -> str:
    resp = client.post("/api/auth/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


@pytest.fixture
def user_token(client) -> str:
    resp = client.post("/api/auth/login", json={"username": TEST_USERNAME, "password": TEST_PASSWORD})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]
