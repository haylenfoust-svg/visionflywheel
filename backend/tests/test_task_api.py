"""Upload → detect → persist → visualise (PRD FR-2, M2 DoD)."""

from __future__ import annotations

import io

import pytest

from app.utils.imaging import make_test_image


@pytest.fixture
def sample_png_bytes(tmp_path):
    path = make_test_image(tmp_path / "sample.png")
    return path.read_bytes()


def _login(client, username="admin", password="admin-password-123") -> str:
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["data"]["access_token"]


class TestUpload:
    def test_upload_returns_detections(self, client, sample_png_bytes):
        token = _login(client)
        resp = client.post(
            "/api/tasks/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("sample.png", io.BytesIO(sample_png_bytes), "image/png")},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["code"] == 0
        data = body["data"]
        assert data["task_id"] > 0
        assert data["status"] == "done"
        assert data["detector_mode"] == "fallback"  # torch is not installed here
        assert data["image_url"].startswith("/api/files/")
        assert data["result_url"].startswith("/api/files/")
        assert data["inference_ms"] >= 0
        # each detection has the standard shape
        for d in data["detections"]:
            assert set(d) >= {"id", "class_name", "class_name_zh", "confidence", "bbox", "status"}
            assert d["status"] == "pending"
            assert d["source"] == "model"

    def test_upload_rejects_bad_extension(self, client):
        token = _login(client)
        resp = client.post(
            "/api/tasks/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("malware.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == 40002

    def test_upload_rejects_empty_file(self, client):
        token = _login(client)
        resp = client.post(
            "/api/tasks/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("empty.png", io.BytesIO(b""), "image/png")},
        )
        assert resp.status_code == 400

    def test_upload_requires_auth(self, client, sample_png_bytes):
        resp = client.post(
            "/api/tasks/upload",
            files={"file": ("sample.png", io.BytesIO(sample_png_bytes), "image/png")},
        )
        assert resp.status_code == 401


class TestQuery:
    def test_list_tasks(self, client, sample_png_bytes):
        token = _login(client)
        client.post(
            "/api/tasks/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("a.png", io.BytesIO(sample_png_bytes), "image/png")},
        )
        resp = client.get("/api/tasks", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        page = resp.json()["data"]
        assert page["total"] >= 1
        assert len(page["items"]) >= 1

    def test_get_task_and_detections(self, client, sample_png_bytes):
        token = _login(client)
        up = client.post(
            "/api/tasks/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("a.png", io.BytesIO(sample_png_bytes), "image/png")},
        )
        task_id = up.json()["data"]["task_id"]

        resp = client.get(f"/api/tasks/{task_id}", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == task_id

        resp = client.get(f"/api/tasks/{task_id}/detections", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        rows = resp.json()["data"]
        # each row's bbox is a dict
        for r in rows:
            assert {"x1", "y1", "x2", "y2"} <= set(r["bbox"])

    def test_404_when_missing(self, client):
        token = _login(client)
        assert client.get("/api/tasks/999999", headers={"Authorization": f"Bearer {token}"}).status_code == 404

    def test_stats(self, client, sample_png_bytes):
        token = _login(client)
        client.post(
            "/api/tasks/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("a.png", io.BytesIO(sample_png_bytes), "image/png")},
        )
        resp = client.get("/api/detections/stats", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 1
        assert "by_status" in data
        assert "by_class" in data
        assert "avg_confidence" in data


class TestFileServing:
    def test_result_file_served(self, client, sample_png_bytes):
        token = _login(client)
        up = client.post(
            "/api/tasks/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("a.png", io.BytesIO(sample_png_bytes), "image/png")},
        )
        result_url = up.json()["data"]["result_url"]
        path = result_url.replace("/api/files/", "")
        resp = client.get(f"/api/files/{path}", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("image/")

    def test_weights_never_served(self, client):
        token = _login(client)
        resp = client.get("/api/files/weights/model.pt", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_path_traversal_rejected(self, client):
        token = _login(client)
        resp = client.get("/api/files/../../etc/passwd", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code in (403, 404)


class TestLabelMapping:
    def test_coco_seed_maps_to_chinese(self):
        from app.services.label_mapper import COCO_ZH_SEED

        assert COCO_ZH_SEED["dog"] == "狗"
        assert COCO_ZH_SEED["cat"] == "猫"

    def test_unknown_label_falls_back_to_english(self):
        from app.services.label_mapper import LabelMapper

        mapper = LabelMapper(db=None)
        assert mapper.to_zh("unknown-widget") == "unknown-widget"
        assert mapper.to_zh("Dog") == "狗"  # case-insensitive lookup
