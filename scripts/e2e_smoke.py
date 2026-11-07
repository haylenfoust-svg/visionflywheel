"""E2E smoke test against a running backend — run `python scripts/e2e_smoke.py <base_url>`."""

from __future__ import annotations

import sys

import httpx


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8770"
    with httpx.Client(base_url=base, timeout=10) as c:
        # 1) health (no auth)
        r = c.get("/api/system/health")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["code"] == 0, body
        print(f"[OK] health: {body['data']}")

        # 2) login
        r = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["code"] == 0, body
        token = body["data"]["access_token"]
        assert body["data"]["user"]["role"] == "admin"
        print(f"[OK] login: user={body['data']['user']['username']} role={body['data']['user']['role']}")

        headers = {"Authorization": f"Bearer {token}"}

        # 3) me
        r = c.get("/api/auth/me", headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["username"] == "admin"
        print(f"[OK] me: {r.json()['data']['username']}")

        # 4) config snapshot
        r = c.get("/api/config", headers=headers)
        assert r.status_code == 200, r.text
        values = r.json()["data"]["values"]
        print(f"[OK] config: {len(values)} keys — conf={values['default_conf_threshold']}")

        # 5) write config
        r = c.put(
            "/api/config/default_conf_threshold",
            headers=headers,
            json={"value": 0.42},
        )
        assert r.status_code == 200, r.text
        assert r.json()["data"]["value"] == 0.42
        assert r.json()["data"]["source"] == "db"
        print(f"[OK] config write: 0.42 (source=db)")

        # 6) audit trail
        r = c.get("/api/config/audit", headers=headers)
        assert r.status_code == 200, r.text
        assert len(r.json()["data"]) >= 1
        print(f"[OK] audit: {len(r.json()['data'])} entries")

        # 7) permission matrix: normal user cannot write config
        r = c.post("/api/auth/users", headers=headers, json={"username": "smoke-user", "password": "smoke-pass-123", "role": "user"})
        assert r.status_code == 201, r.text
        r = c.post("/api/auth/login", json={"username": "smoke-user", "password": "smoke-pass-123"})
        user_token = r.json()["data"]["access_token"]
        r = c.put(
            "/api/config/default_conf_threshold",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"value": 0.9},
        )
        assert r.status_code == 403, r.text
        print(f"[OK] permission: user cannot write config (403)")

    print("\n[E2E] all smoke checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
