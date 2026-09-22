"""Live smoke for the kinglet-demo-basic canary.

Usage (from examples/demo-basic)::

    uv run pywrangler deploy
    uv run python smoke.py [base-url]

Exits non-zero on the first failure.
"""

from __future__ import annotations

import json
import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "https://kinglet-demo-basic.mitch-336.workers.dev"
TOKEN = "user-token-123"


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("PASS " if cond else "FAIL ") + name, detail)
    if not cond:
        raise SystemExit(f"smoke failed: {name} {detail}")


def main() -> None:
    client = httpx.Client(base_url=BASE, timeout=30.0)

    health = client.get("/api/")
    check("health 200", health.status_code == 200, health.text[:100])
    check("health payload", health.json().get("status") == "healthy")

    search = client.get("/api/search?page=2&limit=5&active=true&tags=python")
    check("public route 200", search.status_code == 200)
    check("typed params", search.json()["pagination"] == {"page": 2, "limit": 5})

    denied = client.get("/api/users/42")
    check("protected route 401", denied.status_code == 401, denied.text[:100])

    allowed = client.get(
        "/api/users/42", headers={"authorization": f"Bearer {TOKEN}"}
    )
    check("authorized route 200", allowed.status_code == 200, allowed.text[:100])
    check("path param", allowed.json().get("user_id") == 42)

    created = client.post("/api/auth/register", json={"email": "smoke@example.com"})
    check("JSON POST roundtrip 201", created.status_code == 201, created.text[:100])

    invalid = client.post("/api/auth/register", json={})
    check("validation 400", invalid.status_code == 400, invalid.text[:100])

    spec = client.get("/api/openapi.json")
    check("openapi 200", spec.status_code == 200)
    check("openapi paths", bool(json.loads(spec.text).get("paths")))

    print("basic smoke: all checks passed")


if __name__ == "__main__":
    main()
