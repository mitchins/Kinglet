#!/usr/bin/env python3
"""
Basic Kinglet API Example
Shows core features: routing, typed parameters, authentication, testing
"""

from kinglet import Kinglet, Response, TestClient

# Create app with root path for /api endpoints
app = Kinglet(root_path="/api", debug=True)

@app.get("/")
async def health_check(request):
    """Health check endpoint"""
    return {
        "status": "healthy",
        "request_id": request.request_id
    }

@app.get("/search")
async def search_users(request):
    """Example with typed query parameters"""
    page = request.query_int("page", 1)
    limit = request.query_int("limit", 10)
    active_only = request.query_bool("active", False)
    tags = request.query_all("tags")
    
    return {
        "users": [f"user_{i}" for i in range((page-1)*limit, page*limit)],
        "filters": {"active": active_only, "tags": tags},
        "pagination": {"page": page, "limit": limit}
    }

@app.get("/users/{user_id}")
async def get_user(request):
    """Example with typed path parameters and authentication"""
    # Typed path parameter with validation
    user_id = request.path_param_int("user_id")
    
    # Check authentication
    token = request.bearer_token()
    if not token:
        return Response.error("Authentication required", status=401,
                            request_id=request.request_id)
    
    return {"user_id": user_id, "authenticated": True, "token": token}

@app.post("/auth/register")
async def register(request):
    """Example with JSON body and validation"""
    data = await request.json()
    
    if not data.get("email"):
        return Response.error("Email required", status=400,
                            detail="Please provide a valid email",
                            request_id=request.request_id)
    
    return Response.json({
        "user_id": "123",
        "email": data["email"],
        "created": True
    }, request_id=request.request_id)

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
    status, headers, body = client.request("GET", "/api/search?page=2&limit=5&active=true&tags=python")
    print(f"Search: {status} - {body}")
    
    # Test authenticated user lookup
    status, headers, body = client.request("GET", "/api/users/42", headers={
        "Authorization": "Bearer user-token-123"
    })
    print(f"User: {status} - {body}")
    
    # Test registration
    status, headers, body = client.request("POST", "/api/auth/register", json={
        "email": "test@example.com"
    })
    print(f"Register: {status} - {body}")
    
    # Test validation error
    status, headers, body = client.request("POST", "/api/auth/register", json={})
    print(f"Error: {status} - {body}")
    
    print("\n✅ All examples completed!")