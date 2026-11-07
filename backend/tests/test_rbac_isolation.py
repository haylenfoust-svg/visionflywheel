"""RBAC permission + org/team data-isolation tests (B端-1, B端-2)."""

from __future__ import annotations

import io

import pytest

from app.models.rbac import Organization, Role, Team, UserRole
from app.models.user import User


def _login(client, username="admin", password="admin-password-123") -> str:
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["data"]["access_token"]


def _make_user(db_session, username: str, role: str = "user") -> User:
    from app.core.security import hash_password

    u = User(username=username, password_hash=hash_password("password-123"), role=role)
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


def _assign_role(db_session, user: User, role_code: str, scope_type: str = "global", scope_id: int | None = None) -> None:
    role = db_session.query(Role).filter(Role.code == role_code).first()
    if role is None:
        pytest.skip(f"role {role_code} not seeded")
    db_session.add(
        UserRole(user_id=user.id, role_id=role.id, scope_type=scope_type, scope_id=scope_id)
    )
    db_session.commit()


def _upload(client, token: str, name: str = "s.png", org_id: int | None = None, team_id: int | None = None) -> dict:
    import pathlib
    import tempfile

    from app.utils.imaging import make_test_image

    with tempfile.TemporaryDirectory() as td:
        png = make_test_image(pathlib.Path(td) / "s.png").read_bytes()
        data = {"file": (name, io.BytesIO(png), "image/png")}
        if org_id is not None:
            data["org_id"] = (None, str(org_id))
        if team_id is not None:
            data["team_id"] = (None, str(team_id))
        resp = client.post(
            "/api/tasks/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": data["file"]},
            data={k: v[1] for k, v in data.items() if k != "file"},
        )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


