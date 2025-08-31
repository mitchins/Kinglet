"""
Secure Admin Endpoint Example for Kinglet

Demonstrates proper security patterns for admin endpoints including:
- Correct decorator ordering
- Response object usage for status codes
- Case-insensitive header handling
- Confirmation headers for dangerous operations
- Multi-layer security checks

This example reflects lessons learned from real-world security issues.
"""

from kinglet import Kinglet, Response, Router
from kinglet.authz import get_user

app = Kinglet(debug=False)  # Production security settings
admin_router = Router()

# ============================================================================
# SECURE ADMIN DECORATOR WITH MULTIPLE LAYERS
# ============================================================================


def require_admin(handler):
    """
    Multi-layer admin security decorator

    Security layers:
    1. Authentication required (valid JWT)
    2. Admin role verification (no development bypasses)
    3. User context setup for handler access
    """

    async def wrapped(request):
        # Layer 1: Require authentication
        user = await get_user(request)
        if not user:
            return Response(
                {
                    "error": "Admin access requires authentication",
                    "hint": "Include valid JWT token in Authorization header",
                },
                status=401,
            )

        # Layer 2: Verify admin role (NO development bypasses!)
        claims = user.get("claims", {})
        is_admin = claims.get("role") == "admin" or claims.get("is_publisher") is True

        if not is_admin:
            return Response(
                {
                    "error": "Admin access denied - insufficient privileges",
                    "required_role": "admin",
                },
                status=403,
            )

        # Layer 3: Set user context for handler
        request.state = getattr(request, "state", type("State", (), {})())
        request.state.user = user

        return await handler(request)

    return wrapped


# ============================================================================
# UTILITY FUNCTIONS FOR ROBUST SECURITY
# ============================================================================


def get_header_case_insensitive(request, header_name):
    """
    Get header value checking multiple case variations

    HTTP headers are case-insensitive but implementations vary.
    This ensures we catch headers regardless of client casing.
    """
    variations = [
        header_name.lower(),  # x-confirm-action
        header_name.upper(),  # X-CONFIRM-ACTION
        header_name.title(),  # X-Confirm-Action
        "-".join(
            word.capitalize() for word in header_name.split("-")
        ),  # X-Confirm-Action (alt)
    ]

    for variation in variations:
        value = request.header(variation)
        if value:
            return value
    return None


# ============================================================================
# SECURE ADMIN ENDPOINTS - CORRECT DECORATOR ORDER
# ============================================================================


@admin_router.get("/tables")
@require_admin  # ← CORRECT: Router decorator FIRST, then security decorator
async def get_tables(request):
    """
    Get list of database tables

    Security: Admin role required
    """
    try:
        # Mock database table listing
        tables = ["users", "games", "transactions", "sessions", "game_media"]

        return {
            "tables": tables,
            "total": len(tables),
            "admin_user": request.state.user["id"],
        }
    except Exception as e:
        return Response({"error": f"Failed to fetch tables: {str(e)}"}, status=500)


@admin_router.get("/stats")
@require_admin  # ← CORRECT: Router decorator FIRST, then security decorator
async def get_database_stats(request):
    """
    Get database statistics

    Security: Admin role required
    """
    try:
        # Mock database statistics
        stats = {
            "users": 1250,
            "games": 52,
            "transactions": 891,
            "total_revenue": 15750.50,
        }

        return {
            "table_counts": stats,
            "last_updated": "2024-01-15T10:30:00Z",
            "admin_user": request.state.user["id"],
        }
    except Exception as e:
        return Response({"error": f"Failed to get stats: {str(e)}"}, status=500)


@admin_router.post("/cache/nuke")
@require_admin  # ← CORRECT: Router decorator FIRST, then security decorator
async def nuke_cache(request):
    """
    Nuclear cache clear - removes all cached content

    Security: Admin role required + confirmation header
    Dangerous operation requires explicit confirmation
    """

    # Check confirmation header (case-insensitive)
    confirm_header = get_header_case_insensitive(request, "x-confirm-nuke")

    if confirm_header != "true":
        return Response(
            {
                "error": "Cache nuke confirmation required. Add X-Confirm-Nuke: true header",
                "example": 'curl -H "X-Confirm-Nuke: true" -X POST /api/admin/cache/nuke',
            },
            status=400,
        )

    try:
        # Mock cache clearing operation
        cache_prefixes = ["homepage_", "games_list_", "game_detail_"]
        nuked_count = 127  # Mock cleared objects count

        return Response(
            {
                "success": True,
                "message": f"Cache nuked: {nuked_count} objects deleted",
                "nuked_count": nuked_count,
                "cache_prefixes_cleared": cache_prefixes,
                "admin_user": request.state.user["id"],
                "timestamp": "2024-01-15T10:35:22Z",
            }
        )

    except Exception as e:
        return Response(
            {"error": f"Cache nuke failed: {str(e)}", "type": type(e).__name__},
            status=500,
        )


@admin_router.delete("/tables/{table_name}/row/{row_id}")
@require_admin  # ← CORRECT: Router decorator FIRST, then security decorator
async def delete_row(request):
    """
    Delete a database row

    Security: Admin role required + confirmation header
    """
    table_name = request.path_param("table_name")
    row_id = request.path_param("row_id")

    # Validate table name (prevent SQL injection)
    allowed_tables = ["users", "games", "transactions", "sessions"]
    if table_name not in allowed_tables:
        return Response(
            {
                "error": "Table not allowed for deletion",
                "allowed_tables": allowed_tables,
            },
            status=400,
        )

    # Check confirmation header (case-insensitive)
    confirm_header = get_header_case_insensitive(request, "x-confirm-delete")

    if confirm_header != "true":
        return Response(
            {
                "error": "Delete confirmation required. Add X-Confirm-Delete: true header",
                "warning": f"This will permanently delete row {row_id} from {table_name}",
            },
            status=400,
        )

    try:
        # Mock deletion operation
        return Response(
            {
                "success": True,
                "deleted_table": table_name,
                "deleted_id": row_id,
                "admin_user": request.state.user["id"],
                "timestamp": "2024-01-15T10:40:15Z",
            }
        )

    except Exception as e:
        return Response({"error": f"Failed to delete row: {str(e)}"}, status=500)


