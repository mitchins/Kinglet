"""
Kinglet TOTP Workers Demo

This demo exercises the auth and TOTP surface against a real Workers runtime.
"""

import traceback

from kinglet import Kinglet, Response
from kinglet.authz import configure_otp_provider, require_auth, require_elevated_session
from kinglet.totp import (
    create_elevated_jwt,
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_totp_qr_url,
    generate_totp_secret,
    verify_totp_code,
)

try:
    from workers import WorkerEntrypoint
except ModuleNotFoundError:

    class WorkerEntrypoint:
        def __init__(self, ctx=None, env=None):
            self.ctx = ctx
            self.env = env


app = Kinglet(debug=False)


def _env_get(env, key: str, default=None):
    if isinstance(env, dict):
        return env.get(key, default)
    return getattr(env, key, default)


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        configure_otp_provider(self.env)
        return await app(request, self.env)


@app.get("/", public=True)
async def health(request):
    return {"status": "healthy", "demo": "kinglet-totp-workers-demo"}


@app.get("/auth/totp/test-info", public=True)
async def test_info(request):
    return {
        "environment": _env_get(request.env, "ENVIRONMENT", "unknown"),
        "totp_enabled": str(_env_get(request.env, "TOTP_ENABLED", "true")).lower()
        == "true",
        "has_jwt_secret": bool(_env_get(request.env, "JWT_SECRET", None)),
    }


@app.post("/auth/totp/setup")
@require_auth
async def setup_totp(request):
    user = request.state.user
    claims = user.get("claims", {})
    secret = generate_totp_secret()
    return {
        "user_id": user["id"],
        "secret": secret,
        "qr_url": generate_totp_qr_url(
            secret,
            claims.get("email", f"user-{user['id']}"),
            "KingletWorkersDemo",
        ),
    }


@app.post("/auth/totp/verify")
@require_auth
async def verify_totp(request):
    body = await request.json() or {}
    secret = body.get("secret", "")
    code = body.get("code", "")

    if not secret or not code:
        return Response({"error": "Code and secret required"}, status=400)

    return {
        "valid": verify_totp_code(secret, code),
        "user_id": request.state.user["id"],
    }


@app.post("/auth/totp/roundtrip")
@require_auth
async def roundtrip_secret(request):
    body = await request.json() or {}
    secret = body.get("secret") or generate_totp_secret()
    try:
        encrypted = encrypt_totp_secret(secret, request.env)
        decrypted = decrypt_totp_secret(encrypted, request.env)
    except Exception as exc:
        if str(_env_get(request.env, "MODE", "")).strip().lower() != "prod":
            return Response(
                {
                    "error": "roundtrip failed",
                    "detail": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(),
                },
                status=500,
            )
        raise

    return {
        "secret": secret,
        "encrypted": encrypted,
        "decrypted": decrypted,
        "ok": secret == decrypted,
    }


@app.get("/auth/totp/elevated-check")
@require_elevated_session
async def elevated_check(request):
    claims = request.state.user.get("claims", {})
    elevated_token = create_elevated_jwt(
        {"sub": request.state.user["id"], "email": claims.get("email", "")},
        _env_get(request.env, "JWT_SECRET"),
    )
    return {
        "ok": True,
        "user_id": request.state.user["id"],
        "elevated_token_preview": elevated_token[:24],
    }
