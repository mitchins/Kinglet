"""
Kinglet Authorization Demo - Simple authentication patterns
"""

import kinglet.authz
from kinglet import Kinglet, Response, security_decorator
from kinglet.authz import require_auth

app = Kinglet()


@app.get("/", public=True)
async def home(request):
    return {
        "demo": "Kinglet Authorization",
        "endpoints": [
            "/public - No auth required",
            "/protected - Requires authentication",
            "/manual-auth - Requires authentication (via @require_authenticated decorator)",
            "/admin/action - Admin access with confirmation (via @require_admin_auth decorator)",
        ],
    }


@app.get("/public", public=True)
async def public_endpoint(request):
    """Public endpoint - no auth required"""
    return {"message": "This is public", "auth_required": False}


@app.get("/protected")
@require_auth
async def protected_endpoint(request):
    """Protected endpoint - requires authentication"""
    user = await kinglet.authz.get_user(request)
    claims = user.get("claims", {}) if user else {}
    return {
        "message": "You are authenticated",
        "user_id": user.get("id") if user else None,
        "email": claims.get("email"),
    }


# ---------------------------------------------------------------------------
# Custom security decorators — mirror the pattern from secure_admin_example.py.
# Always call kinglet.authz.get_user through the module so monkeypatching works.
# ---------------------------------------------------------------------------


@security_decorator
def require_authenticated(handler):
    """Require a valid authenticated user (JWT). Returns 401 if unauthenticated."""

    async def wrapped(request):
        user = await kinglet.authz.get_user(request)
        if not user:
            return Response({"error": "Authentication required"}, status=401)
        request.state = getattr(request, "state", type("State", (), {})())
        request.state.user = user
        return await handler(request)

    return wrapped


@security_decorator
def require_admin_auth(handler):
    """Require an authenticated user with role == 'admin'. Returns 401/403 otherwise."""

    async def wrapped(request):
        user = await kinglet.authz.get_user(request)
        if not user:
            return Response({"error": "Authentication required"}, status=401)
        claims = user.get("claims", {})
        if claims.get("role") != "admin":
            return Response({"error": "Admin access required"}, status=403)
        request.state = getattr(request, "state", type("State", (), {})())
        request.state.user = user
        return await handler(request)

    return wrapped


# Manual auth check example — now uses a proper @security_decorator wrapper
@app.get("/manual-auth")
@require_authenticated  # ← CORRECT: route decorator OUTERMOST, security decorator below
async def manual_auth_check(request):
    """Example of authentication enforced via a custom @security_decorator."""
    user = request.state.user
    return {
        "message": "Manual auth successful",
        "user": user.get("id"),
        "method": "security_decorator",
    }


# Admin example with proper security — now uses a proper @security_decorator wrapper
@app.post("/admin/action")
@require_admin_auth  # ← CORRECT: route decorator OUTERMOST, security decorator below
async def admin_action(request):
    """Admin action with confirmation requirement."""
    user = request.state.user
    claims = user.get("claims", {})
    email = claims.get("email", "")

    # Require confirmation header for dangerous actions
    confirm = request.header("x-confirm-action")
    if confirm != "true":
        return Response(
            {
                "error": "Confirmation required",
                "hint": "Add header: X-Confirm-Action: true",
            },
            status=400,
        )

    return {
        "success": True,
        "admin": email,
        "message": "Admin action completed",
    }


# Mock JWT for testing
@app.post("/mock-login", public=True)
async def mock_login(request):
    """Create a mock JWT for testing (demo only)"""
    body = await request.json() or {}
    email = body.get("email", "test@example.com")

    # In production, validate credentials and create real JWT
    mock_jwt = f"mock.jwt.{email.replace('@', '_at_')}"

    return {
        "token": mock_jwt,
        "type": "Bearer",
        "email": email,
        "note": "This is a mock token for demo purposes",
    }


# Cloudflare Workers entry point
async def on_fetch(request, env):
    return await app(request, env)
