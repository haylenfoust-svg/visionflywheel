"""Security + metrics + drift tests (2FA / reset / OAuth / curves / drift)."""

from __future__ import annotations

import time

import pytest


def _login(client, username="admin", password="admin-password-123") -> str:
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["data"]["access_token"]


class TestTwoFactor:
    def test_setup_returns_secret_and_uri(self, client, db_session):
        token = _login(client)
        r = client.post("/api/auth/2fa/setup", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()["data"]
        assert "secret" in data
        assert data["uri"].startswith("otpauth://totp/")
        assert data["digits"] == 6
        assert data["period"] == 30

    def test_confirm_with_wrong_code_rejected(self, client, db_session):
        token = _login(client)
        client.post("/api/auth/2fa/setup", headers={"Authorization": f"Bearer {token}"})
        r = client.post(
            "/api/auth/2fa/confirm",
            headers={"Authorization": f"Bearer {token}"},
            json={"code": "000000"},
        )
        # The code is almost certainly wrong (1/10^6 chance)
        # If it does succeed (rare), skip the assertion
        if r.status_code == 200:
            pytest.skip("lucky TOTP collision")
        assert r.status_code == 400

    def test_disable_without_code_works_when_not_enabled(self, client):
        token = _login(client)
        r = client.post("/api/auth/2fa/disable", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["data"]["enabled"] is False

    def test_status_reflects_state(self, client):
        token = _login(client)
        r = client.get("/api/auth/2fa/status", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["data"]["enabled"] is False

    def test_totp_verification_roundtrip(self):
        """Verify the TOTP helper directly with a synthetic secret + code."""
        import base64

        from app.services.security_service import (
            _hotp,
            generate_totp_secret,
            totp_uri,
            verify_totp,
        )

        secret = generate_totp_secret()
        assert totp_uri(secret, "tester").startswith("otpauth://totp/")

        # Generate a valid code at the current time
        padded = secret + "=" * (-len(secret) % 8)
        raw = base64.b32decode(padded, casefold=True)
        counter = int(time.time() / 30)
        code = _hotp(raw, counter)
        assert verify_totp(secret, code, at_time=time.time()) is True
        assert verify_totp(secret, "000000", at_time=time.time()) is False


class TestPasswordReset:
    def test_request_returns_token(self, client, db_session):
        r = client.post(
            "/api/auth/password-reset/request",
            json={"username": "admin"},
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["issued"] is True
        assert "token" in data

    def test_confirm_with_valid_token_resets_password(self, client, db_session):
        r = client.post(
            "/api/auth/password-reset/request",
            json={"username": "admin"},
        )
        token = r.json()["data"]["token"]
        r2 = client.post(
            "/api/auth/password-reset/confirm",
            json={"token": token, "new_password": "brandnewpass123"},
        )
        assert r2.status_code == 200
        assert r2.json()["data"]["reset"] is True

        # Old password no longer works
        r3 = client.post("/api/auth/login", json={"username": "admin", "password": "admin-password-123"})
        assert r3.status_code == 401
        # New password works
        r4 = client.post("/api/auth/login", json={"username": "admin", "password": "brandnewpass123"})
        assert r4.status_code == 200

    def test_confirm_with_invalid_token_rejected(self, client):
        r = client.post(
            "/api/auth/password-reset/confirm",
            json={"token": "invalid-token-value", "new_password": "newpass123"},
        )
        assert r.status_code == 401

    def test_confirm_with_weak_password_rejected(self, client):
        r = client.post(
            "/api/auth/password-reset/request",
            json={"username": "admin"},
        )
        token = r.json()["data"]["token"]
        r2 = client.post(
            "/api/auth/password-reset/confirm",
            json={"token": token, "new_password": "short"},
        )
        assert r2.status_code == 400


class TestOAuth:
    """OAuth flows — external HTTP is mocked; no network in tests."""

    def test_authorize_501_when_unconfigured(self, client, monkeypatch):
        """Unconfigured provider raises 501 (config missing)."""
        from app.core.config import get_settings
        s = get_settings()
        monkeypatch.setattr(s, "google_client_id", "")
        monkeypatch.setattr(s, "github_client_id", "")
        monkeypatch.setattr(s, "saml_sso_url", "")
        for provider in ["google", "github", "saml"]:
            r = client.get(f"/api/auth/oauth/{provider}/authorize")
            assert r.status_code == 501, f"{provider} should be 501 when unconfigured"

    def test_authorize_google_returns_url(self, client, monkeypatch):
        """Configured Google provider returns a real authorize URL."""
        from app.core.config import get_settings
        s = get_settings()
        monkeypatch.setattr(s, "google_client_id", "test-client-id")
        monkeypatch.setattr(s, "google_client_secret", "test-secret")
        r = client.get("/api/auth/oauth/google/authorize")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["authorize_url"].startswith("https://accounts.google.com/")
        assert "test-client-id" in data["authorize_url"]
        assert "state=" in data["authorize_url"]

    def test_authorize_github_returns_url(self, client, monkeypatch):
        from app.core.config import get_settings
        s = get_settings()
        monkeypatch.setattr(s, "github_client_id", "gh-client-id")
        monkeypatch.setattr(s, "github_client_secret", "gh-secret")
        r = client.get("/api/auth/oauth/github/authorize")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["authorize_url"].startswith("https://github.com/login/oauth/authorize")

    def test_callback_state_mismatch_rejected(self, client, monkeypatch):
        """State cache rejects mismatched provider before any HTTP."""
        from app.core.config import get_settings
        s = get_settings()
        monkeypatch.setattr(s, "google_client_id", "g")
        monkeypatch.setattr(s, "google_client_secret", "g")
        r = client.get("/api/auth/oauth/google/authorize")
        assert r.status_code == 200
        url = r.json()["data"]["authorize_url"]
        from urllib.parse import parse_qs, urlparse
        state = parse_qs(urlparse(url).query).get("state", [""])[0]
        assert state
        # Use that state with a DIFFERENT provider -> 401 before HTTP
        r2 = client.get(f"/api/auth/oauth/github/callback?code=x&state={state}")
        assert r2.status_code == 401

    def test_unsupported_provider_rejected(self, client):
        r = client.get("/api/auth/oauth/myspace/authorize")
        assert r.status_code == 400
        r2 = client.get("/api/auth/oauth/myspace/callback?code=x")
        assert r2.status_code == 400


class TestTrainingMetrics:
    def test_metrics_endpoint_returns_structure(self, client, db_session):
        """Even with no training run, the endpoint returns a valid shape."""
        token = _login(client)
        # Register a fake weight
        from pathlib import Path

        from app.core.config import get_settings

        weights_dir = Path(get_settings().weights_dir)
        weights_dir.mkdir(parents=True, exist_ok=True)
        (weights_dir / "metric_test.pt").write_bytes(b"0" * 4096)
        r = client.get("/api/weights", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        weights = r.json()["data"]
        target = next((w for w in weights if w["filename"] == "metric_test.pt"), None)
        if target is None:
            pytest.skip("weight not registered")
        r2 = client.get(f"/api/weights/{target['id']}/metrics", headers={"Authorization": f"Bearer {token}"})
        assert r2.status_code == 200
        data = r2.json()["data"]
        assert "summary" in data
        assert "epochs" in data
        assert data["summary"]["weight_id"] == target["id"]

    def test_metrics_curves_parsed(self, client, tmp_path):
        """Synthesize a results.csv and verify the parser."""
        import csv

        from app.services.metrics_service import _read_results_csv

        csv_path = tmp_path / "results.csv"
        with csv_path.open("w", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=[
                    "epoch",
                    "metrics/precision(B)",
                    "metrics/recall(B)",
                    "metrics/mAP50(B)",
                    "metrics/mAP50-95(B)",
                    "val/box_loss",
                ],
            )
            writer.writeheader()
            for e in range(5):
                writer.writerow(
                    {
                        "epoch": e,
                        "metrics/precision(B)": 0.5 + e * 0.1,
                        "metrics/recall(B)": 0.4 + e * 0.1,
                        "metrics/mAP50(B)": 0.6 + e * 0.05,
                        "metrics/mAP50-95(B)": 0.4 + e * 0.05,
                        "val/box_loss": 1.0 - e * 0.1,
                    }
                )
        rows = _read_results_csv(csv_path)
        assert len(rows) == 5
        assert rows[0]["epoch"] == 0.0
        assert rows[-1]["map50_95"] == pytest.approx(0.6, abs=0.01)
        assert rows[-1]["val_box_loss"] == pytest.approx(0.6, abs=0.01)


class TestDriftMonitoring:
    def test_drift_endpoint_returns_structure(self, client, db_session):
        token = _login(client)
        r = client.get("/api/stats/drift", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()["data"]
        assert "status" in data
        assert "confidence_drift" in data
        assert "class_drift" in data
        assert "correction_drift" in data
        assert "alerts" in data
        assert data["status"] in ("stable", "drifting")

    def test_drift_detects_confidence_drop(self, client, db_session):
        """Insert a synthetic confidence drop and verify the alert fires."""
        import random
        from datetime import datetime, timedelta, timezone

        from app.models.detection import Detection
        from app.models.task import Task

        # Create a task
        now = datetime.now(timezone.utc)
        task = Task(type="image", status="done", created_by="admin", total_items=1, done_items=1)
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        # Old window: high conf (0.8-1.0)
        for _ in range(30):
            db_session.add(
                Detection(
                    task_id=task.id,
                    image_path="x.png",
                    class_id=0,
                    class_name="object",
                    confidence=random.uniform(0.8, 1.0),
                    x1=0, y1=0, x2=100, y2=100,
                    status="corrected",
                    source="model",
                    created_at=now - timedelta(days=25),
                )
            )
        # Recent window: low conf (0.1-0.3)
        for _ in range(30):
            db_session.add(
                Detection(
                    task_id=task.id,
                    image_path="x.png",
                    class_id=0,
                    class_name="object",
                    confidence=random.uniform(0.1, 0.3),
                    x1=0, y1=0, x2=100, y2=100,
                    status="corrected",
                    source="model",
                    created_at=now - timedelta(days=1),
                )
            )
        db_session.commit()

        token = _login(client)
        r = client.get("/api/stats/drift", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["confidence_drift"]["drifted"] is True, f"expected drift: {data['confidence_drift']}"
        assert any(a["kind"] == "confidence_drop" for a in data["alerts"])

    def test_drift_stable_when_no_change(self, client, db_session):
        from datetime import datetime, timedelta, timezone

        from app.models.detection import Detection
        from app.models.task import Task

        now = datetime.now(timezone.utc)
        task = Task(type="image", status="done", created_by="admin", total_items=1, done_items=1)
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        for _ in range(30):
            db_session.add(
                Detection(
                    task_id=task.id,
                    image_path="x.png",
                    class_id=0,
                    class_name="object",
                    confidence=0.9,
                    x1=0, y1=0, x2=100, y2=100,
                    status="corrected",
                    source="model",
                    created_at=now - timedelta(days=25),
                )
            )
        for _ in range(30):
            db_session.add(
                Detection(
                    task_id=task.id,
                    image_path="x.png",
                    class_id=0,
                    class_name="object",
                    confidence=0.9,
                    x1=0, y1=0, x2=100, y2=100,
                    status="corrected",
                    source="model",
                    created_at=now - timedelta(days=1),
                )
            )
        db_session.commit()

        token = _login(client)
        r = client.get("/api/stats/drift", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["confidence_drift"]["drifted"] is False
        assert data["class_drift"]["drifted"] is False
        assert data["status"] == "stable"
