# Kinglet 🐦

**A lightweight, neat and tidy routing framework for Python Workers**

Kinglet is designed specifically for Cloudflare Workers Python runtime, providing a clean, FastAPI-inspired API without the heavy dependencies. Perfect for building APIs that need to stay within Workers' startup and memory limits.

## Why Kinglet?

- 🪶 **Lightweight**: Zero external dependencies, built for Workers
- 🎯 **Clean Routing**: Intuitive decorators and path parameters  
- ⚡ **Fast Startup**: No heavy framework overhead
- 🔧 **Middleware Support**: Composable request/response processing
- 🛡️ **Type Hints**: Full typing support for better DX
- 🧪 **Well Tested**: Comprehensive test suite

## Quick Start

```python
from kinglet import Kinglet

app = Kinglet()

@app.get("/")
async def hello(request):
    return {"message": "Hello, World!"}

@app.get("/users/{id}")
async def get_user(request):
    user_id = request.path_param("id")
    return {"user_id": user_id}

# Workers entry point
async def on_fetch(request, env):
    return await app(request, env)
```

## Features

### Clean Routing

```python
from kinglet import Kinglet

app = Kinglet()

# HTTP method decorators
@app.get("/users")
@app.post("/users")
@app.put("/users/{id}")
@app.delete("/users/{id}")
async def handler(request):
    return {"method": request.method}

# Path parameters with type hints
@app.get("/users/{id:int}/posts/{slug:str}")
async def get_post(request):
    user_id = request.path_param("id")  # Extracted as string
    slug = request.path_param("slug")
    return {"user_id": user_id, "slug": slug}
```

### Request Handling

```python
@app.post("/api/data")
async def handle_data(request):
    # Query parameters
    page = request.query("page", 1)
    filters = request.query_list("filter")
    
    # Headers
    auth = request.header("authorization")
    
    # JSON body
    data = await request.json()
    
    # Form data
    form = await request.form()
    
    # Client info
    ip = request.client_ip()
    user_agent = request.user_agent()
    
    return {"received": data}
```

### Response Types

```python
from kinglet import Response
from kinglet.response import json_response, redirect_response

@app.get("/json")
async def json_endpoint(request):
    # Auto-detected as JSON
    return {"key": "value"}

@app.get("/explicit")
async def explicit_response(request):
    return Response({"data": "value"}, status=201)

@app.get("/redirect")
async def redirect_endpoint(request):
    return redirect_response("https://example.com")

@app.get("/custom")
async def custom_response(request):
    return (Response({"success": True})
            .header("X-Custom", "value")
            .cors(origin="https://mysite.com")
            .cookie("session", "abc123", max_age=3600))
```

### Sub-routers

```python
from kinglet import Kinglet, Router

# Main app
app = Kinglet()

# API router
api_router = Router()

@api_router.get("/users")
async def list_users(request):
    return {"users": []}

@api_router.get("/users/{id}")
async def get_user(request):
    return {"user": {}}

# Mount the API router
app.include_router("/api/v1", api_router)

# Now accessible at:
# GET /api/v1/users
# GET /api/v1/users/123
```

### Middleware

```python
from kinglet.middleware import CorsMiddleware, TimingMiddleware

# Built-in middleware
app.middleware_stack.append(CorsMiddleware())
app.middleware_stack.append(TimingMiddleware())

# Custom middleware
@app.middleware
class AuthMiddleware:
    async def process_request(self, request):
        # Add user info to request
        token = request.header("authorization")
        if token:
            request.user = decode_token(token)
        return request
    
    async def process_response(self, request, response):
        # Add security headers
        response.header("X-Frame-Options", "DENY")
        return response
```

### Error Handling

```python
@app.exception_handler(404)
async def not_found(request, exc):
    return {"error": "Not found", "path": request.path}

@app.exception_handler(500)
async def server_error(request, exc):
    return {"error": "Internal server error"}, 500
```

## Built-in Middleware

- **CorsMiddleware**: Handle CORS headers and preflight requests
- **TimingMiddleware**: Add response time headers  
- **LoggingMiddleware**: Request/response logging
- **SecurityHeadersMiddleware**: Common security headers
- **RateLimitMiddleware**: Simple IP-based rate limiting

## Installation

```bash
pip install kinglet
```

## Workers Integration

Create your worker with Kinglet:

```python
# worker.py
from kinglet import Kinglet

app = Kinglet()

@app.get("/")
async def hello(request):
    return {"message": "Hello from Kinglet!"}

@app.get("/api/health")  
async def health_check(request):
    return {"status": "healthy"}

# Workers entry point
async def on_fetch(request, env):
    return await app(request, env)
```

Deploy with Wrangler:

```toml
# wrangler.toml
name = "my-kinglet-api"
main = "worker.py"
compatibility_date = "2024-01-01"
compatibility_flags = ["python_workers"]

[env.production]
name = "my-kinglet-api-prod"
```

## Testing

Kinglet is designed to be easily testable:

```python
import pytest
from kinglet import Kinglet

@pytest.fixture
def app():
    app = Kinglet()
    
    @app.get("/test")
    async def test_handler(request):
        return {"test": True}
    
    return app

@pytest.mark.asyncio
async def test_endpoint(app):
    # Create mock request
    mock_request = MockRequest("GET", "http://localhost/test")
    mock_env = {}
    
    # Call app
    response = await app(mock_request, mock_env)
    
    # Assert response
    assert response.status == 200
```

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black kinglet/

# Type checking
mypy kinglet/
```

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions welcome! Please read CONTRIBUTING.md for guidelines.

---

Built with ❤️ for the Python Workers community