<div align="center">
  <img src="logo.png" alt="Kinglet Logo" width="200" height="200">
  <h1>Kinglet</h1>
  <p><strong>Lightning-fast Python web framework for Cloudflare Workers</strong></p>
</div>

## Quick Start

Available on PyPi either: run `pip install kinglet` or add to pyproject.toml `dependencies = ["kinglet"]`

**Manual Installation:** Copy the entire `kinglet/` folder (modular structure) to your worker project. No longer a single file - the framework is now modularized for better maintainability.

## What's New

### Version 1.4.0
1. **Fine-Grained Authorization (FGA)** - Decorator-based auth with JWT validation
2. **TOTP/2FA Support** - Session elevation with RFC 6238 TOTP
3. **OTP Provider Pattern** - Pluggable OTP providers for prod/dev environments
4. **Claim-based Access Control** - Business-level claims (publisher, host, etc.)
5. **Admin Override Capabilities** - Environment-based admin escape hatches
6. **Modular Architecture** - Clean separation of concerns across focused modules

### Version 1.3.0 
1. **D1 Database Helpers** - `d1_unwrap()`, `d1_unwrap_results()` 
2. **R2 Storage Helpers** - `r2_put()`, `r2_get_content_info()`
3. **Auto Exception Wrapping** - Automatic error handling
4. **Request Validation** - `@validate_json_body`, `@require_field`
5. **Media URL Generation** - CDN-aware URL helpers

```python
# Deploy to your ASGI environment
from kinglet import Kinglet

app = Kinglet(root_path="/api")

@app.post("/auth/login")
async def login(request):
    data = await request.json()
    return {"token": "jwt-token", "user": data["email"]}
```

## Why Kinglet?

| Feature | Kinglet | FastAPI | Flask |
|---------|---------|---------|-------|
| **Bundle Size** | 226KB (modular) | 7.8MB | 1.9MB |
| **Testing** | No server needed | Requires TestServer | Requires test client |
| **Workers Ready** | ✅ Built-in | ❌ Complex setup | ❌ Not compatible |

*In practical terms FastAPI's load time (especially on cold start) may exceed the worker allownace of cloudflare. Additionally Flask, Bottle and co have different expectations for the tuple that ASGI passes in.*

## Feature Overview

### Core Framework
1. **Routing** - Decorator-based routing with path/query parameters
2. **Request/Response** - Type-safe parameter extraction and response helpers
3. **Middleware** - Request lifecycle hooks and global middleware
4. **Error Handling** - Auto exception wrapping with request IDs
5. **Testing** - Direct testability without server spin-up

### Cloudflare Integration  
6. **D1 Database** - Helper functions for D1 proxy objects
7. **R2 Storage** - Simplified R2 operations with metadata
8. **KV Namespaces** - Type-safe KV operations
9. **Durable Objects** - DO communication helpers
10. **Cache API** - Cache-aside pattern with R2 backing

### Security & Auth
11. **JWT Validation** - HS256 JWT verification 
12. **TOTP/2FA** - RFC 6238 TOTP implementation
13. **Session Elevation** - Step-up authentication for sensitive ops
14. **Fine-Grained Auth** - Decorator-based authorization
15. **Geo Restrictions** - Country-based access control

### Developer Experience
16. **Type Safety** - Full type hints and validation
17. **Debug Mode** - Enhanced error messages in development
18. **Request Validation** - JSON body and field validators
19. **Media URLs** - CDN-aware URL generation
20. **OTP Providers** - Pluggable auth providers for dev/prod

## Core Features

### **Root Path Support**
Perfect for `/api` behind Cloudflare Pages:

```python
app = Kinglet(root_path="/api")

@app.get("/users")  # Handles /api/users
async def get_users(request):
    return {"users": []}
```

### **Typed Parameters** 
Built-in validation for query and path parameters:

```python
@app.get("/search")
async def search(request):
    limit = request.query_int("limit", 10)        # Returns int or 400 error
    enabled = request.query_bool("enabled", False) # Returns True/False
    tags = request.query_all("tags")              # Returns list of values

@app.get("/users/{user_id}")
async def get_user(request):
    user_id = request.path_param_int("user_id")   # Returns int or 400 error
    uuid = request.path_param_uuid("uuid")        # Validates UUID format
```

