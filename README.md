<div align="center">
  <img src="logo.png" alt="Kinglet Logo" width="200" height="200">
  <h1>Kinglet</h1>
  <p><strong>Lightning-fast Python web framework for Cloudflare Workers</strong></p>
  
  [![CI](https://github.com/mitchins/Kinglet/actions/workflows/ci.yml/badge.svg)](https://github.com/mitchins/Kinglet/actions/workflows/ci.yml)
  [![codecov](https://codecov.io/github/mitchins/kinglet/graph/badge.svg?token=VSA89V2XBH)](https://codecov.io/github/mitchins/kinglet)
  [![PyPI version](https://badge.fury.io/py/kinglet.svg)](https://badge.fury.io/py/kinglet)
  [![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
</div>

## Quick Start

Install: `pip install kinglet` or add `dependencies = ["kinglet"]` to pyproject.toml

```python
from kinglet import Kinglet, CorsMiddleware, cache_aside_d1

app = Kinglet(root_path="/api")

# Flexible middleware (v1.4.2+)
app.add_middleware(CorsMiddleware(allow_origin="*"))

@app.post("/auth/login")
async def login(request):
    data = await request.json()
    return {"token": "jwt-token", "user": data["email"]}

@app.get("/api/data")
@cache_aside_d1(cache_type="api_data", ttl=1800)  # D1 caching (v1.5.0+)
async def get_data(request):
    return {"data": "cached_in_prod_fresh_in_dev"}
```

## Why Kinglet?

| Feature | Kinglet | FastAPI | Flask |
|---------|---------|---------|-------|
| **Bundle Size** | 226KB | 7.8MB | 1.9MB |
| **Testing** | No server needed | TestServer required | Test client required |
| **Workers Ready** | ✅ Built-in | ❌ Complex setup | ❌ Not compatible |

## Key Features

**Core:** Decorator routing, typed parameters, flexible middleware, auto error handling, serverless testing
**Cloudflare:** D1/R2/KV helpers, D1-backed caching, environment-aware policies, CDN-aware URLs  
**Database:** Micro-ORM for D1 with migrations, field validation, bulk operations (v1.6.0+)
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

**Flexible Middleware & Caching:**
```python
# Configure middleware with parameters
cors = CorsMiddleware(allow_origin="*", allow_methods="GET,POST")
app.add_middleware(cors)

# D1-backed caching (v1.5.0+) - faster and cheaper for <1MB responses
@app.get("/api/data")
@cache_aside_d1(cache_type="api_data", ttl=1800)  # D1 primary, R2 fallback
async def get_data(request):
    return {"data": "expensive_query_result"}

# R2-backed caching for larger responses
@app.get("/api/large")
@cache_aside(cache_type="large_data", ttl=3600)  # Environment-aware
async def get_large_data(request):
    return {"data": "large_expensive_query_result"}
```

**D1 Micro-ORM (v1.6.0+):**
```python
from kinglet import Model, StringField, IntegerField

class Game(Model):
    title = StringField(max_length=200)
    score = IntegerField(default=0)

# Simple CRUD with field validation
game = await Game.objects.create(db, title="Pac-Man", score=100)
top_games = await Game.objects.filter(db, score__gte=90).order_by("-score").all()
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
- **[ORM Guide](docs/ORM.md)** - D1 micro-ORM with migrations (v1.6.0+)
- **[Middleware Guide](docs/MIDDLEWARE.md)** - Flexible middleware system (v1.4.2+)
- **[Caching Guide](docs/CACHING.md)** - Environment-aware caching (v1.4.3+)
- **[Security Guide](docs/SECURITY_BEST_PRACTICES.md)** - Critical security patterns
- **[TOTP/2FA Guide](docs/TOTP.md)** - Two-factor authentication

---

Built for Cloudflare Workers Python community. **[Need help?](https://github.com/mitchins/Kinglet/issues)**