class TestPermissionEnforcement:
    """Each endpoint requires its declared permission code (B端-1)."""

    def test_admin_can_do_everything_via_legacy_bypass(self, client):
        token = _login(client, "admin", "admin-password-123")
        # These should all succeed because admin has role='admin' bypass
        assert client.get("/api/auth/users", headers={"Authorization": f"Bearer {token}"}).status_code == 200
        assert client.get("/api/rbac/roles", headers={"Authorization": f"Bearer {token}"}).status_code == 200
        assert client.get("/api/dataset", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    def test_user_without_role_cannot_write_config(self, client, db_session):
        # Fresh user with NO RBAC role
        _make_user(db_session, "norole")
        token = _login(client, "norole", "password-123")
        r = client.put(
            "/api/config/default_conf_threshold",
            headers={"Authorization": f"Bearer {token}"},
            json={"value": 0.1},
        )
        assert r.status_code == 403
        assert r.json()["code"] == 40301

    def test_user_without_role_cannot_write_task(self, client, db_session):
        _make_user(db_session, "norole2")
        token = _login(client, "norole2", "password-123")
        import pathlib
        import tempfile

        from app.utils.imaging import make_test_image

        with tempfile.TemporaryDirectory() as td:
            png = make_test_image(pathlib.Path(td) / "s.png").read_bytes()
            r = client.post(
                "/api/tasks/upload",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": ("s.png", io.BytesIO(png), "image/png")},
            )
        assert r.status_code == 403

    def test_operator_role_has_expected_permissions(self, client, db_session):
        _make_user(db_session, "op1")
        _assign_role(db_session, db_session.query(User).filter(User.username == "op1").first(), "operator")
        token = _login(client, "op1", "password-123")
        # Operator CAN write tasks
        import pathlib
        import tempfile

        from app.utils.imaging import make_test_image

        with tempfile.TemporaryDirectory() as td:
            png = make_test_image(pathlib.Path(td) / "s.png").read_bytes()
            r = client.post(
                "/api/tasks/upload",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": ("s.png", io.BytesIO(png), "image/png")},
            )
        assert r.status_code == 200
        # Operator CANNOT delete users
        r = client.delete("/api/auth/users/999", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403

    def test_operator_cannot_switch_weights(self, client, db_session):
        _make_user(db_session, "op2")
        _assign_role(db_session, db_session.query(User).filter(User.username == "op2").first(), "operator")
        token = _login(client, "op2", "password-123")
        r = client.put("/api/weights/1/default", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403

    def test_viewer_cannot_correct(self, client, db_session):
        _make_user(db_session, "viewer1")
        _assign_role(db_session, db_session.query(User).filter(User.username == "viewer1").first(), "viewer")
        token = _login(client, "viewer1", "password-123")
        r = client.post(
            "/api/corrections",
            headers={"Authorization": f"Bearer {token}"},
            json={"action": "confirm", "detection_id": 1},
        )
        assert r.status_code == 403

    def test_permission_denied_message(self, client, db_session):
        _make_user(db_session, "noPerms")
        token = _login(client, "noPerms", "password-123")
        r = client.get("/api/rbac/roles", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403
        assert "missing permission" in r.json()["message"]

    def test_unknown_permission_code_in_catalog(self):
        from app.services.permission_catalog import PERMISSION_INDEX

        assert "user.read" in PERMISSION_INDEX
        assert "system.admin" in PERMISSION_INDEX
        assert "dataset.export" in PERMISSION_INDEX


class TestDataIsolation:
    """org/team scope filtering on business queries (B端-2)."""

    def _setup_scoped_user(self, db_session, username: str, org_id: int | None = None, team_id: int | None = None):
        u = _make_user(db_session, username)
        if org_id is not None:
            _assign_role(db_session, u, "operator", scope_type="org", scope_id=org_id)
        elif team_id is not None:
            _assign_role(db_session, u, "operator", scope_type="team", scope_id=team_id)
        else:
            _assign_role(db_session, u, "operator", scope_type="global")
        return u

    def test_global_scope_sees_all(self, client, db_session):
        admin_token = _login(client, "admin", "admin-password-123")
        # Admin creates a task with a scope
        org = Organization(name="Test Org", code="test_org_iso1")
        db_session.add(org)
        db_session.commit()
        db_session.refresh(org)
        _upload(client, admin_token, org_id=org.id)

        # Global-scope user can see it
        self._setup_scoped_user(db_session, "global1")
        token = _login(client, "global1", "password-123")
        r = client.get("/api/tasks", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["data"]["total"] >= 1

    def test_org_scope_filters_by_org(self, client, db_session):
        admin_token = _login(client, "admin", "admin-password-123")
        org_a = Organization(name="Org A", code="org_a")
        org_b = Organization(name="Org B", code="org_b")
        db_session.add_all([org_a, org_b])
        db_session.commit()
        db_session.refresh(org_a)
        db_session.refresh(org_b)

        # Upload one to each org
        _upload(client, admin_token, name="a.png", org_id=org_a.id)
        _upload(client, admin_token, name="b.png", org_id=org_b.id)

        # User scoped to org_a should see only org_a's tasks (plus unscoped)
        self._setup_scoped_user(db_session, "org_a_user", org_id=org_a.id)
        token = _login(client, "org_a_user", "password-123")
        r = client.get("/api/tasks", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        org_ids = {t.get("org_id") for t in items}
        # Should NOT see org_b tasks
        assert org_b.id not in org_ids, f"leaked org_b tasks: {org_ids}"

    def test_team_scope_filters_by_team(self, client, db_session):
        admin_token = _login(client, "admin", "admin-password-123")
        org = Organization(name="Team Org", code="team_org")
        db_session.add(org)
        db_session.commit()
        db_session.refresh(org)
        team_a = Team(name="Team A", code="team_a", org_id=org.id)
        team_b = Team(name="Team B", code="team_b", org_id=org.id)
        db_session.add_all([team_a, team_b])
        db_session.commit()
        db_session.refresh(team_a)
        db_session.refresh(team_b)

        _upload(client, admin_token, name="t1.png", team_id=team_a.id)
        _upload(client, admin_token, name="t2.png", team_id=team_b.id)

        self._setup_scoped_user(db_session, "team_a_user", team_id=team_a.id)
        token = _login(client, "team_a_user", "password-123")
        r = client.get("/api/tasks", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        team_ids = {t.get("team_id") for t in items}
        assert team_b.id not in team_ids, f"leaked team_b tasks: {team_ids}"

    def test_no_role_gets_403_everywhere(self, client, db_session):
        """A user with NO RBAC role is rejected at the permission gate (B端-1)."""
        admin_token = _login(client, "admin", "admin-password-123")
        _upload(client, admin_token, name="admin_task.png")

        _make_user(db_session, "no_role_user")
        token = _login(client, "no_role_user", "password-123")
        # Every business endpoint now requires a permission code
        for path in ["/api/tasks", "/api/detections/stats", "/api/dataset", "/api/weights"]:
            r = client.get(path, headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 403, f"{path} should 403 for role-less user"

    def test_scoped_user_cannot_see_other_scoped_rows(self, client, db_session):
        """A user scoped to team X cannot see rows scoped to team Y (B端-2)."""
        admin_token = _login(client, "admin", "admin-password-123")
        org = Organization(name="Iso Org", code="iso_org")
        db_session.add(org)
        db_session.commit()
        db_session.refresh(org)
        team_a = Team(name="A", code="a", org_id=org.id)
        team_b = Team(name="B", code="b", org_id=org.id)
        db_session.add_all([team_a, team_b])
        db_session.commit()
        db_session.refresh(team_a)
        db_session.refresh(team_b)

        _upload(client, admin_token, name="a.png", team_id=team_a.id)
        _upload(client, admin_token, name="b.png", team_id=team_b.id)

        # User scoped to team_a — sees only team_a rows (and unscoped)
        u = _make_user(db_session, "team_a_only")
        _assign_role(db_session, u, "viewer", scope_type="team", scope_id=team_a.id)
        token = _login(client, "team_a_only", "password-123")
        r = client.get("/api/tasks", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        team_ids = {t.get("team_id") for t in items}
        assert team_b.id not in team_ids, f"leaked team_b tasks: {team_ids}"

    def test_scoped_user_sees_unscoped_tasks(self, client, db_session):
        admin_token = _login(client, "admin", "admin-password-123")
        # Unscoped task (no org, no team)
        _upload(client, admin_token, name="unscoped.png")

        self._setup_scoped_user(db_session, "unscoped_seer")
        token = _login(client, "unscoped_seer", "password-123")
        r = client.get("/api/tasks", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        # Should see at least the unscoped one
        unscoped = [t for t in items if t.get("org_id") is None and t.get("team_id") is None]
        assert len(unscoped) >= 1

    def test_scope_filter_ignores_scoped_other_org(self, client, db_session):
        admin_token = _login(client, "admin", "admin-password-123")
        org_a = Organization(name="Org A2", code="org_a2")
        org_b = Organization(name="Org B2", code="org_b2")
        db_session.add_all([org_a, org_b])
        db_session.commit()
        db_session.refresh(org_a)
        db_session.refresh(org_b)

        _upload(client, admin_token, name="a.png", org_id=org_a.id)
        _upload(client, admin_token, name="b.png", org_id=org_b.id)

        self._setup_scoped_user(db_session, "only_a", org_id=org_a.id)
        token = _login(client, "only_a", "password-123")
        r = client.get("/api/tasks", headers={"Authorization": f"Bearer {token}"})
        items = r.json()["data"]["items"]
        for t in items:
            assert t.get("org_id") != org_b.id, f"saw org_b task: {t}"