### **Authentication Helpers**
Parse Bearer tokens and Basic auth automatically:

```python
@app.get("/protected")
async def protected_route(request):
    token = request.bearer_token()        # Extract JWT from Authorization header
    user, password = request.basic_auth() # Parse Basic authentication
    is_authed = request.is_authenticated() # True if any auth present
    
    if not token:
        return Response.error("Authentication required", 401)
    return {"user": "authenticated"}
```

### **Experience APIs & Caching**
R2-backed cache-aside pattern with dynamic path support:

```python
@app.get("/games/{slug}")
@cache_aside(cache_type="game_detail", ttl=3600)
async def game_detail(request):
    return {"game": await get_game(request.path_param("slug"))}
```

### **Exception Wrapping & Access Control**
Automatic error handling and endpoint restrictions:

```python
app = Kinglet(debug=True)  # Auto-wraps exceptions with request IDs

@app.get("/admin/debug")
@require_dev()  # 403 in production
@geo_restrict(allowed=["US", "CA"]) 
async def debug_endpoint(request):
    raise ValueError("Auto-wrapped with context")
```

### **Fine-Grained Authorization (v1.4.0)**
Decorator-based auth with JWT validation and admin override:

```python
from kinglet.authz import require_auth, require_owner, allow_public_or_owner

@app.get("/profile")
@require_auth  # User must be logged in
async def profile(req):
    return {"user": req.state.user["id"]}

@app.delete("/posts/{id}")
@require_owner(
    lambda req, id: d1_load_owner_public(req.env.DB, "posts", id),
    allow_admin_env="ADMIN_IDS"  # Admins can bypass ownership
)
async def delete_post(req, obj):
    # Only owner or admin can delete
    return {"deleted": True}

@app.get("/listings/{id}")
@allow_public_or_owner(load_listing, forbidden_as_404=True)
async def get_listing(req, obj):
    # Public listings visible to all, private only to owner
    return {"listing": obj}
```

Admin override via environment variable:
```toml
# wrangler.toml
[vars]
ADMIN_IDS = "admin-uuid-1,admin-uuid-2,support-uuid-3"
```

⚠️ **Critical Security Note**: Decorator order matters! Router decorators MUST come before security decorators:

```python
# ✅ CORRECT - Secure
@app.get("/admin/data")    # Router decorator FIRST  
@require_admin             # Auth decorator SECOND
async def admin_data(req): 
    return {"secret": "data"}

# ❌ WRONG - Security bypassed!
@require_admin             # Auth decorator first (bypassed!)
@app.get("/admin/data")    # Router decorator second
async def vulnerable(req):
    return {"exposed": "data"}
```

See [authz_example.py](examples/authz_example.py) for complete patterns and [Security Best Practices](docs/SECURITY_BEST_PRACTICES.md) for critical security guidance.

### **Zero-Dependency Testing**
Test without HTTP servers - runs in <1ms:

```python
def test_my_api():
    client = TestClient(app)
    
    status, headers, body = client.request("GET", "/search?limit=5&enabled=true")
    assert status == 200
    
    status, headers, body = client.request("GET", "/protected", headers={
        "Authorization": "Bearer jwt-token-123"
    })
    assert status == 200
```

## Learn More

- **[Quick Examples](examples/)** - Basic API and decorators examples
- **[Security Best Practices](docs/SECURITY_BEST_PRACTICES.md)** - Critical security patterns and pitfalls
- **[Testing Guide](docs/TESTING.md)** - Unit & integration testing  
- **[Cloudflare Setup](docs/CLOUDFLARE.md)** - Workers deployment
- **[API Reference](docs/API.md)** - Complete method docs

## Production Ready

