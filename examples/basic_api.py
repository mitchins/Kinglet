#!/usr/bin/env python3
"""
Basic Kinglet API Example
Shows core features: routing, typed parameters, authentication, testing, OpenAPI docs
"""

import os
import sys

# Add parent directory to path so we can import kinglet
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from kinglet import Kinglet, Response, SchemaGenerator, TestClient

# Create app with root path for /api endpoints
app = Kinglet(root_path="/api", debug=True)


@app.get("/")
async def health_check(request):
    """Health check endpoint"""
    import sys

    return {
        "status": "healthy",
        "project": "Kinglet-BasicAPI-Example",
        "description": "Basic Kinglet API demonstration",
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "runtime": "Pyodide" if hasattr(sys, "_emscripten_info") else "CPython",
        "request_id": request.request_id,
    }


@app.get("/search")
async def search_users(request):
    """Example with typed query parameters"""
    page = request.query_int("page", 1)
    limit = request.query_int("limit", 10)
    active_only = request.query_bool("active", False)
    tags = request.query_all("tags")

    return {
        "users": [f"user_{i}" for i in range((page - 1) * limit, page * limit)],
        "filters": {"active": active_only, "tags": tags},
        "pagination": {"page": page, "limit": limit},
    }


@app.get("/users/{user_id}")
async def get_user(request):
    """Example with typed path parameters and authentication"""
    # Typed path parameter with validation
    user_id = request.path_param_int("user_id")

    # Check authentication
    token = request.bearer_token()
    if not token:
        return Response.error(
            "Authentication required", status=401, request_id=request.request_id
        )

    return {"user_id": user_id, "authenticated": True, "token": token}


@app.post("/auth/register")
async def register(request):
    """Example with JSON body and validation"""
    data = await request.json()

    if not data.get("email"):
        return Response.error(
            "Email required",
            status=400,
            detail="Please provide a valid email",
            request_id=request.request_id,
        )

    return Response.json(
        {"user_id": "123", "email": data["email"], "created": True},
        request_id=request.request_id,
    )


# OpenAPI Documentation Endpoints
@app.get("/openapi.json")
async def openapi_spec(request):
    """
    OpenAPI 3.0 Specification

    Returns the complete OpenAPI spec for this API.
    Can be used with Swagger UI, ReDoc, or code generators.
    """
    generator = SchemaGenerator(
        app,
        title="Basic Kinglet API",
        version="1.0.0",
        description="Demonstrates core Kinglet features with auto-generated documentation",
    )
    return Response(generator.generate_spec())


@app.get("/docs")
async def swagger_ui(request):
    """
    Interactive API Documentation (Swagger UI)

    Browse and test the API endpoints interactively.
    """
    generator = SchemaGenerator(app, title="Basic Kinglet API", version="1.0.0")
    return Response(
        generator.serve_swagger_ui(spec_url="/api/openapi.json"),
        content_type="text/html",
    )


@app.get("/redoc")
async def redoc_ui(request):
    """
    API Documentation (ReDoc)

    Alternative documentation interface with a clean design.
    """
    generator = SchemaGenerator(app, title="Basic Kinglet API", version="1.0.0")
    return Response(
        generator.serve_redoc(spec_url="/api/openapi.json"), content_type="text/html"
    )


# Cloudflare Workers entry point
async def on_fetch(request, env):
    return await app(request, env)


# Development testing
if __name__ == "__main__":
    print("🧪 Testing Kinglet API Example")
    print("=" * 40)

    client = TestClient(app)

    # Test health check
    status, headers, body = client.request("GET", "/api/")
    print(f"Health: {status} - {body}")

    # Test search with typed parameters
    status, headers, body = client.request(
        "GET", "/api/search?page=2&limit=5&active=true&tags=python"
    )
    print(f"Search: {status} - {body}")

    # Test authenticated user lookup
    status, headers, body = client.request(
        "GET", "/api/users/42", headers={"Authorization": "Bearer user-token-123"}
    )
    print(f"User: {status} - {body}")

    # Test registration
    status, headers, body = client.request(
        "POST", "/api/auth/register", json={"email": "test@example.com"}
    )
    print(f"Register: {status} - {body}")

    # Test validation error
    status, headers, body = client.request("POST", "/api/auth/register", json={})
    print(f"Error: {status} - {body}")

    # Test OpenAPI spec generation
    status, headers, body = client.request("GET", "/api/openapi.json")
    print(f"\nOpenAPI Spec: {status}")
    if status == 200:
        import json

        spec = json.loads(body)
        print(f"  - OpenAPI version: {spec.get('openapi')}")
        print(f"  - Title: {spec.get('info', {}).get('title')}")
        print(f"  - Endpoints: {len(spec.get('paths', {}))}")
        print(
            f"  - Paths: {', '.join(list(spec.get('paths', {}).keys())[:5])}{'...' if len(spec.get('paths', {})) > 5 else ''}"
        )

    # Test Swagger UI
    status, headers, body = client.request("GET", "/api/docs")
    print(f"Swagger UI: {status} - {len(body)} chars")

    print("\n✅ All examples completed!")
    print("\n📚 API Documentation available at:")
    print("   - /api/docs (Swagger UI)")
    print("   - /api/redoc (ReDoc)")
    print("   - /api/openapi.json (OpenAPI spec)")
