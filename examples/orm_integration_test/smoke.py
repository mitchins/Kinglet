"""Live smoke for the kinglet-demo-orm canary (ASGI + D1).

Usage (from examples/orm_integration_test)::

    uv run pywrangler deploy
    uv run python smoke.py [base-url]

Exits non-zero on the first failure.
"""

from __future__ import annotations

import sys
import uuid

import httpx

BASE = (
    sys.argv[1]
    if len(sys.argv) > 1
    else "https://kinglet-demo-orm.mitch-336.workers.dev"
)
TOKEN = "demo-migrate-token"


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("PASS " if cond else "FAIL ") + name, detail)
    if not cond:
        raise SystemExit(f"smoke failed: {name} {detail}")


def main() -> None:
    client = httpx.Client(base_url=BASE, timeout=30.0)
    tag = uuid.uuid4().hex[:8]

    migrated = client.post("/migrate", headers={"Authorization": f"Bearer {TOKEN}"})
    check("migrate 200", migrated.status_code == 200, migrated.text[:150])

    created = client.post(
        "/games", json={"title": f"smoke-{tag}", "score": 7, "metadata": {"t": tag}}
    )
    check("create 200", created.status_code == 200, created.text[:150])
    game_id = created.json()["game"]["id"]
    check("nullable description", "description" in created.json()["game"])

    fetched = client.get(f"/games/{game_id}")
    check("retrieve 200", fetched.status_code == 200)
    check("retrieve payload", fetched.json()["game"]["title"] == f"smoke-{tag}")

    updated = client.put(f"/games/{game_id}", json={"score": 42})
    check("update 200", updated.status_code == 200)
    check("update payload", updated.json()["game"]["score"] == 42)

    email = f"smoke-{tag}@example.com"
    user1 = client.post(
        "/users", json={"email": email, "username": f"smoke-{tag}"}
    )
    check("user create 200", user1.status_code == 200, user1.text[:150])

    user2 = client.post(
        "/users", json={"email": email, "username": f"smoke-{tag}-dup"}
    )
    check("constraint error 400", user2.status_code == 400, user2.text[:150])

    listed = client.get("/games")
    check("list 200", listed.status_code == 200)
    check("list non-empty", listed.json().get("total", 0) >= 1)

    filtered = client.get("/games?min_score=40")
    check("filter 200", filtered.status_code == 200)
    check(
        "filter applies",
        all(g["score"] >= 40 for g in filtered.json().get("games", [])),
    )

    deleted = client.delete(f"/games/{game_id}")
    check("delete 200", deleted.status_code == 200, deleted.text[:150])

    gone = client.get(f"/games/{game_id}")
    check("deleted gone 404", gone.status_code == 404, gone.text[:150])

    print("orm smoke: all checks passed")


if __name__ == "__main__":
    main()
