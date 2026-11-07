"""Dataset export / holdout / weight hot-swap tests (PRD FR-5 FR-6)."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest


def _login(client, username="admin", password="admin-password-123") -> str:
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["data"]["access_token"]


@pytest.fixture
def corrected_task(client, tmp_path):
    """Upload + confirm a detection so there's something exportable."""
    from app.utils.imaging import make_test_image

    png = make_test_image(tmp_path / "s.png").read_bytes()
    token = _login(client)
    up = client.post(
        "/api/tasks/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("s.png", io.BytesIO(png), "image/png")},
    )
    assert up.status_code == 200, up.text
    data = up.json()["data"]
    for det in data["detections"]:
        r = client.post(
            "/api/corrections",
            headers={"Authorization": f"Bearer {token}"},
            json={"action": "confirm", "detection_id": det["id"]},
        )
        assert r.status_code == 200
    return data


class TestDatasetExport:
    def test_export_produces_yolo_layout(self, client, corrected_task):
        token = _login(client)
        resp = client.post(
            "/api/dataset/export",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "smoke", "val_ratio": 0.2, "seed": 42},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]
        assert data["dataset_version"].startswith("smoke-")
        assert data["total_labels"] >= 1
        assert len(data["class_names"]) >= 1

        # Verify on disk
        version = data["dataset_version"]
        from app.core.config import get_settings

        runtime_root = Path(get_settings().upload_dir).parent.resolve()
        root = runtime_root / "datasets" / version
        assert (root / "data.yaml").is_file()
        assert (root / "images" / "train").is_dir()
        assert (root / "images" / "val").is_dir()
        assert (root / "labels" / "train").is_dir()
        assert (root / "labels" / "val").is_dir()

    def test_data_yaml_is_valid(self, client, corrected_task):
        token = _login(client)
        version = client.post(
            "/api/dataset/export",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "yaml-check"},
        ).json()["data"]["dataset_version"]

        from app.core.config import get_settings

        runtime_root = Path(get_settings().upload_dir).parent.resolve()
        yaml_text = (runtime_root / "datasets" / version / "data.yaml").read_text(encoding="utf-8")
        assert "train: images/train" in yaml_text
        assert "val: images/val" in yaml_text
        assert "names:" in yaml_text

    def test_labels_are_normalised(self, client, corrected_task):
        token = _login(client)
        version = client.post(
            "/api/dataset/export",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "norm-check"},
        ).json()["data"]["dataset_version"]

        from app.core.config import get_settings

        runtime_root = Path(get_settings().upload_dir).parent.resolve()
        root = runtime_root / "datasets" / version
        labels = list((root / "labels").rglob("*.txt"))
        assert labels, "expected at least one label file"
        for lbl in labels:
            for line in lbl.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                parts = line.split()
                assert len(parts) == 5, f"want 'class cx cy w h', got: {line!r}"
                cls, cx, cy, bw, bh = parts
                assert cls.isdigit()
                for value in (cx, cy, bw, bh):
                    v = float(value)
                    assert 0.0 <= v <= 1.0, f"value out of range: {value}"

    def test_export_is_idempotent_wrt_images(self, client, corrected_task):
        """The same image should not appear in two different dataset exports."""
        token = _login(client)
        r1 = client.post(
            "/api/dataset/export",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "first"},
        )
        assert r1.status_code == 201
        r2 = client.post(
            "/api/dataset/export",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "second"},
        )
        assert r2.status_code == 409, "second export should find nothing new"

    def test_download_zip(self, client, corrected_task):
        token = _login(client)
        version = client.post(
            "/api/dataset/export",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "zip-check"},
        ).json()["data"]["dataset_version"]
        resp = client.get(f"/api/dataset/{version}/download", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        names = zf.namelist()
        assert "data.yaml" in names


class TestHoldout:
    def test_holdout_is_recorded(self, client, corrected_task):
        token = _login(client)
        client.post(
            "/api/dataset/export",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "holdout-check"},
        )
        r = client.get("/api/dataset/holdout", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        for item in items:
            assert item["split"] == "holdout"
            assert item["is_frozen"] is True

    def test_holdout_never_in_train_val(self, client, corrected_task):
        """Frozen holdout images must not leak into train/val dirs."""
        token = _login(client)
        client.post(
            "/api/dataset/export",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "no-leak"},
        )
        r = client.get("/api/dataset/holdout", headers={"Authorization": f"Bearer {token}"})
        holdout_paths = {item["image_path"] for item in r.json()["data"]["items"]}

        from app.core.config import get_settings

        runtime_root = Path(get_settings().upload_dir).parent.resolve()
        for version_dir in (runtime_root / "datasets").iterdir():
            for split in ("train", "val"):
                for img in (version_dir / "images" / split).glob("*"):
                    # Just verify the split mapping does not place holdout images in train/val
                    # (mapping is by filename stem; checking holdout paths is enough here)
                    assert img.name not in {Path(p).name for p in holdout_paths}


class TestWeightManager:
    def test_register_trained_weight(self, client, corrected_task, tmp_path):
        from app.core.config import get_settings

        weights_dir = Path(get_settings().weights_dir)
        weights_dir.mkdir(parents=True, exist_ok=True)
        fake = weights_dir / "best_test.pt"
        fake.write_bytes(b"0" * 4096)

        token = _login(client)
        r = client.get("/api/weights", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        names = [w["filename"] for w in r.json()["data"]]
        assert "best_test.pt" in names

    def test_hot_swap_returns_requires_restart_false(self, client, tmp_path):
        from app.core.config import get_settings

        weights_dir = Path(get_settings().weights_dir)
        weights_dir.mkdir(parents=True, exist_ok=True)
        (weights_dir / "swap_a.pt").write_bytes(b"0" * 4096)
        (weights_dir / "swap_b.pt").write_bytes(b"0" * 4096)

        token = _login(client)
        weights = client.get("/api/weights", headers={"Authorization": f"Bearer {token}"}).json()["data"]
        target = next(w for w in weights if w["filename"] == "swap_b.pt")
        resp = client.put(
            f"/api/weights/{target['id']}/default",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["is_default"] is True
        assert data["requires_restart"] is False  # FR-6.5 / G4

    def test_user_cannot_hot_swap(self, client, tmp_path):
        from app.core.config import get_settings

        weights_dir = Path(get_settings().weights_dir)
        weights_dir.mkdir(parents=True, exist_ok=True)
        (weights_dir / "user_swap.pt").write_bytes(b"0" * 4096)

        token = _login(client, "tester", "test-password-123")
        weights = client.get("/api/weights", headers={"Authorization": f"Bearer {token}"}).json()["data"]
        if weights:
            resp = client.put(
                f"/api/weights/{weights[0]['id']}/default",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 403


class TestTrainingGating:
    def test_training_rejected_in_fallback_mode(self, client, corrected_task):
        """ADR-002: fallback detector cannot train."""
        token = _login(client)
        version = client.post(
            "/api/dataset/export",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "train-gate"},
        ).json()["data"]["dataset_version"]
        resp = client.post(
            "/api/train",
            headers={"Authorization": f"Bearer {token}"},
            json={"dataset_version": version, "epochs": 1},
        )
        # Without ultralytics installed the detector is 'fallback' -> 403
        assert resp.status_code == 403
        assert resp.json()["code"] == 40303
