"""Live smoke for the kinglet-demo-totp legacy canary.

The demo keeps its ``WorkerEntrypoint`` + ``await app(request, self.env)``
entry deliberately: it proves existing Worker deployments still work. This
smoke exercises JWT auth, TOTP setup/verify, Web Crypto secret roundtrip
and elevated sessions through that legacy path.

Usage (from examples/totp_workers_demo)::

    uv run pywrangler deploy
    uv run python smoke.py [base-url]

Exits non-zero on the first failure.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import struct
import sys
import time

import httpx

BASE = (
    sys.argv[1]
    if len(sys.argv) > 1
    else "https://kinglet-demo-totp.mitch-336.workers.dev"
)
JWT_SECRET = "totp-workers-demo-jwt-secret"


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("PASS " if cond else "FAIL ") + name, detail)
    if not cond:
        raise SystemExit(f"smoke failed: {name} {detail}")


def mint(claims: dict) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip(
        "="
    )
    sig = hmac.new(
        JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256
    ).digest()
    return f"{header}.{payload}." + base64.urlsafe_b64encode(sig).decode().rstrip(
        "="
    )


def totp_code(secret_b32: str, at: int | None = None) -> str:
    """RFC 6238 TOTP (SHA1, 30s step, 6 digits) for smoke verification."""
    key = base64.b32decode(secret_b32.upper())
    counter = struct.pack(">Q", int((at if at is not None else time.time()) // 30))
    digest = hmac.new(key, counter, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{code % 1_000_000:06d}"


def main() -> None:
    client = httpx.Client(base_url=BASE, timeout=30.0)
    token = mint({"sub": "smoke-user", "exp": int(time.time()) + 600})
    auth = {"authorization": f"Bearer {token}"}

    health = client.get("/")
    check("health 200", health.status_code == 200, health.text[:100])

    info = client.get("/auth/totp/test-info")
    check("test-info 200", info.status_code == 200)
    check("jwt secret present", info.json().get("has_jwt_secret") is True)

    denied = client.post("/auth/totp/setup")
    check("setup denied without auth", denied.status_code == 401)

    setup = client.post("/auth/totp/setup", headers=auth)
    check("setup 200", setup.status_code == 200, setup.text[:150])
    secret = setup.json()["secret"]
    check("qr url", setup.json().get("qr_url", "").startswith("otpauth://"))

    verify = client.post(
        "/auth/totp/verify",
        headers=auth,
        json={"secret": secret, "code": totp_code(secret)},
    )
    check("verify valid 200", verify.status_code == 200, verify.text[:150])
    check("verify true", verify.json().get("valid") is True)

    bad = client.post(
        "/auth/totp/verify", headers=auth, json={"secret": secret, "code": "000000"}
    )
    check("verify wrong code", bad.json().get("valid") is False)

    roundtrip = client.post("/auth/totp/roundtrip", headers=auth, json={})
    check("webcrypto roundtrip 200", roundtrip.status_code == 200, roundtrip.text[:200])
    check("roundtrip ok", roundtrip.json().get("ok") is True)

    elevated = client.get("/auth/totp/elevated-check", headers=auth)
    check("elevation required 403", elevated.status_code == 403, elevated.text[:150])

    print("totp smoke: all checks passed")


if __name__ == "__main__":
    main()
