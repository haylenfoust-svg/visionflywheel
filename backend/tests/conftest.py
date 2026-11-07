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

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


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
