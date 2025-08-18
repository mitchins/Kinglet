# kinglet/authz.py
import base64
import hashlib
import hmac
import json
import time
from typing import Any, Awaitable, Callable, Optional

from .http import Response  # Import directly from http module
from .totp import DummyOTPProvider, set_otp_provider  # TOTP support


# ---------- JWT (HS256) minimal ----------
def _b64url_decode(s: str) -> bytes:
    s += "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s.encode())

def verify_jwt_hs256(token: str, secret: str) -> Optional[dict]:
    try:
        h_b64, p_b64, s_b64 = token.split(".")
        signing = f"{h_b64}.{p_b64}".encode()
        sig = _b64url_decode(s_b64)
        want = hmac.new(secret.encode(), signing, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, want):
            return None
        payload = json.loads(_b64url_decode(p_b64))
        now = int(time.time())
        if "nbf" in payload and now < int(payload["nbf"]): return None
        if "exp" in payload and now >= int(payload["exp"]): return None
        return payload
    except Exception:
        return None

async def get_user(req, *, env_key="JWT_SECRET") -> Optional[dict]:
    """
    Returns {"id": <user_id>, "claims": {...}} or None.
    Prefers Bearer token; falls back to Cloudflare Access JWT header if present.
    """
    # Bearer token
    auth = (getattr(req, "header", lambda *_: None)("authorization") or "")
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
        secret = getattr(req.env, env_key, None)
        if secret:
            claims = verify_jwt_hs256(token, secret)
            if claims:
                uid = claims.get("sub") or claims.get("uid") or claims.get("user_id")
                if uid:
                    return {"id": str(uid), "claims": claims}
    # Cloudflare Access (optional): CF-Access-Jwt-Assertion already verified by Access
    access_jwt = (getattr(req, "header", lambda *_: None)("cf-access-jwt-assertion") or
                  getattr(req, "header", lambda *_: None)("cf-access-jwt"))  # relax
    if access_jwt:
        # Trust upstream; parse payload without verify (optional: add JWKS verification later)
        try:
            _, p_b64, _ = access_jwt.split(".")
            claims = json.loads(_b64url_decode(p_b64))
            uid = claims.get("sub") or claims.get("email") or claims.get("user_uuid")
            if uid:
                return {"id": str(uid), "claims": claims}
        except Exception:
            pass
    return None

# ---------- Relationship resolvers (pluggable) ----------
# You supply these per resource; keep them tiny + fast.

# Example D1 owner resolver (table with columns: id TEXT PRIMARY KEY, owner_id TEXT, public INTEGER)
async def d1_load_owner_public(d1, table: str, rid: str) -> Optional[dict]:
    sql = f"SELECT owner_id, public FROM {table} WHERE id=? LIMIT 1"
    row = (await d1.prepare(sql).bind(rid).first()) or None
    if not row: return None
    return {"owner_id": str(row["owner_id"]), "public": bool(row["public"])}

# Example R2 media owner resolver (owner_id stored in customMetadata.owner_id)
async def r2_media_owner(env, bucket_binding: str, key: str) -> Optional[dict]:
    bucket = getattr(env, bucket_binding)
    head = await (bucket.head(key) if hasattr(bucket, "head") else bucket.get(key))
    if not head: return None
    owner = None
    try:
        meta = getattr(head, "customMetadata", None)
        if meta: owner = meta.get("owner_id") or meta.get("owner")
    except Exception:
        pass
    return {"owner_id": str(owner) if owner else None, "public": False}

# ---------- Decorators ----------
def require_auth(handler: Callable[[Any], Awaitable[Any]]):
    async def wrapped(req):
        user = await get_user(req)
        if not user:
            return Response({"error": "unauthorized"}, status=401)
        req.state = getattr(req, "state", type("S", (), {})())  # cheap state bag
        req.state.user = user
        return await handler(req)
    return wrapped

def allow_public_or_owner(
    load_fn: Callable[[Any, str], Awaitable[Optional[dict]]],
    *, id_param="uid", forbidden_as_404=True
):
    """
    load_fn(req, rid) -> {"owner_id": str, "public": bool} or None
    """
    def deco(handler):
        async def wrapped(req):
            rid = req.path_param(id_param)
            rec = await load_fn(req, rid)
            if not rec:
                return Response({"error": "not found"}, status=404)
            if rec.get("public", False):
                return await handler(req, obj=rec)
            user = await get_user(req)
            if user and rec.get("owner_id") and str(user["id"]) == str(rec["owner_id"]):
                req.state = getattr(req, "state", type("S", (), {})())
                req.state.user = user
                return await handler(req, obj=rec)
            # Deny: optionally hide existence
            if forbidden_as_404:
                return Response({"error": "not found"}, status=404)
            return Response({"error": "forbidden"}, status=403)
        return wrapped
    return deco