@admin_router.get("/cache/info")
@require_admin  # ← CORRECT: Router decorator FIRST, then security decorator
async def get_cache_info(request):
    """
    Get information about cached objects

    Security: Admin role required (read-only, no confirmation needed)
    """
    try:
        # Mock cache information
        cache_info = {
            "homepage_": {"count": 3, "size_mb": 1.2},
            "games_list_": {"count": 15, "size_mb": 0.8},
            "game_detail_": {"count": 52, "size_mb": 4.1},
        }

        total_objects = sum(info["count"] for info in cache_info.values())
        total_size = sum(info["size_mb"] for info in cache_info.values())

        return {
            "cache_info": cache_info,
            "total_cached_objects": total_objects,
            "total_size_mb": round(total_size, 2),
            "admin_user": request.state.user["id"],
        }

    except Exception as e:
        return Response({"error": f"Failed to get cache info: {str(e)}"}, status=500)


# ============================================================================
# PUBLIC ENDPOINTS FOR COMPARISON
# ============================================================================


@app.get("/health")
async def health_check(request):
    """Public health check endpoint - no authentication required"""
    return {
        "status": "healthy",
        "project": "Kinglet-SecureAdminExample",
        "description": "Secure admin endpoint demonstration",
        "timestamp": "2024-01-15T10:45:00Z",
        "version": "1.0.0",
    }


@app.get("/api/games")
async def list_games(request):
    """Public games list - no authentication required"""
    return {
        "games": [
            {"id": 1, "title": "Space Adventure", "public": True},
            {"id": 2, "title": "Puzzle Master", "public": True},
        ],
        "total": 2,
    }


# ============================================================================
# APPLICATION SETUP
# ============================================================================

# Include admin router with prefix
app.include_router("/api/admin", admin_router)


# ============================================================================
# TESTING THE SECURE ADMIN ENDPOINTS
# ============================================================================

if __name__ == "__main__":
    from kinglet import TestClient

    client = TestClient(app)

    print("🛡️  Testing Secure Admin Endpoints")
    print("=" * 50)

    # Test 1: Public endpoint (should work)
    print("\n✅ Test 1: Public endpoint")
    status, _, body = client.request("GET", "/health")
    print(f"Status: {status}, Response: {body}")

    # Test 2: Admin endpoint without auth (should fail)
    print("\n❌ Test 2: Admin endpoint without auth")
    status, _, body = client.request("GET", "/api/admin/tables")
    print(f"Status: {status}, Response: {body}")

    # Test 3: Admin endpoint with mock auth (should work)
    print("\n✅ Test 3: Admin endpoint with auth")
    # Note: In real usage, you'd get this token from login endpoint
    mock_admin_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.mock.admin.token"

    # Mock get_user for testing
    from unittest.mock import AsyncMock

    import kinglet.authz

    original_get_user = kinglet.authz.get_user
    kinglet.authz.get_user = AsyncMock(
        return_value={
            "id": "admin-123",
            "claims": {"role": "admin", "email": "admin@test.com"},
        }
    )

    try:
        status, _, body = client.request(
            "GET",
            "/api/admin/tables",
            headers={"Authorization": f"Bearer {mock_admin_token}"},
        )
        print(f"Status: {status}, Response: {body}")

        # Test 4: Dangerous operation without confirmation (should fail)
        print("\n❌ Test 4: Dangerous operation without confirmation")
        status, _, body = client.request(
            "POST",
            "/api/admin/cache/nuke",
            headers={"Authorization": f"Bearer {mock_admin_token}"},
        )
        print(f"Status: {status}, Response: {body}")

        # Test 5: Dangerous operation with confirmation (should work)
        print("\n✅ Test 5: Dangerous operation with confirmation")
        status, _, body = client.request(
            "POST",
            "/api/admin/cache/nuke",
            headers={
                "Authorization": f"Bearer {mock_admin_token}",
                "X-Confirm-Nuke": "true",
            },
        )
        print(f"Status: {status}, Response: {body}")

    finally:
        # Restore original get_user
        kinglet.authz.get_user = original_get_user

    print("\n🎯 All security tests completed!")
    print("\nKey Security Features Demonstrated:")
    print("✓ Correct decorator ordering (router first, auth second)")
    print("✓ Response objects for proper HTTP status codes")
    print("✓ Case-insensitive header handling")
    print("✓ Confirmation headers for dangerous operations")
    print("✓ Multi-layer security checks")
    print("✓ No development environment bypasses")


"""
Environment Configuration (wrangler.toml):

[vars]
JWT_SECRET = "your-production-jwt-secret"

[env.development.vars]
JWT_SECRET = "development-jwt-secret"

Security Notes:
1. Never use different security logic between dev and production
2. Always test with proper admin accounts, not security bypasses
3. Router decorators must come BEFORE security decorators
4. Use Response objects for non-200 status codes
5. Check headers case-insensitively for robustness
6. Require confirmation headers for dangerous operations
"""
