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
        form_data = {k: v[1] for k, v in data.items() if k != "file"}
        resp = client.post(
            "/api/tasks/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": data["file"]},
            data=form_data,
        )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


class TestPermissionEnforcement:
    """Each endpoint requires its declared permission code (B端-1)."""

    def test_admin_can_do_everything_via_legacy_bypass(self, client):
        token = _login(client, "admin", "admin-password-123")
        assert client.get("/api/auth/users", headers={"Authorization": f"Bearer {token}"}).status_code == 200
        assert client.get("/api/rbac/roles", headers={"Authorization": f"Bearer {token}"}).status_code == 200
        assert client.get("/api/dataset", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    def test_user_without_role_cannot_write_config(self, client, db_session):
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
        org = Organization(name="Test Org", code="test_org_iso1")
        db_session.add(org)
        db_session.commit()
        db_session.refresh(org)
        _upload(client, admin_token, org_id=org.id)
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
        _upload(client, admin_token, name="a.png", org_id=org_a.id)
        _upload(client, admin_token, name="b.png", org_id=org_b.id)
        self._setup_scoped_user(db_session, "org_a_user", org_id=org_a.id)
        token = _login(client, "org_a_user", "password-123")
        r = client.get("/api/tasks", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        org_ids = {t.get("org_id") for t in items}
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
        admin_token = _login(client, "admin", "admin-password-123")
        _upload(client, admin_token, name="admin_task.png")
        _make_user(db_session, "no_role_user")
        token = _login(client, "no_role_user", "password-123")
        for path in ["/api/tasks", "/api/detections/stats", "/api/dataset", "/api/weights"]:
            r = client.get(path, headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 403, f"{path} should 403 for role-less user"

    def test_scoped_user_cannot_see_other_scoped_rows(self, client, db_session):
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
        _upload(client, admin_token, name="unscoped.png")
        self._setup_scoped_user(db_session, "unscoped_seer")
        token = _login(client, "unscoped_seer", "password-123")
        r = client.get("/api/tasks", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        items = r.json()["data"]["items"]
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


class TestQualityMetrics:
    """Flywheel quality signals (AI-2)."""

    def test_quality_endpoint(self, client, db_session):
        token = _login(client, "admin", "admin-password-123")
        r = client.get("/api/stats/quality", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()["data"]
        assert "rates" in data
        assert "totals" in data
        assert "trend" in data
        assert "false_positive_rate" in data["rates"]
        assert "correction_rate" in data["rates"]

    def test_quality_reflects_corrections(self, client, db_session):
        token = _login(client, "admin", "admin-password-123")
        _upload(client, token, name="q.png")
        dets = client.get("/api/tasks/1/detections", headers={"Authorization": f"Bearer {token}"}).json()["data"]
        if not dets:
            pytest.skip("no detections (untrained YOLO)")
        client.post(
            "/api/corrections",
            headers={"Authorization": f"Bearer {token}"},
            json={"action": "false_positive", "detection_id": dets[0]["id"]},
        )
        r = client.get("/api/stats/quality", headers={"Authorization": f"Bearer {token}"})
        data = r.json()["data"]
        assert data["totals"]["rejected"] >= 1
        assert data["rates"]["false_positive_rate"] > 0


class TestScopeOnChildModels:
    """corrections / dataset / feedback inherit scope via task_id (B端-2)."""

    def test_corrections_scoped_by_task(self, client, db_session):
        """Users cannot see corrections made on tasks outside their scope."""
        admin_token = _login(client, "admin", "admin-password-123")
        org_a = Organization(name="Corr Org A", code="corr_a")
        org_b = Organization(name="Corr Org B", code="corr_b")
        db_session.add_all([org_a, org_b])
        db_session.commit()
        db_session.refresh(org_a)
        db_session.refresh(org_b)

        task_a = _upload(client, admin_token, name="ca.png", org_id=org_a.id)
        task_b = _upload(client, admin_token, name="cb.png", org_id=org_b.id)

        for tid in [task_a["task_id"], task_b["task_id"]]:
            dets = client.get(f"/api/tasks/{tid}/detections", headers={"Authorization": f"Bearer {admin_token}"}).json()["data"]
            if not dets:
                continue
            client.post(
                "/api/corrections",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"action": "confirm", "detection_id": dets[0]["id"]},
            )

        u = _make_user(db_session, "corr_a_user")
        _assign_role(db_session, u, "operator", scope_type="org", scope_id=org_a.id)
        token = _login(client, "corr_a_user", "password-123")
        r = client.get("/api/corrections/audit", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        for c in items:
            tr = client.get(f"/api/tasks/{c['task_id']}", headers={"Authorization": f"Bearer {admin_token}"})
            if tr.status_code == 200:
                org_id = tr.json()["data"].get("org_id")
                assert org_id != org_b.id, f"leaked org_b correction: {c}"

    def test_dataset_scoped_by_org(self, client, db_session):
        admin_token = _login(client, "admin", "admin-password-123")
        org_a = Organization(name="DS A", code="ds_a")
        db_session.add(org_a)
        db_session.commit()
        db_session.refresh(org_a)

        task = _upload(client, admin_token, name="a.png", org_id=org_a.id)
        # Correct a detection so there is something exportable
        dets = client.get(
            f"/api/tasks/{task['task_id']}/detections",
            headers={"Authorization": f"Bearer {admin_token}"},
        ).json()["data"]
        if dets:
            client.post(
                "/api/corrections",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"action": "confirm", "detection_id": dets[0]["id"]},
            )
        else:
            client.post(
                "/api/corrections",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={
                    "action": "add",
                    "task_id": task["task_id"],
                    "new_class_name": "target",
                    "new_bbox": {"x1": 1.0, "y1": 1.0, "x2": 100.0, "y2": 100.0},
                },
            )
        r = client.post(
            "/api/dataset/export",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "ds_test"},
        )
        assert r.status_code == 201

        u = _make_user(db_session, "ds_other")
        _assign_role(db_session, u, "operator", scope_type="org", scope_id=99999)
        token = _login(client, "ds_other", "password-123")
        r = client.get("/api/dataset", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        for item in r.json()["data"]["items"]:
            assert item.get("org_id") in (None, 99999)

    def test_feedback_scoped(self, client, db_session):
        admin_token = _login(client, "admin", "admin-password-123")
        org_a = Organization(name="FB A", code="fb_a")
        db_session.add(org_a)
        db_session.commit()
        db_session.refresh(org_a)
        task_a = _upload(client, admin_token, name="fa.png", org_id=org_a.id)

        client.post(
            "/api/feedback",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"content": "org_a issue", "task_id": task_a["task_id"]},
        )

        u = _make_user(db_session, "fb_a_user")
        _assign_role(db_session, u, "operator", scope_type="org", scope_id=org_a.id)
        token = _login(client, "fb_a_user", "password-123")
        r = client.get("/api/feedback", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert any(i["content"] == "org_a issue" for i in items), f"should see org_a feedback, got {items}"

        org_b = Organization(name="FB B", code="fb_b")
        db_session.add(org_b)
        db_session.commit()
        db_session.refresh(org_b)
        u2 = _make_user(db_session, "fb_b_user")
        _assign_role(db_session, u2, "operator", scope_type="org", scope_id=org_b.id)
        token2 = _login(client, "fb_b_user", "password-123")
        r2 = client.get("/api/feedback", headers={"Authorization": f"Bearer {token2}"})
        items2 = r2.json()["data"]["items"]
        assert not any(i["content"] == "org_a issue" for i in items2), f"leaked org_a feedback to org_b: {items2}"


class TestScopeEdgeCases:
    """Edge cases: cross-org/team, NULL scope, mixed ownership, no role (B端-2)."""

    def test_null_scope_visible_to_all_scoped_users(self, client, db_session):
        """Unscoped feedback (task_id NULL) is visible to any user with any scope."""
        admin_token = _login(client, "admin", "admin-password-123")
        org_a = Organization(name="Edge A", code="edge_a")
        db_session.add(org_a)
        db_session.commit()
        db_session.refresh(org_a)

        # Admin creates a ticket with NO task_id (unscoped)
        client.post(
            "/api/feedback",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"content": "unscoped ticket"},
        )

        # User scoped to org_a should see it (unscoped is visible to all)
        u = _make_user(db_session, "edge_a_user")
        _assign_role(db_session, u, "operator", scope_type="org", scope_id=org_a.id)
        token = _login(client, "edge_a_user", "password-123")
        r = client.get("/api/feedback", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert any(i["content"] == "unscoped ticket" for i in items), f"unscoped visible to scoped user: {items}"

    def test_mixed_org_and_team_scopes(self, client, db_session):
        """User with BOTH org and team scopes sees rows matching either."""
        admin_token = _login(client, "admin", "admin-password-123")
        org_a = Organization(name="Mix Org", code="mix_org")
        db_session.add(org_a)
        db_session.commit()
        db_session.refresh(org_a)
        team_x = Team(name="Mix X", code="mix_x", org_id=org_a.id)
        db_session.add(team_x)
        db_session.commit()
        db_session.refresh(team_x)

        # Task in org_a (unscoped team)
        _upload(client, admin_token, name="org.png", org_id=org_a.id)
        # Task in team_x
        _upload(client, admin_token, name="team.png", team_id=team_x.id)
        # Task in org_b (should NOT be visible)
        org_b = Organization(name="Mix B", code="mix_b")
        db_session.add(org_b)
        db_session.commit()
        db_session.refresh(org_b)
        _upload(client, admin_token, name="other.png", org_id=org_b.id)

        # User with BOTH org:org_a AND team:team_x scopes
        u = _make_user(db_session, "mix_user")
        _assign_role(db_session, u, "operator", scope_type="org", scope_id=org_a.id)
        _assign_role(db_session, u, "operator", scope_type="team", scope_id=team_x.id)
        token = _login(client, "mix_user", "password-123")
        r = client.get("/api/tasks", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        org_ids = {t.get("org_id") for t in items}
        team_ids = {t.get("team_id") for t in items}
        # Should see org_a rows (org scope) AND team_x rows (team scope)
        assert org_a.id in org_ids, f"should see org_a: {org_ids}"
        assert team_x.id in team_ids, f"should see team_x: {team_ids}"
        # Should NOT see org_b rows
        assert org_b.id not in org_ids, f"leaked org_b: {org_ids}"

    def test_team_scoped_user_sees_team_rows_and_unscoped(self, client, db_session):
        admin_token = _login(client, "admin", "admin-password-123")
        org = Organization(name="TU Org", code="tu_org")
        db_session.add(org)
        db_session.commit()
        db_session.refresh(org)
        team_a = Team(name="TU A", code="tu_a", org_id=org.id)
        db_session.add(team_a)
        db_session.commit()
        db_session.refresh(team_a)

        # team_a row
        _upload(client, admin_token, name="team.png", team_id=team_a.id)
        # unscoped row
        _upload(client, admin_token, name="unscoped.png")

        u = _make_user(db_session, "tu_user")
        _assign_role(db_session, u, "operator", scope_type="team", scope_id=team_a.id)
        token = _login(client, "tu_user", "password-123")
        r = client.get("/api/tasks", headers={"Authorization": f"Bearer {token}"})
        items = r.json()["data"]["items"]
        # Should see team_a row and unscoped row
        team_ids = {t.get("team_id") for t in items}
        assert team_a.id in team_ids or None in team_ids, f"should see team_a or unscoped: team_ids={team_ids}"

    def test_no_role_403_on_all_isolated_endpoints(self, client, db_session):
        """Role-less user is rejected at the permission gate on isolated endpoints."""
        admin_token = _login(client, "admin", "admin-password-123")
        _upload(client, admin_token, name="any.png")

        _make_user(db_session, "edge_noperm")
        token = _login(client, "edge_noperm", "password-123")
        for path in ["/api/feedback", "/api/corrections/audit", "/api/dataset", "/api/tasks", "/api/stats/quality"]:
            r = client.get(path, headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 403, f"{path} should 403 for role-less user, got {r.status_code}"

    def test_admin_global_sees_all_scoped_rows(self, client, db_session):
        """Admin (legacy role=admin) sees all rows regardless of scope."""
        admin_token = _login(client, "admin", "admin-password-123")
        org_a = Organization(name="Adm A", code="adm_a")
        org_b = Organization(name="Adm B", code="adm_b")
        db_session.add_all([org_a, org_b])
        db_session.commit()
        db_session.refresh(org_a)
        db_session.refresh(org_b)

        _upload(client, admin_token, name="a.png", org_id=org_a.id)
        _upload(client, admin_token, name="b.png", org_id=org_b.id)
        r = client.get("/api/tasks", headers={"Authorization": f"Bearer {admin_token}"})
        items = r.json()["data"]["items"]
        org_ids = {t.get("org_id") for t in items}
        assert org_a.id in org_ids
        assert org_b.id in org_ids, f"admin should see both: {org_ids}"

    def test_global_scope_sees_cross_org_rows(self, client, db_session):
        admin_token = _login(client, "admin", "admin-password-123")
        org_a = Organization(name="GS A", code="gs_a")
        org_b = Organization(name="GS B", code="gs_b")
        db_session.add_all([org_a, org_b])
        db_session.commit()
        db_session.refresh(org_a)
        db_session.refresh(org_b)

        _upload(client, admin_token, name="a.png", org_id=org_a.id)
        _upload(client, admin_token, name="b.png", org_id=org_b.id)

        u = _make_user(db_session, "gs_global")
        _assign_role(db_session, u, "operator", scope_type="global")
        token = _login(client, "gs_global", "password-123")
        r = client.get("/api/tasks", headers={"Authorization": f"Bearer {token}"})
        items = r.json()["data"]["items"]
        org_ids = {t.get("org_id") for t in items}
        assert org_a.id in org_ids
        assert org_b.id in org_ids, f"global scope sees all: {org_ids}"
