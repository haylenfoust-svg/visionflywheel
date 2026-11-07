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

    print("\n[E2E] M1 + M2 smoke checks all passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
