"""Config three-tier priority tests (ADR-003)."""

from __future__ import annotations

import os

from app.services.config_service import ConfigService


def test_default_when_no_db_no_env():
    svc = ConfigService()
    os.environ.pop("VF_DEFAULT_CONF_THRESHOLD", None)

    class FakeDB:
        def query(self, *_args, **_kwargs):
            class Q:
                def filter(self, *_args, **_kwargs):
                    return self

                def first(self):
                    return None

            return Q()

    value, source = svc.get_with_source(FakeDB(), "default_conf_threshold")
    assert source == "default"
    assert value == 0.5


def test_db_overrides_default(client, admin_token):
    # write 0.3 to DB
    client.put(
        "/api/config/default_conf_threshold",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"value": 0.3},
    )
    resp = client.get("/api/config", headers={"Authorization": f"Bearer {admin_token}"})
    entry = resp.json()["data"]["values"]["default_conf_threshold"]
    assert entry["value"] == 0.3
    assert entry["source"] == "db"


def test_reset_falls_back_to_default(client, admin_token):
    client.put(
        "/api/config/default_conf_threshold",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"value": 0.9},
    )
    client.delete("/api/config/default_conf_threshold", headers={"Authorization": f"Bearer {admin_token}"})
    resp = client.get("/api/config", headers={"Authorization": f"Bearer {admin_token}"})
    entry = resp.json()["data"]["values"]["default_conf_threshold"]
    assert entry["value"] == 0.5
    assert entry["source"] == "default"


def test_unknown_key_rejected(client, admin_token):
    resp = client.put(
        "/api/config/nonexistent_key",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"value": 1},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == 40001


def test_config_audit_recorded(client, admin_token):
    client.put(
        "/api/config/default_iou_threshold",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"value": 0.7},
    )
    resp = client.get("/api/config/audit", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    keys = [a["entity_key"] for a in resp.json()["data"]]
    assert "default_iou_threshold" in keys