- **Request ID tracing** for debugging
- **Typed parameter validation** (int, bool, UUID)
- **Built-in authentication helpers** (Bearer, Basic auth)
- **Automatic exception wrapping** with environment-aware details
- **Access control decorators** (dev-only, geo-restrictions)
- **R2 cache-aside pattern** for Experience APIs
- **Environment-aware media URLs** (dev vs production)
- **Request validation decorators** (JSON body, required fields)
- **Configurable CORS** for security
- **Error boundaries** with proper status codes
- **Debug mode** for development
- **Type hints** for better DX
- **Zero-dependency testing** with TestClient

## Contributing

Built for the Cloudflare Workers Python community. PRs welcome for:

- Performance optimizations
- Additional middleware patterns
- Better TypeScript integration
- More testing utilities

---

**Need help?** Check the [docs](docs/) or [open an issue](https://github.com/mitchins/Kinglet/issues).

---

## Full API Example

```python
from kinglet import Kinglet, Response, TestClient

# Create app with root path for /api endpoints
app = Kinglet(root_path="/api", debug=True)

@app.get("/")
async def health_check(request):
    return {"status": "healthy", "request_id": request.request_id}

@app.post("/auth/register") 
async def register(request):
    data = await request.json()
    
    if not data.get("email"):
        return Response.error("Email required", status=400, 
                            request_id=request.request_id)
    
    # Simulate user creation
    return Response.json({
        "user_id": "123",
        "email": data["email"], 
        "created": True
    }, request_id=request.request_id)

@app.get("/users/{user_id}")
async def get_user(request):
    # Typed path parameter with validation
    user_id = request.path_param_int("user_id")  # Returns int or 400 error
    
    # Check authentication
    token = request.bearer_token()
    if not token:
        return Response.error("Authentication required", status=401,
                            request_id=request.request_id)
    
    # Access environment (Cloudflare bindings) 
    db = request.env.DB
    user = await db.prepare("SELECT * FROM users WHERE id = ?").bind(user_id).first()
    
    if not user:
        return Response.error("User not found", status=404,
                            request_id=request.request_id) 
    
    return {"user": user.to_py(), "token": token}

@app.get("/search")
async def search_users(request):
    # Typed query parameters
    page = request.query_int("page", 1)
    limit = request.query_int("limit", 10) 
    active_only = request.query_bool("active", False)
    tags = request.query_all("tags")
    
    return {
        "users": [f"user_{i}" for i in range((page-1)*limit, page*limit)],
        "filters": {"active": active_only, "tags": tags},
        "pagination": {"page": page, "limit": limit}
    }


# Production: Cloudflare Workers entry point
async def on_fetch(request, env):
    return await app(request, env)

# Development: Test without server
if __name__ == "__main__":
    client = TestClient(app)
    
    # Test health check
    status, headers, body = client.request("GET", "/")
    print(f"Health: {status} - {body}")
    
    # Test registration  
    status, headers, body = client.request("POST", "/auth/register", json={
        "email": "test@example.com",
        "password": "secure123"
    })
    print(f"Register: {status} - {body}")
    
    # Test authenticated user lookup
    status, headers, body = client.request("GET", "/users/42", headers={
        "Authorization": "Bearer user-token-123"
    })
    print(f"User: {status} - {body}")
    
    # Test typed query parameters
    status, headers, body = client.request("GET", "/search?page=2&limit=5&active=true&tags=python")
    print(f"Search: {status} - {body}")
    
    # Test error handling
    status, headers, body = client.request("POST", "/auth/register", json={})
    print(f"Error: {status} - {body}")
```

**Output:**
```
Health: 200 - {"status": "healthy", "request_id": "a1b2c3d4"}
Register: 200 - {"user_id": "123", "email": "test@example.com", "created": true, "request_id": "e5f6g7h8"}
User: 200 - {"user": {"id": 42, "email": "test@example.com"}, "token": "user-token-123"}
Search: 200 - {"users": ["user_5", "user_6", "user_7", "user_8", "user_9"], "filters": {"active": true, "tags": ["python"]}, "pagination": {"page": 2, "limit": 5}}
Error: 400 - {"error": "Email required", "status_code": 400, "request_id": "i9j0k1l2"}
```