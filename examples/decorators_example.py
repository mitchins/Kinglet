#!/usr/bin/env python3
"""
Kinglet Decorators Example
Demonstrates exception wrapping, dev-only endpoints, and geo-restrictions
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kinglet import Kinglet, TestClient, geo_restrict, require_dev, wrap_exceptions

# Create app with global exception wrapping enabled (default)
app = Kinglet(debug=True, auto_wrap_exceptions=True)

# === GLOBAL EXCEPTION WRAPPING ===
# All endpoints automatically get exception wrapping when auto_wrap_exceptions=True


@app.get("/api/games")
async def get_games(request):
    """Example endpoint that might throw errors - automatically wrapped"""
    # Simulate database access that might fail
    if request.query("simulate_error") == "true":
        raise ConnectionError("Database connection failed")

    return {
        "games": [
            {"id": 1, "title": "Epic Adventure", "price": 9.99},
            {"id": 2, "title": "Puzzle Master", "price": 4.99},
        ],
        "auto_wrapped": True,
    }


# === MANUAL EXCEPTION WRAPPING ===
# For apps with auto_wrap_exceptions=False, you can manually wrap specific endpoints

app_manual = Kinglet(auto_wrap_exceptions=False)


@app_manual.get("/api/manual")
@wrap_exceptions(step="manual_endpoint", expose_details=True)
async def manual_wrapped(request):
    """Manually wrapped endpoint with specific step identifier"""
    if request.query("break") == "true":
        raise ValueError("Something broke in the manual endpoint")

    return {"message": "Manual wrapping works", "step": "manual_endpoint"}


# === DEV-ONLY ENDPOINTS ===


@app.get("/admin/debug")
@require_dev()
async def debug_info(request):
    """Debug endpoint only available in development/test environments"""
    return {
        "debug": True,
        "environment": request.env.ENVIRONMENT,
        "request_id": request.request_id,
        "headers": dict(request._headers),
        "note": "This endpoint only works in development mode",
    }


@app.get("/admin/clear-cache")
@require_dev()
async def clear_cache(request):
    """Another dev-only endpoint for cache management"""
    # In a real app, this would clear your cache
    return {
        "message": "Cache cleared",
        "timestamp": "2025-08-09T12:00:00Z",
        "note": "This would be dangerous in production!",
    }


# === GEO-RESTRICTED ENDPOINTS ===


@app.get("/api/games-us")
@geo_restrict(allowed=["US"])
async def us_only_games(request):
    """Games only available in the US"""
    return {
        "games": ["US Exclusive Game 1", "US Exclusive Game 2"],
        "region": "US",
        "note": "These games are only available in the United States",
    }


@app.get("/api/games-global")
@geo_restrict(blocked=["CN", "RU"])
async def global_games_with_restrictions(request):
    """Games available globally except in specific countries"""
    return {
        "games": ["Global Game 1", "Global Game 2"],
        "restrictions": "Not available in CN, RU",
        "note": "Available worldwide except blocked countries",
    }


# === COMBINING DECORATORS ===


@app.get("/admin/restricted-debug")
@require_dev()
@geo_restrict(allowed=["US", "CA"])
@wrap_exceptions(step="admin_debug", expose_details=True)
async def super_restricted_debug(request):
    """
    Highly restricted endpoint:
    - Only works in dev/test environments
    - Only available in US/CA
    - Has custom exception wrapping with step identifier
    """
    country = request.header("cf-ipcountry", "XX")

    # Simulate potential error
    if request.query("error") == "true":
        raise RuntimeError("Simulated error in restricted endpoint")

    return {
        "message": "Super restricted debug endpoint",
        "environment": request.env.ENVIRONMENT,
        "country": country,
        "restrictions": ["dev-only", "US/CA only"],
        "step": "admin_debug",
    }


# === DEMO FUNCTION ===


def demo():
    """Demonstrate the decorator features"""
    print("🎭 Kinglet Decorators Demo\n")

    # Test client for development environment
    dev_client = TestClient(app, env={"ENVIRONMENT": "development"})

    # Test client for production environment
    prod_client = TestClient(app, env={"ENVIRONMENT": "production"})

    print("1. Global Exception Wrapping:")
    status, headers, body = dev_client.request("GET", "/api/games?simulate_error=true")
    print(f"   Error response: {status} - {body[:100]}...")

    print("\n2. Dev-Only Endpoints:")
    status, headers, body = dev_client.request("GET", "/admin/debug")
    print(f"   Dev environment: {status} - Access granted")

    status, headers, body = prod_client.request("GET", "/admin/debug")
    print(f"   Prod environment: {status} - Access denied")

    print("\n3. Geo-Restricted Endpoints:")
    status, headers, body = dev_client.request(
        "GET", "/api/games-us", headers={"cf-ipcountry": "US"}
    )
    print(f"   US request: {status} - Access granted")

    status, headers, body = dev_client.request(
        "GET", "/api/games-us", headers={"cf-ipcountry": "DE"}
    )
    print(f"   DE request: {status} - Access denied")

    print("\n4. Combined Restrictions:")
    status, headers, body = dev_client.request(
        "GET", "/admin/restricted-debug", headers={"cf-ipcountry": "US"}
    )
    print(f"   Dev + US: {status} - Access granted")

    status, headers, body = prod_client.request(
        "GET", "/admin/restricted-debug", headers={"cf-ipcountry": "US"}
    )
    print(f"   Prod + US: {status} - Blocked by dev restriction")

    status, headers, body = dev_client.request(
        "GET", "/admin/restricted-debug", headers={"cf-ipcountry": "CN"}
    )
    print(f"   Dev + CN: {status} - Blocked by geo restriction")

    print("\n5. Manual Exception Wrapping:")
    manual_client = TestClient(app_manual)
    status, headers, body = manual_client.request("GET", "/api/manual?break=true")
    print(f"   Manual wrap: {status} - {body[:80]}...")

    print("\n✅ Demo complete! All decorator features working.")


if __name__ == "__main__":
    demo()
