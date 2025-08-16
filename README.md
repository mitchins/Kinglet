<div align="center">
  <img src="logo.png" alt="Kinglet Logo" width="200" height="200">
  <h1>Kinglet</h1>
  <p><strong>Lightning-fast Python web framework for Cloudflare Workers</strong></p>
</div>

## Quick Start

Install: `pip install kinglet` or add `dependencies = ["kinglet"]` to pyproject.toml

```python
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
| **Bundle Size** | 226KB | 7.8MB | 1.9MB |
| **Testing** | No server needed | TestServer required | Test client required |
| **Workers Ready** | ✅ Built-in | ❌ Complex setup | ❌ Not compatible |

## Key Features

**Core:** Decorator routing, typed parameters, middleware, auto error handling, serverless testing
**Cloudflare:** D1/R2/KV helpers, cache-aside pattern, CDN-aware URLs  
**Security:** JWT validation, TOTP/2FA, geo-restrictions, fine-grained auth decorators
**Developer:** Full type hints, debug mode, request validation, zero-dependency testing

## Examples

**Typed Parameters & Auth:**
```python
@app.get("/users/{user_id}")
async def get_user(request):
    user_id = request.path_param_int("user_id")  # Validates or returns 400
    token = request.bearer_token()               # Extract JWT
    limit = request.query_int("limit", 10)       # Query params with defaults
    return {"user": user_id, "token": token}
```

**Security & Access Control:**
```python
@app.get("/admin/debug")
@require_dev()                    # 404 in production (blackhole)
@geo_restrict(allowed=["US"])     # HTTP 451 for other countries
async def debug_endpoint(request):
    return {"debug": "sensitive data"}
```

**Testing (No Server):**
```python
def test_api():
    client = TestClient(app)
    status, headers, body = client.request("GET", "/users/123")
    assert status == 200
```

## Documentation

- **[Examples](examples/)** - Quick start examples  
- **[Security Guide](docs/SECURITY_BEST_PRACTICES.md)** - Critical security patterns
- **[API Reference](docs/)** - Complete documentation

---

Built for Cloudflare Workers Python community. **[Need help?](https://github.com/mitchins/Kinglet/issues)**