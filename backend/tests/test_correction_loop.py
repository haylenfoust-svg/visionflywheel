"""Correction loop tests (PRD FR-3, M3 DoD)."""

from __future__ import annotations

import io

import pytest


def _login(client, username="admin", password="admin-password-123") -> str:
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["data"]["access_token"]


@pytest.fixture
def seeded_task(client, tmp_path):
    """Upload a synthetic image and return (task_id, first_detection_id)."""
    from app.utils.imaging import make_test_image

    png = make_test_image(tmp_path / "s.png").read_bytes()
    token = _login(client)
    resp = client.post(
        "/api/tasks/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("s.png", io.BytesIO(png), "image/png")},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    return data["task_id"], data["detections"]


class TestConfirm:
    def test_confirm_marks_corrected(self, client, seeded_task):
        task_id, detections = seeded_task
        det_id = detections[0]["id"]
        token = _login(client)
        resp = client.post(
            "/api/corrections",
            headers={"Authorization": f"Bearer {token}"},
            json={"action": "confirm", "detection_id": det_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["action"] == "confirm"
        assert body["detection_status"] == "corrected"

    def test_confirm_is_audited(self, client, seeded_task):
        task_id, detections = seeded_task
        det_id = detections[0]["id"]
        token = _login(client)
        client.post(
            "/api/corrections",
            headers={"Authorization": f"Bearer {token}"},
            json={"action": "confirm", "detection_id": det_id},
        )
        resp = client.get(
            "/api/corrections/audit",
            headers={"Authorization": f"Bearer {token}"},
            params={"detection_id": det_id},
        )
        assert resp.status_code == 200
        rows = resp.json()["data"]["items"]
        assert len(rows) == 1
        assert rows[0]["action"] == "confirm"
        assert rows[0]["operator"] == "admin"


class TestRelabel:
    def test_relabel_updates_class(self, client, seeded_task):
        task_id, detections = seeded_task
        det_id = detections[0]["id"]
        token = _login(client)
        resp = client.post(
            "/api/corrections",
            headers={"Authorization": f"Bearer {token}"},
            json={"action": "relabel", "detection_id": det_id, "new_class_name": "缺陷A"},
        )
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["detection_status"] == "corrected"

        # verify persistence
        r = client.get(f"/api/detections/{det_id}", headers={"Authorization": f"Bearer {token}"})
        assert r.json()["data"]["class_name"] == "缺陷A"

    def test_relabel_requires_class(self, client, seeded_task):
        task_id, detections = seeded_task
        det_id = detections[0]["id"]
        token = _login(client)
        resp = client.post(
            "/api/corrections",
            headers={"Authorization": f"Bearer {token}"},
            json={"action": "relabel", "detection_id": det_id},
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == 42201


class TestFalsePositive:
    def test_marks_rejected(self, client, seeded_task):
        task_id, detections = seeded_task
        det_id = detections[0]["id"]
        token = _login(client)
        resp = client.post(
            "/api/corrections",
            headers={"Authorization": f"Bearer {token}"},
            json={"action": "false_positive", "detection_id": det_id},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["detection_status"] == "rejected"


class TestAdjust:
    def test_adjust_updates_bbox(self, client, seeded_task):
        task_id, detections = seeded_task
        det_id = detections[0]["id"]
        token = _login(client)
        resp = client.post(
            "/api/corrections",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "action": "adjust",
                "detection_id": det_id,
                "new_bbox": {"x1": 10.0, "y1": 20.0, "x2": 110.0, "y2": 120.0},
            },
        )
        assert resp.status_code == 200
        r = client.get(f"/api/detections/{det_id}", headers={"Authorization": f"Bearer {token}"})
        bbox = r.json()["data"]["bbox"]
        assert bbox["x1"] == 10.0
        assert bbox["x2"] == 110.0

    def test_adjust_rejects_degenerate_bbox(self, client, seeded_task):
        task_id, detections = seeded_task
        det_id = detections[0]["id"]
        token = _login(client)
        resp = client.post(
            "/api/corrections",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "action": "adjust",
                "detection_id": det_id,
                "new_bbox": {"x1": 100.0, "y1": 100.0, "x2": 50.0, "y2": 50.0},
            },
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == 42201


class TestAdd:
    def test_add_creates_manual_detection(self, client, seeded_task):
        task_id, detections = seeded_task
        token = _login(client)
        before = len(client.get(f"/api/tasks/{task_id}/detections", headers={"Authorization": f"Bearer {token}"}).json()["data"])
        resp = client.post(
            "/api/corrections",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "action": "add",
                "task_id": task_id,
                "new_class_name": "补检目标",
                "new_bbox": {"x1": 200.0, "y1": 200.0, "x2": 300.0, "y2": 320.0},
            },
        )
        assert resp.status_code == 200, resp.text
        after_rows = client.get(f"/api/tasks/{task_id}/detections", headers={"Authorization": f"Bearer {token}"}).json()["data"]
        assert len(after_rows) == before + 1
        created = [r for r in after_rows if r["source"] == "manual"]
        assert len(created) == 1
        assert created[0]["class_name"] == "补检目标"


class TestAppendOnly:
    def test_put_rejected(self, client, seeded_task):
        del seeded_task  # fixture ensures a task + detection exists
        token = _login(client)
        resp = client.put(
            "/api/corrections/1",
            headers={"Authorization": f"Bearer {token}"},
            json={"action": "confirm"},
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == 40302

    def test_delete_rejected(self, client, seeded_task):
        del seeded_task
        token = _login(client)
        resp = client.delete("/api/corrections/1", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403
        assert resp.json()["code"] == 40302


class TestUndo:
    def test_undo_reverts_relabel(self, client, seeded_task):
        task_id, detections = seeded_task
        det_id = detections[0]["id"]
        original_class = detections[0]["class_name"]
        token = _login(client)
        corr = client.post(
            "/api/corrections",
            headers={"Authorization": f"Bearer {token}"},
            json={"action": "relabel", "detection_id": det_id, "new_class_name": "改错了"},
        ).json()["data"]

        undo = client.post(
            "/api/corrections/undo",
            headers={"Authorization": f"Bearer {token}"},
            json={"correction_id": corr["correction_id"]},
        )
        assert undo.status_code == 200
        assert undo.json()["data"]["action"] == "undo"

        # detection reverted
        r = client.get(f"/api/detections/{det_id}", headers={"Authorization": f"Bearer {token}"})
        assert r.json()["data"]["class_name"] == original_class

    def test_undo_add_removes_box(self, client, seeded_task):
        task_id, detections = seeded_task
        token = _login(client)
        before = len(client.get(f"/api/tasks/{task_id}/detections", headers={"Authorization": f"Bearer {token}"}).json()["data"])
        corr = client.post(
            "/api/corrections",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "action": "add",
                "task_id": task_id,
                "new_class_name": "临时补检",
                "new_bbox": {"x1": 1.0, "y1": 1.0, "x2": 50.0, "y2": 50.0},
            },
        ).json()["data"]
        mid = len(client.get(f"/api/tasks/{task_id}/detections", headers={"Authorization": f"Bearer {token}"}).json()["data"])
        assert mid == before + 1

        client.post(
            "/api/corrections/undo",
            headers={"Authorization": f"Bearer {token}"},
            json={"correction_id": corr["correction_id"]},
        )
        after = len(client.get(f"/api/tasks/{task_id}/detections", headers={"Authorization": f"Bearer {token}"}).json()["data"])
        assert after == before

    def test_undo_log_is_append_only(self, client, seeded_task):
        task_id, detections = seeded_task
        det_id = detections[0]["id"]
        token = _login(client)
        corr = client.post(
            "/api/corrections",
            headers={"Authorization": f"Bearer {token}"},
            json={"action": "confirm", "detection_id": det_id},
        ).json()["data"]
        client.post(
            "/api/corrections/undo",
            headers={"Authorization": f"Bearer {token}"},
            json={"correction_id": corr["correction_id"]},
        )
        audit = client.get(
            "/api/corrections/audit",
            headers={"Authorization": f"Bearer {token}"},
            params={"detection_id": det_id},
        ).json()["data"]["items"]
        actions = [r["action"] for r in audit]
        assert "confirm" in actions
        assert "undo" in actions
        # both rows are preserved
        assert len(audit) == 2


class TestBatch:
    def test_batch_apply(self, client, seeded_task):
        task_id, detections = seeded_task
        token = _login(client)
        ids = [d["id"] for d in detections[:2]]
        resp = client.post(
            "/api/corrections/batch",
            headers={"Authorization": f"Bearer {token}"},
            json={"items": [{"action": "confirm", "detection_id": i} for i in ids]},
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2


class TestFeedback:
    def test_user_can_create_ticket(self, client, seeded_task):
        task_id, detections = seeded_task
        token = _login(client, "tester", "test-password-123")
        resp = client.post(
            "/api/feedback",
            headers={"Authorization": f"Bearer {token}"},
            json={"detection_id": detections[0]["id"], "content": "这个框不准"},
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["status"] == "open"

    def test_feedback_scope_visibility(self, client, seeded_task):
        """Default: see all tickets in scope. mine=true narrows to own."""
        task_id, detections = seeded_task
        admin = _login(client)
        user = _login(client, "tester", "test-password-123")
        client.post(
            "/api/feedback",
            headers={"Authorization": f"Bearer {user}"},
            json={"content": "tester's ticket"},
        )
        client.post(
            "/api/feedback",
            headers={"Authorization": f"Bearer {admin}"},
            json={"content": "admin's ticket"},
        )
        # Default: user sees both (both unscoped, user has global operator role)
        r_user = client.get("/api/feedback", headers={"Authorization": f"Bearer {user}"}).json()["data"]["items"]
        assert len(r_user) == 2, f"expected both tickets in scope, got {r_user}"
        # mine=true narrows to own
        r_mine = client.get("/api/feedback?mine=true", headers={"Authorization": f"Bearer {user}"}).json()["data"]["items"]
        assert all(t["username"] == "tester" for t in r_mine), f"mine=true should filter to own: {r_mine}"
        # admin sees both
        r_admin = client.get("/api/feedback", headers={"Authorization": f"Bearer {admin}"}).json()["data"]["items"]
        assert len(r_admin) == 2

    def test_admin_can_reply_and_resolve(self, client, seeded_task):
        task_id, detections = seeded_task
        admin = _login(client)
        user = _login(client, "tester", "test-password-123")
        tid = client.post(
            "/api/feedback",
            headers={"Authorization": f"Bearer {user}"},
            json={"content": "需要复核"},
        ).json()["data"]["id"]

        r = client.put(
            f"/api/feedback/{tid}/reply",
            headers={"Authorization": f"Bearer {admin}"},
            json={"reply": "已复核，改为缺陷A"},
        )
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "replied"

        r = client.put(
            f"/api/feedback/{tid}/status",
            headers={"Authorization": f"Bearer {admin}"},
            json={"status": "resolved"},
        )
        assert r.json()["data"]["status"] == "resolved"

    def test_user_cannot_reply(self, client, seeded_task):
        task_id, detections = seeded_task
        del task_id, detections
        user = _login(client, "tester", "test-password-123")
        tid = client.post(
            "/api/feedback",
            headers={"Authorization": f"Bearer {user}"},
            json={"content": "x"},
        ).json()["data"]["id"]
        resp = client.put(
            f"/api/feedback/{tid}/reply",
            headers={"Authorization": f"Bearer {user}"},
            json={"reply": "擅自回复"},
        )
        assert resp.status_code == 403
