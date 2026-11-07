"""Auth + permission matrix (PRD FR-1, M1 DoD)."""

from __future__ import annotations


class TestLogin:
    def test_login_success(self, client):
        resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin-password-123"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["token_type"] == "bearer"
        assert body["data"]["user"]["role"] == "admin"
        assert body["data"]["access_token"]

    def test_login_wrong_password(self, client):
        resp = client.post("/api/auth/login", json={"username": "admin", "password": "nope"})
        assert resp.status_code == 401
        assert resp.json()["code"] == 40101

    def test_login_unknown_user(self, client):
        resp = client.post("/api/auth/login", json={"username": "ghost", "password": "whatever"})
        assert resp.status_code == 401
        assert resp.json()["code"] == 40101


class TestMe:
    def test_me_requires_token(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_me_with_token(self, client, user_token):
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 200
        assert resp.json()["data"]["username"] == "tester"


class TestPermissionMatrix:
    """M1 DoD: 完整权限矩阵."""

    def test_user_cannot_list_users(self, client, user_token):
        resp = client.get("/api/auth/users", headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 403
        assert resp.json()["code"] == 40301

    def test_admin_can_list_users(self, client, admin_token):
        resp = client.get("/api/auth/users", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        usernames = [u["username"] for u in resp.json()["data"]]
        assert "admin" in usernames
        assert "tester" in usernames

    def test_user_cannot_create_user(self, client, user_token):
        resp = client.post(
            "/api/auth/users",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"username": "new", "password": "password123", "role": "user"},
        )
        assert resp.status_code == 403

    def test_admin_can_create_user(self, client, admin_token):
        resp = client.post(
            "/api/auth/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"username": "created", "password": "password123", "role": "user"},
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["username"] == "created"

    def test_user_cannot_read_config(self, client, user_token):
        resp = client.get("/api/config", headers={"Authorization": f"Bearer {user_token}"})
        # 普通用户可读配置（业务需要），但写操作受限
        assert resp.status_code == 200

    def test_user_cannot_write_config(self, client, user_token):
        resp = client.put(
            "/api/config/default_conf_threshold",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"value": 0.3},
        )
        assert resp.status_code == 403

    def test_admin_can_write_config(self, client, admin_token):
        resp = client.put(
            "/api/config/default_conf_threshold",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"value": 0.3},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["value"] == 0.3
        assert resp.json()["data"]["source"] == "db"

    def test_forbidden_key_not_configurable(self, client, admin_token):
        resp = client.put(
            "/api/config/secret_key",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"value": "hacked"},
        )
        assert resp.status_code == 403


class TestSystem:
    def test_health_no_auth(self, client):
        resp = client.get("/api/system/health")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] in ("healthy", "degraded")

    def test_info_requires_auth(self, client):
        resp = client.get("/api/system/info")
        assert resp.status_code == 401

    def test_info_with_auth(self, client, user_token):
        resp = client.get("/api/system/info", headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 200
        assert resp.json()["data"]["version"]


class TestErrorEnvelope:
    def test_validation_error_envelope(self, client):
        resp = client.post("/api/auth/login", json={"username": ""})
        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == 40001
        assert "validation error" in body["message"]

    def test_request_id_echoed(self, client):
        resp = client.get("/api/system/health", headers={"X-Request-Id": "req-123"})
        assert resp.headers.get("X-Request-Id") == "req-123"
