<div align="center">
  <img src="logo.png" alt="Kinglet Logo" width="200" height="200">
  <h1>Kinglet</h1>
  <p><strong>Lightning-fast Python web framework for Cloudflare Workers</strong></p>
</div>

## Quick Start

Available on PyPi either: run `pip install kinglet` or add to pyproject.toml `dependencies = ["kinglet"]`

If you can't install packages: embed `kinglet/kinglet.py` into your worker/src or project

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
| **Bundle Size** | 29KB | 7.8MB | 1.9MB |
| **Testing** | No server needed | Requires TestServer | Requires test client |
| **Workers Ready** | ✅ Built-in | ❌ Complex setup | ❌ Not compatible |

*In practical terms FastAPI's load time (especially on cold start) may exceed the worker allownace of cloudflare. Additionally Flask, Bottle and co have different expectations for the tuple that ASGI passes in.*

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

- **[Quick Examples](docs/EXAMPLES.md)** - Common patterns
- **[Testing Guide](docs/TESTING.md)** - Unit & integration testing  
- **[Cloudflare Setup](docs/CLOUDFLARE.md)** - Workers deployment
- **[API Reference](docs/API.md)** - Complete method docs

## Production Ready

- **Request ID tracing** for debugging
- **Typed parameter validation** (int, bool, UUID)
- **Built-in authentication helpers** (Bearer, Basic auth)
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