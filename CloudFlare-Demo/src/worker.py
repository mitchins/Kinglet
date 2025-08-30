"""
Kinglet 1.4.0 Demo - Testing all new features
"""

from kinglet import Kinglet, Response, Router
from kinglet.authz import (
    allow_public_or_owner,
    get_user,
    require_auth,
    require_owner,
)
from kinglet.totp import generate_totp_secret, verify_totp_code

app = Kinglet()


# ============ Basic Routes ============
@app.get("/")
async def hello(request):
    return {
        "message": "Kinglet 1.4.0 Demo",
        "version": "1.4.0",
        "features": [
            "Authorization (FGA)",
            "TOTP Support",
            "D1 Helpers",
            "R2 Helpers",
            "Security Best Practices",
        ],
    }


@app.get("/health")
async def health_check(request):
    return {"status": "healthy", "version": "1.4.0"}


# ============ Authorization Demo ============
auth_router = Router()


@auth_router.get("/public")
async def public_endpoint(request):
    """Public endpoint - no auth required"""
    return {"message": "This is public", "auth_required": False}


@auth_router.get("/protected")
@require_auth
async def protected_endpoint(request):
    """Protected endpoint - requires authentication"""
    user = await get_user(request)
    return {
        "message": "You are authenticated",
        "user_id": user.get("sub") if user else None,
    }


@auth_router.get("/resource/{resource_id}")
@allow_public_or_owner("resource_id")
async def resource_endpoint(request):
    """Resource that's public or owner-only"""
    resource_id = request.path_params.get("resource_id")
    user = await get_user(request)

    # Mock resource lookup
    resource = {
        "id": resource_id,
        "public": resource_id.startswith("public-"),
        "owner_id": "user-123" if not resource_id.startswith("public-") else None,
    }

    return {
        "resource": resource,
        "accessed_by": user.get("sub") if user else "anonymous",
    }


@auth_router.get("/owner-only/{resource_id}")
@require_owner("resource_id")
async def owner_only_endpoint(request):
    """Owner-only resource"""
    resource_id = request.path_params.get("resource_id")
    user = await get_user(request)
    return {
        "message": "Owner access granted",
        "resource_id": resource_id,
        "owner": user.get("sub"),
    }


app.include_router("/auth", auth_router)

# ============ TOTP Demo ============
totp_router = Router()


@totp_router.post("/setup")
@require_auth
async def setup_totp(request):
    """Generate TOTP secret for user"""
    user = await get_user(request)
    if not user:
        return Response({"error": "Authentication required"}, status=401)

    secret = generate_totp_secret()
    # In production, save this secret to database
    return {
        "secret": secret,
        "qr_data": f"otpauth://totp/KingletDemo:{user.get('email', 'user')}?secret={secret}&issuer=KingletDemo",
    }


@totp_router.post("/verify")
@require_auth
async def verify_totp_endpoint(request):
    """Verify TOTP code"""
    user = await get_user(request)
    if not user:
        return Response({"error": "Authentication required"}, status=401)

    body = await request.json() or {}
    code = body.get("code")
    secret = body.get("secret")  # In production, fetch from database

    if not code or not secret:
        return Response({"error": "Code and secret required"}, status=400)

    is_valid = verify_totp_code(secret, code)

    return {
        "valid": is_valid,
        "message": "TOTP verified successfully" if is_valid else "Invalid code",
    }


app.include_router("/totp", totp_router)

# ============ D1 Database Demo ============
db_router = Router()


@db_router.get("/users")
async def list_users(request):
    """List users from D1 database"""
    try:
        # Mock D1 query
        if hasattr(request.env, "DB"):
            # In real environment, this would query D1
            results = await request.env.DB.prepare("SELECT * FROM users LIMIT 10").all()

            from kinglet import d1_unwrap_results

            users = d1_unwrap_results(results)
            return {"users": users}
    except:
        pass

    # Mock data for demo
    return {
        "users": [
            {"id": 1, "name": "Alice", "email": "alice@example.com"},
            {"id": 2, "name": "Bob", "email": "bob@example.com"},
        ],
        "note": "Mock data - D1 not configured",
    }


