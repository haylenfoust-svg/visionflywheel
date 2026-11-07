"""E2E smoke test — M1 auth + M2 recognition loop.

Run: `python scripts/e2e_smoke.py <base_url>` after `python -m app.seed`.
"""

from __future__ import annotations

import io
import sys
import tempfile
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))


def _make_test_png() -> bytes:
    """Deterministic PNG with a few distinct blobs."""
    import cv2
    import numpy as np

    canvas = np.full((480, 640, 3), 240, dtype=np.uint8)
    cv2.rectangle(canvas, (80, 60), (240, 220), (40, 40, 200), -1)
    cv2.circle(canvas, (450, 300), 90, (40, 180, 60), -1)
    cv2.rectangle(canvas, (300, 340), (420, 430), (200, 120, 40), -1)
    ok, buf = cv2.imencode(".png", canvas)
    assert ok
    return buf.tobytes()


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8770"
    png = _make_test_png()

    with httpx.Client(base_url=base, timeout=30) as c:
        # ---------- M1: auth ----------
        r = c.get("/api/system/health")
        assert r.status_code == 200, r.text
        health = r.json()["data"]
        print(f"[OK] health: {health}")

        r = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        assert r.status_code == 200, r.text
        token = r.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print(f"[OK] login: {r.json()['data']['user']['username']}")

        # ---------- M2: upload → detect → visualise ----------
        r = c.post(
            "/api/tasks/upload",
            headers=headers,
            files={"file": ("smoke.png", io.BytesIO(png), "image/png")},
            data={"conf_threshold": "0.3"},
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["status"] == "done", data
        assert data["detector_mode"] in ("yolo", "fallback"), data
        assert data["result_url"].startswith("/api/files/"), data
        task_id = data["task_id"]
        ndet = len(data["detections"])
        print(f"[OK] upload+detect: task={task_id} mode={data['detector_mode']} detections={ndet} ms={data['inference_ms']:.0f}")

        # Result image is served
        result_path = data["result_url"].replace("/api/files/", "")
        r = c.get(f"/api/files/{result_path}", headers=headers)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("image/"), r.headers
        print(f"[OK] result image served: {len(r.content)} bytes")

        # Detections queryable with Chinese labels
        r = c.get(f"/api/tasks/{task_id}/detections", headers=headers)
        assert r.status_code == 200, r.text
        rows = r.json()["data"]
        assert len(rows) == ndet
        if rows:
            d = rows[0]
            assert d["class_name_zh"] is not None or d["class_name"] == "object"
            assert {"x1", "y1", "x2", "y2"} <= set(d["bbox"])
        print(f"[OK] detections queried: {len(rows)} rows, labels mapped")

        # Stats
        r = c.get("/api/detections/stats", headers=headers)
        assert r.status_code == 200, r.text
        stats = r.json()["data"]
        assert stats["total"] >= ndet
        print(f"[OK] stats: total={stats['total']} avg_conf={stats['avg_confidence']}")

        # Rejection cases
        r = c.post(
            "/api/tasks/upload",
            headers=headers,
            files={"file": ("bad.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
        )
        assert r.status_code == 400, r.text
        print(f"[OK] bad extension rejected (code={r.json()['code']})")

        r = c.get("/api/files/weights/x.pt", headers=headers)
        assert r.status_code == 403, r.text
        print("[OK] weights never served")

        # ---------- M3: correction loop ----------
        det_id = rows[0]["id"] if rows else None
        if det_id is None:
            print("[SKIP] no detections to correct")
        else:
            # confirm
            r = c.post(
                "/api/corrections",
                headers=headers,
                json={"action": "confirm", "detection_id": det_id},
            )
            assert r.status_code == 200, r.text
            assert r.json()["data"]["detection_status"] == "corrected"
            print(f"[OK] confirm -> corrected (det #{det_id})")

            # relabel
            r = c.post(
                "/api/corrections",
                headers=headers,
                json={"action": "relabel", "detection_id": det_id, "new_class_name": "缺陷A"},
            )
            assert r.status_code == 200, r.text
            r = c.get(f"/api/detections/{det_id}", headers=headers)
            assert r.json()["data"]["class_name"] == "缺陷A"
            print("[OK] relabel -> class_name=缺陷A")

            # adjust
            r = c.post(
                "/api/corrections",
                headers=headers,
                json={
                    "action": "adjust",
                    "detection_id": det_id,
                    "new_bbox": {"x1": 11.0, "y1": 22.0, "x2": 111.0, "y2": 122.0},
                },
            )
            assert r.status_code == 200, r.text
            r = c.get(f"/api/detections/{det_id}", headers=headers)
            assert r.json()["data"]["bbox"]["x1"] == 11.0
            print("[OK] adjust -> bbox updated")

            # add a new box
            r = c.post(
                "/api/corrections",
                headers=headers,
                json={
                    "action": "add",
                    "task_id": task_id,
                    "new_class_name": "补检",
                    "new_bbox": {"x1": 200.0, "y1": 200.0, "x2": 300.0, "y2": 320.0},
                },
            )
            assert r.status_code == 200, r.text
            r = c.get(f"/api/tasks/{task_id}/detections", headers=headers)
            assert any(d["source"] == "manual" for d in r.json()["data"])
            print("[OK] add -> manual detection added")

            # false_positive on another detection
            if len(rows) > 1:
                r = c.post(
                    "/api/corrections",
                    headers=headers,
                    json={"action": "false_positive", "detection_id": rows[1]["id"]},
                )
                assert r.status_code == 200, r.text
                assert r.json()["data"]["detection_status"] == "rejected"
                print("[OK] false_positive -> rejected")

            # audit trail (append-only)
            r = c.get("/api/corrections/audit", headers=headers, params={"task_id": task_id})
            assert r.status_code == 200, r.text
            audit = r.json()["data"]["items"]
            actions = {a["action"] for a in audit}
            assert {"confirm", "relabel", "adjust", "add"} <= actions, actions
            print(f"[OK] audit: {len(audit)} rows, actions={sorted(actions)}")

            # undo the relabel (targeted)
            relabel_row = next(a for a in audit if a["action"] == "relabel")
            r = c.post(
                "/api/corrections/undo",
                headers=headers,
                json={"correction_id": relabel_row["id"]},
            )
            assert r.status_code == 200, r.text
            r = c.get(f"/api/detections/{det_id}", headers=headers)
            assert r.json()["data"]["class_name"] != "缺陷A", "undo should have reverted the class"
            print("[OK] undo -> class reverted")

            # immutability
            r = c.put(f"/api/corrections/{relabel_row['id']}", headers=headers, json={"action": "x"})
            assert r.status_code == 403, r.text
            assert r.json()["code"] == 40302
            print("[OK] corrections are append-only (PUT 403)")

        # feedback ticket
        r = c.post(
            "/api/feedback",
            headers=headers,
            json={"content": "这个结果需要复核", "task_id": task_id},
        )
        assert r.status_code == 201, r.text
        tid = r.json()["data"]["id"]
        r = c.put(
            f"/api/feedback/{tid}/reply",
            headers=headers,
            json={"reply": "已复核，改为缺陷A"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["data"]["status"] == "replied"
        print(f"[OK] feedback ticket #{tid} created + replied")

        # ---------- M4: dataset export + holdout + weights ----------
        r = c.get("/api/dataset/pending", headers=headers)
        assert r.status_code == 200, r.text
        pending_images = r.json()["data"]["pending_images"]
        assert pending_images >= 1, "expect at least one corrected image to export"
        print(f"[OK] dataset pending: {pending_images} images")

        r = c.post(
            "/api/dataset/export",
            headers=headers,
            json={"name": "smoke", "val_ratio": 0.2, "seed": 42},
        )
        assert r.status_code == 201, r.text
        dataset = r.json()["data"]
        assert dataset["total_labels"] >= 1
        assert len(dataset["class_names"]) >= 1
        version = dataset["dataset_version"]
        print(
            f"[OK] export {version}: train={dataset['train_images']} val={dataset['val_images']} "
            f"holdout={dataset['holdout_images']} classes={dataset['class_names']}"
        )

        # data.yaml + labels on disk
        from pathlib import Path as _Path

        from app.core.config import get_settings as _gs

        runtime_root = _Path(_gs().upload_dir).parent.resolve()
        root = runtime_root / "datasets" / version
        assert (root / "data.yaml").is_file(), f"missing data.yaml under {root}"
        train_imgs = list((root / "images" / "train").glob("*"))
        val_imgs = list((root / "images" / "val").glob("*"))
        assert train_imgs or val_imgs
        assert (root / "labels" / "train").is_dir() and (root / "labels" / "val").is_dir()
        # labels are normalised to 0..1
        for lbl in (root / "labels").rglob("*.txt"):
            for line in lbl.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                cls, cx, cy, bw, bh = line.split()
                assert cls.isdigit()
                for v in (cx, cy, bw, bh):
                    f = float(v)
                    assert 0.0 <= f <= 1.0
        print(f"[OK] yolo layout verified: train={len(train_imgs)} val={len(val_imgs)} labels normalised")

        # holdout freeze
        r = c.get("/api/dataset/holdout", headers=headers)
        assert r.status_code == 200, r.text
        holdout_items = r.json()["data"]["items"]
        for item in holdout_items:
            assert item["split"] == "holdout"
            assert item["is_frozen"] is True
        print(f"[OK] holdout: {len(holdout_items)} frozen images")

        # second export should find nothing new (idempotent w.r.t. images)
        r = c.post("/api/dataset/export", headers=headers, json={"name": "smoke2"})
        assert r.status_code == 409, r.text
        print("[OK] second export finds nothing new (409)")

        # download zip
        r = c.get(f"/api/dataset/{version}/download", headers=headers)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/zip"
        print(f"[OK] dataset zip download: {len(r.content)} bytes")

        # weights
        from app.core.config import get_settings as _gs2

        weights_dir = _Path(_gs2().weights_dir)
        weights_dir.mkdir(parents=True, exist_ok=True)
        (weights_dir / "smoke_best.pt").write_bytes(b"0" * 8192)

        r = c.get("/api/weights", headers=headers)
        assert r.status_code == 200, r.text
        weights = r.json()["data"]
        target = next(w for w in weights if w["filename"] == "smoke_best.pt")
        print(f"[OK] weights registered: {len(weights)} entries")

        r = c.put(f"/api/weights/{target['id']}/default", headers=headers)
        assert r.status_code == 200, r.text
        swap = r.json()["data"]
        assert swap["is_default"] is True
        assert swap["requires_restart"] is False  # FR-6.5 / G4
        print(f"[OK] hot-swap default weight in {swap['reloaded_in_ms']:.0f}ms (requires_restart=false)")

        # training is gated in fallback mode (ADR-002)
        r = c.post(
            "/api/train",
            headers=headers,
            json={"dataset_version": version, "epochs": 1},
        )
        assert r.status_code == 403, r.text
        assert r.json()["code"] == 40303
        print("[OK] training gated in fallback mode (403)")

    print("\n[E2E] M1 + M2 + M3 + M4 smoke checks all passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
