"""Live smoke for the kinglet-demo-r2 canary (ASGI + R2 binary).

Uploads a deterministic binary fixture, downloads it back, and asserts
exact SHA-256 integrity plus the stored MIME type — no base64 or string
expansion anywhere on the path.

Usage (from examples/demo-r2)::

    uv run pywrangler deploy
    uv run python smoke.py [base-url]

Exits non-zero on the first failure.
"""

from __future__ import annotations

import hashlib
import sys

import httpx

BASE = (
    sys.argv[1]
    if len(sys.argv) > 1
    else "https://kinglet-demo-r2.mitch-336.workers.dev"
)
MIME = "application/octet-stream"


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("PASS " if cond else "FAIL ") + name, detail)
    if not cond:
        raise SystemExit(f"smoke failed: {name} {detail}")


def main() -> None:
    client = httpx.Client(base_url=BASE, timeout=60.0)
    # Deterministic fixture covering every byte value (~100 KiB).
    fixture = bytes(range(256)) * 400
    digest = hashlib.sha256(fixture).hexdigest()

    uploaded = client.post("/media", content=fixture, headers={"Content-Type": MIME})
    check("upload 200", uploaded.status_code == 200, uploaded.text[:150])
    payload = uploaded.json()
    check("upload size", payload.get("size") == len(fixture), str(payload))
    media_id = payload["id"]

    downloaded = client.get(f"/media/{media_id}")
    check("download 200", downloaded.status_code == 200)
    body = bytes(downloaded.content)
    check("exact length", len(body) == len(fixture), f"{len(body)} bytes")
    check(
        "SHA-256 match",
        hashlib.sha256(body).hexdigest() == digest,
        hashlib.sha256(body).hexdigest(),
    )
    check(
        "MIME preserved",
        (downloaded.headers.get("content-type") or "").startswith(MIME),
        downloaded.headers.get("content-type", ""),
    )

    # The r2_put helper path stores an identical copy under -helper.
    helper = client.get(f"/media/{media_id}-helper")
    check("helper copy 200", helper.status_code == 200)
    check(
        "helper SHA-256 match",
        hashlib.sha256(bytes(helper.content)).hexdigest() == digest,
    )

    missing = client.get("/media/does-not-exist")
    check("missing 404", missing.status_code == 404, missing.text[:100])

    print("r2 smoke: all checks passed")


if __name__ == "__main__":
    main()