@db_router.post("/users")
async def create_user(request):
    """Create user in D1 database"""
    body = await request.json() or {}

    if not body.get("name") or not body.get("email"):
        return Response({"error": "Name and email required"}, status=400)

    try:
        if hasattr(request.env, "DB"):
            # In real environment, this would insert into D1
            result = (
                await request.env.DB.prepare(
                    "INSERT INTO users (name, email) VALUES (?, ?)"
                )
                .bind(body["name"], body["email"])
                .run()
            )

            from kinglet import d1_unwrap

            meta = d1_unwrap(result.meta)
            return {"created": True, "id": meta.get("last_row_id")}
    except:
        pass

    # Mock response for demo
    return {"created": True, "id": 3, "note": "Mock response - D1 not configured"}


app.include_router("/db", db_router)

# ============ R2 Storage Demo ============
r2_router = Router()


@r2_router.get("/files")
async def list_files(request):
    """List files in R2 bucket"""
    try:
        if hasattr(request.env, "BUCKET"):
            # In real environment, this would list R2 objects
            objects = await request.env.BUCKET.list()
            from kinglet import r2_list

            files = r2_list(objects)
            return {"files": files}
    except:
        pass

    # Mock data for demo
    return {
        "files": [
            {"key": "image1.jpg", "size": 1024000},
            {"key": "document.pdf", "size": 512000},
        ],
        "note": "Mock data - R2 not configured",
    }


@r2_router.get("/file/{key:path}")
async def get_file(request):
    """Get file from R2"""
    key = request.path_params.get("key")

    try:
        if hasattr(request.env, "BUCKET"):
            obj = await request.env.BUCKET.get(key)
            if obj:
                from kinglet import r2_get_content_info

                info = r2_get_content_info(obj)

                # For binary files, return stream directly
                if info["type"] and "image" in info["type"]:
                    from workers import Response as WorkersResponse

                    return WorkersResponse(
                        obj.body,
                        headers={
                            "Content-Type": info["type"],
                            "Content-Length": str(info["size"]),
                        },
                    )

                # For text files, return content
                content = await obj.text()
                return Response(content, headers={"Content-Type": info["type"]})
    except:
        pass

    return Response({"error": f"File '{key}' not found"}, status=404)


app.include_router("/r2", r2_router)

# ============ Security Best Practices Demo ============
admin_router = Router()


def require_admin(handler):
    """Admin authentication decorator"""

    async def wrapped(request):
        user = await get_user(request)
        if not user or not user.get("is_admin"):
            return Response({"error": "Admin access required"}, status=403)
        return await handler(request)

    return wrapped


@admin_router.get("/dashboard")
@require_admin
async def admin_dashboard(request):
    """Admin dashboard - properly secured"""
    return {"message": "Admin Dashboard", "stats": {"users": 100, "requests": 5000}}


@admin_router.post("/dangerous-action")
@require_admin
async def dangerous_action(request):
    """Dangerous action requiring confirmation"""
    # Check for confirmation header
    confirm = request.header("x-confirm-action")
    if confirm != "true":
        return Response(
            {
                "error": "Confirmation required",
                "hint": "Add header: X-Confirm-Action: true",
            },
            status=400,
        )

    return {"success": True, "message": "Dangerous action completed"}


app.include_router("/admin", admin_router)


# ============ Error Handling ============
@app.exception_handler(404)
async def not_found(request, error):
    return Response({"error": "Not found", "path": request.url.pathname}, status=404)


@app.exception_handler(500)
async def server_error(request, error):
    return Response(
        {
            "error": "Internal server error",
            "message": str(error)
            if request.env.ENVIRONMENT == "development"
            else "Something went wrong",
        },
        status=500,
    )


# Cloudflare Workers entry point
async def on_fetch(request, env):
    return await app(request, env)
