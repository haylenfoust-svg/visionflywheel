"""P2 tests — weight regression gate, async queue, drift action loop."""

from __future__ import annotations


def _login(client, username="admin", password="admin-password-123") -> str:
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["data"]["access_token"]


class TestWeightRegressionGate:
    """P2.1 — new weights must not regress holdout metrics."""

    def _register_weight(self, db_session, filename: str, holdout_map: float, is_default: bool = False):
        from pathlib import Path

        from app.core.config import get_settings
        from app.models.weight import Weight

        weights_dir = Path(get_settings().weights_dir)
        weights_dir.mkdir(parents=True, exist_ok=True)
        (weights_dir / filename).write_bytes(b"0" * 4096)
        w = Weight(filename=filename, path=str(weights_dir / filename),
                   is_default=is_default, source="trained",
                   holdout_map=holdout_map)
        db_session.add(w)
        db_session.commit()
        db_session.refresh(w)
        return w

    def test_gate_blocks_regression(self, client, db_session):
        self._register_weight(db_session, "baseline.pt", 0.85, is_default=True)
        target = self._register_weight(db_session, "target_worse.pt", 0.70)
        token = _login(client)
        r = client.get(f"/api/weights/{target.id}/gate", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200  # gate evaluate returns 200
        data = r.json()["data"]
        assert data["allowed"] is False
        assert data["delta"] < 0
        assert data["policy"] == "block"

    def test_gate_allows_improvement(self, client, db_session):
        self._register_weight(db_session, "baseline.pt", 0.75, is_default=True)
        target = self._register_weight(db_session, "target_better.pt", 0.88)
        token = _login(client)
        r = client.get(f"/api/weights/{target.id}/gate", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["allowed"] is True
        assert data["delta"] > 0

    def test_gated_switch_force_overrides(self, client, db_session):
        self._register_weight(db_session, "baseline.pt", 0.90, is_default=True)
        target = self._register_weight(db_session, "target_worse.pt", 0.60)
        token = _login(client)
        r = client.post(
            f"/api/weights/{target.id}/switch-gated",
            headers={"Authorization": f"Bearer {token}"},
            json={"force": True},
        )
        assert r.status_code == 200
        assert r.json()["data"]["gate"]["forced"] is True


class TestInferenceQueue:
    """P2.2 — async job submission and progress tracking."""

    def test_submit_async_job(self, client):
        token = _login(client)
        r = client.post("/api/tasks/submit-async", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()["data"]
        assert "id" in data
        assert data["kind"] == "demo"

    def test_job_poll_returns_progress(self, client):
        token = _login(client)
        r = client.post("/api/tasks/submit-async", headers={"Authorization": f"Bearer {token}"})
        job_id = r.json()["data"]["id"]
        r2 = client.get(f"/api/tasks/jobs/{job_id}", headers={"Authorization": f"Bearer {token}"})
        assert r2.status_code == 200
        assert r2.json()["data"]["id"] == job_id

    def test_job_not_found(self, client):
        token = _login(client)
        r = client.get("/api/tasks/jobs/nonexistent", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 404

    def test_queue_concurrency(self, client):
        token = _login(client)
        ids = []
        for _ in range(3):
            r = client.post("/api/tasks/submit-async", headers={"Authorization": f"Bearer {token}"})
            ids.append(r.json()["data"]["id"])
        assert len(set(ids)) == 3

    def test_job_to_dict_shape(self):
        from app.services.inference_queue import InferenceJob, job_to_dict

        job = InferenceJob(id="test123", kind="image", status="done", progress=1.0)
        d = job_to_dict(job)
        assert d["id"] == "test123"
        assert d["status"] == "done"


class TestDriftActionLoop:
    """P2.3 — drift -> alert -> rollback -> optional retrain."""

    def test_drift_action_returns_report(self, client, db_session):
        token = _login(client)
        r = client.post("/api/stats/drift/action", headers={"Authorization": f"Bearer {token}"}, params={"days": 30, "notify": False})
        assert r.status_code == 200
        data = r.json()["data"]
        assert "report" in data
        assert "actions" in data
        assert "summary" in data

    def test_rollback_recommendation_present(self, client, db_session):
        token = _login(client)
        r = client.post("/api/stats/drift/action", headers={"Authorization": f"Bearer {token}"}, params={"days": 30, "notify": False})
        data = r.json()["data"]
        rollback_actions = [a for a in data["actions"] if a["type"] == "rollback_recommendation"]
        assert len(rollback_actions) == 1
        assert "result" in rollback_actions[0]