def require_owner(
    load_fn: Callable[[Any, str], Awaitable[Optional[dict]]],
    *, id_param="uid", allow_admin_env="ADMIN_IDS"
):
    def deco(handler):
        async def wrapped(req):
            user = await get_user(req)
            if not user:
                return Response({"error": "unauthorized"}, status=401)
            rid = req.path_param(id_param)
            rec = await load_fn(req, rid)
            if not rec:
                return Response({"error": "not found"}, status=404)
            uid = str(user["id"])
            if rec.get("owner_id") and uid == str(rec["owner_id"]):
                req.state = getattr(req, "state", type("S", (), {})())
                req.state.user = user
                return await handler(req, obj=rec)
            # optional admin escape hatch (comma-separated IDs in env)
            admin_ids = (getattr(req.env, allow_admin_env, "") or "").split(",")
            if uid in {a.strip() for a in admin_ids if a.strip()}:
                return await handler(req, obj=rec)
            return Response({"error": "forbidden"}, status=403)
        return wrapped
    return deco

def require_participant(
    load_participants_fn: Callable[[Any, str], Awaitable[set[str]]],
    *, id_param="conversation_id", allow_admin_env="ADMIN_IDS"
):
    def deco(handler):
        async def wrapped(req):
            user = await get_user(req)
            if not user:
                return Response({"error": "unauthorized"}, status=401)
            cid = req.path_param(id_param)
            participants = await load_participants_fn(req, cid)
            uid = str(user["id"])
            if uid in participants:
                req.state = getattr(req, "state", type("S", (), {})())
                req.state.user = user
                return await handler(req)
            admin_ids = (getattr(req.env, allow_admin_env, "") or "").split(",")
            if uid in {a.strip() for a in admin_ids if a.strip()}:
                return await handler(req)
            return Response({"error": "forbidden"}, status=403)
        return wrapped
    return deco
# ---------- Session Elevation Decorators ----------

def require_elevated_session(handler: Callable[[Any], Awaitable[Any]]):
    """Require elevated session (TOTP verified) - skips if TOTP_ENABLED=false"""
    async def wrapped(req):
        user = await get_user(req)
        if not user:
            return Response({"error": "authentication required"}, status=401)

        # Check if TOTP is enabled in this environment
        totp_enabled = getattr(req.env, 'TOTP_ENABLED', 'true').lower() == 'true'
        if not totp_enabled:
            # TOTP disabled - just require basic auth (already validated above)
            req.state = getattr(req, "state", type("S", (), {})())
            req.state.user = user
            return await handler(req)

        claims = user.get('claims', {})

        # Check if session is elevated
        if not claims.get('elevated', False):
            return Response({
                "error": "elevated session required",
                "code": "ELEVATION_REQUIRED",
                "step_up_url": "/auth/totp/step-up"
            }, status=403)

        # Check elevation hasn't expired (double-check beyond JWT exp)
        elevation_time = claims.get('elevation_time', 0)
        current_time = time.time()
        if current_time - elevation_time > 900:  # 15 minutes
            return Response({
                "error": "elevated session expired",
                "code": "ELEVATION_EXPIRED",
                "step_up_url": "/auth/totp/step-up"
            }, status=403)

        req.state = getattr(req, "state", type("S", (), {})())
        req.state.user = user
        return await handler(req)

    return wrapped

def require_claim(claim_name: str, claim_value: Any = True):
    """Require specific claim in JWT (app-specific like 'publisher', 'host')"""
    def deco(handler):
        async def wrapped(req):
            user = await get_user(req)
            if not user:
                return Response({"error": "authentication required"}, status=401)

            claims = user.get('claims', {})
            actual_value = claims.get(claim_name)

            if actual_value != claim_value:
                return Response({
                    "error": "insufficient privileges",
                    "code": "MISSING_CLAIM",
                    "required_claim": claim_name,
                    "required_value": claim_value
                }, status=403)

            req.state = getattr(req, "state", type("S", (), {})())
            req.state.user = user
            return await handler(req)
        return wrapped
    return deco

def require_elevated_claim(claim_name: str, claim_value: Any = True):
    """Require both elevated session AND specific claim - skips elevation if TOTP_ENABLED=false"""
    def deco(handler):
        async def wrapped(req):
            user = await get_user(req)
            if not user:
                return Response({"error": "authentication required"}, status=401)

            claims = user.get('claims', {})

            # Check if TOTP is enabled in this environment
            totp_enabled = getattr(req.env, 'TOTP_ENABLED', 'true').lower() == 'true'

            # Check elevation first (only if TOTP enabled)
            if totp_enabled and not claims.get('elevated', False):
                return Response({
                    "error": "elevated session required",
                    "code": "ELEVATION_REQUIRED",
                    "step_up_url": "/auth/totp/step-up"
                }, status=403)

            # Check specific claim
            actual_value = claims.get(claim_name)
            if actual_value != claim_value:
                return Response({
                    "error": "insufficient privileges",
                    "code": "MISSING_CLAIM",
                    "required_claim": claim_name,
                    "required_value": claim_value
                }, status=403)

            req.state = getattr(req, "state", type("S", (), {})())
            req.state.user = user
            return await handler(req)
        return wrapped
    return deco



def configure_otp_provider(env) -> None:
    """Configure OTP provider based on TOTP_ENABLED environment variable"""
    totp_enabled = getattr(env, 'TOTP_ENABLED', 'true').lower() == 'true'
    if not totp_enabled:
        # Use dummy provider for development/testing
        set_otp_provider(DummyOTPProvider())
    # Production provider is the default
