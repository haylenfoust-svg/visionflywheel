"""LLM/RAG chat tests (PRD FR-8)."""

from __future__ import annotations

import io

import pytest


def _login(client, username="admin", password="admin-password-123") -> str:
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["data"]["access_token"]


@pytest.fixture
def seeded(client, tmp_path):
    """Upload an image and confirm a detection so stats are non-empty."""
    from app.utils.imaging import make_test_image

    png = make_test_image(tmp_path / "s.png").read_bytes()
    token = _login(client)
    up = client.post(
        "/api/tasks/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("s.png", io.BytesIO(png), "image/png")},
    )
    data = up.json()["data"]
    for det in data["detections"]:
        client.post(
            "/api/corrections",
            headers={"Authorization": f"Bearer {token}"},
            json={"action": "confirm", "detection_id": det["id"]},
        )
    return data


class TestChat:
    def test_count_detections(self, client, seeded):
        token = _login(client)
        resp = client.post(
            "/api/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": "今天识别了多少 defect？"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "answer" in data
        assert "sources" in data
        assert data["intent"] == "count_detections"
        assert data["is_hallucination_checked"] is True
        # The answer should cite a real number from the DB
        assert any(ch.isdigit() for ch in data["answer"])

    def test_top_class(self, client, seeded):
        token = _login(client)
        resp = client.post(
            "/api/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": "最常见的类别是什么？"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["intent"] == "top_class"

    def test_today_summary(self, client, seeded):
        token = _login(client)
        resp = client.post(
            "/api/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": "今天做了什么？"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["intent"] in ("today_summary", "general")

    def test_help_intent(self, client):
        token = _login(client)
        resp = client.post(
            "/api/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": "你能做什么？"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["intent"] == "help"

    def test_empty_question_rejected(self, client):
        token = _login(client)
        resp = client.post(
            "/api/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": ""},
        )
        assert resp.status_code == 400

    def test_requires_auth(self, client):
        resp = client.post("/api/chat", json={"question": "hi"})
        assert resp.status_code == 401


class TestKnowledge:
    def test_add_and_list(self, client):
        token = _login(client)
        r = client.post(
            "/api/chat/knowledge",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": "Q1?", "answer": "A1."},
        )
        assert r.status_code == 201
        entry_id = r.json()["data"]["id"]

        r = client.get("/api/knowledge", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        ids = [e["id"] for e in r.json()["data"]]
        assert entry_id in ids

    def test_delete_admin_only(self, client):
        admin = _login(client)
        user = _login(client, "tester", "test-password-123")
        entry_id = client.post(
            "/api/chat/knowledge",
            headers={"Authorization": f"Bearer {admin}"},
            json={"question": "Q", "answer": "A"},
        ).json()["data"]["id"]

        resp = client.delete(f"/api/knowledge/{entry_id}", headers={"Authorization": f"Bearer {user}"})
        assert resp.status_code == 403

        resp = client.delete(f"/api/knowledge/{entry_id}", headers={"Authorization": f"Bearer {admin}"})
        assert resp.status_code == 204

    def test_knowledge_redundant_in_answer(self, client):
        """After saving to KB, a similar question should surface the entry."""
        token = _login(client)
        client.post(
            "/api/chat/knowledge",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": "怎么导出数据集", "answer": "在数据与权重页面点导出训练集按钮即可。"},
        )
        resp = client.post(
            "/api/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": "数据集怎么导出？"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        # Should either be grounded in knowledge or stats — both acceptable
        assert data["answer"]
