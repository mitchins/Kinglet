"""
Kinglet Authorization Demo - Simple authentication patterns
"""

from kinglet import Kinglet, Response
from kinglet.authz import get_user, require_auth

app = Kinglet()


@app.get("/", public=True)
async def home(request):
    return {
        "demo": "Kinglet Authorization",
        "endpoints": [
            "/public - No auth required",
            "/protected - Requires authentication",
            "/admin - Admin access with confirmation",
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
    user = await get_user(request)
    claims = user.get("claims", {}) if user else {}
    return {
        "message": "You are authenticated",
        "user_id": user.get("id") if user else None,
        "email": claims.get("email"),
    }


# Manual auth check example
@app.get(
    "/manual-auth", public=True
)  # TODO: consider a security decorator — handler does inline auth check
async def manual_auth_check(request):
    """Example of manual authentication check"""
    user = await get_user(request)

    if not user:
        return Response({"error": "Authentication required"}, status=401)

    return {
        "message": "Manual auth successful",
        "user": user.get("id"),
        "method": "manual_check",
    }


# Admin example with proper security
@app.post(
    "/admin/action", public=True
)  # TODO: consider a security decorator — handler does inline role/admin check
async def admin_action(request):
    """Admin action with confirmation requirement"""
    user = await get_user(request)
    claims = user.get("claims", {}) if user else {}
    email = claims.get("email", "")
    role = claims.get("role")

    if not user or role != "admin":
        return Response({"error": "Admin access required"}, status=403)

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
