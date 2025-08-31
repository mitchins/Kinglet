# Middleware Guide

Kinglet provides a flexible middleware system for cross-cutting concerns like CORS, timing, authentication, and logging.

## Quick Start

### Basic Middleware Registration

```python
from kinglet import Kinglet, CorsMiddleware

app = Kinglet()

# New in v1.4.2: Direct middleware configuration
cors_middleware = CorsMiddleware(
    allow_origin="https://example.com",
    allow_methods="GET,POST,PUT,DELETE",
    allow_headers="Content-Type,Authorization"
)
app.add_middleware(cors_middleware)
```

### Traditional Decorator Style

```python
@app.middleware
class TimingMiddleware:
    def __init__(self):
        pass

    async def process_request(self, request):
        request.start_time = time.time()
        return request

    async def process_response(self, request, response):
        duration = time.time() - request.start_time
        response.header('X-Response-Time', f'{duration:.3f}s')
        return response
```

## Built-in Middleware

### CorsMiddleware
```python
cors = CorsMiddleware(
    allow_origin="*",                    # Origins allowed
    allow_methods="GET,POST,PUT,DELETE", # HTTP methods
    allow_headers="Content-Type,Authorization", # Headers
    allow_credentials=True,              # Include credentials
    max_age=86400                        # Preflight cache time
)
app.add_middleware(cors)
```

### TimingMiddleware
```python
@app.middleware
class TimingMiddleware:
    async def process_request(self, request):
        request.start_time = time.time()
        return request

    async def process_response(self, request, response):
        duration = time.time() - request.start_time
        response.header('X-Response-Time', f'{duration:.3f}s')
        return response
```

## Custom Middleware

### Request/Response Processing

```python
class AuthMiddleware:
    def __init__(self, secret_key):
        self.secret_key = secret_key

    async def process_request(self, request):
        # Modify request before handler
        if request.path.startswith('/api/'):
            token = request.bearer_token()
            if not self.validate_token(token):
                return Response({'error': 'Unauthorized'}, status=401)
        return request

    async def process_response(self, request, response):
        # Modify response after handler
        response.header('X-API-Version', '1.0')
        return response

# Use with parameters
auth = AuthMiddleware(secret_key="your-secret")
app.add_middleware(auth)
```

### Error Handling Middleware

```python
class ErrorLoggingMiddleware:
    async def process_response(self, request, response):
        if response.status >= 400:
            print(f"Error {response.status}: {request.method} {request.path}")
        return response

app.add_middleware(ErrorLoggingMiddleware())
```

## Middleware Order

Middleware processes requests in the order they're added and responses in reverse order:

```python
app.add_middleware(CorsMiddleware())      # First request, last response
app.add_middleware(TimingMiddleware())    # Second request, second-to-last response
app.add_middleware(AuthMiddleware())      # Last request, first response
```

## Advanced Patterns

### Conditional Middleware

```python
class ConditionalMiddleware:
    def __init__(self, condition_func):
        self.condition_func = condition_func

    async def process_request(self, request):
        if self.condition_func(request):
            # Apply middleware logic
            pass
        return request

# Only apply to API endpoints
api_only = lambda req: req.path.startswith('/api/')
app.add_middleware(ConditionalMiddleware(api_only))
```

### Middleware with Dependencies

```python
class DatabaseMiddleware:
    def __init__(self, db_pool):
        self.db_pool = db_pool

    async def process_request(self, request):
        request.db = await self.db_pool.acquire()
        return request

    async def process_response(self, request, response):
        if hasattr(request, 'db'):
            await self.db_pool.release(request.db)
        return response
```

## Migration from v1.4.1

### Before (Required Subclassing)
```python
@app.middleware
class ConfiguredCors(CorsMiddleware):
    def __init__(self):
        super().__init__(allow_origin="*", allow_methods="GET,POST")
```

### After (Direct Configuration)
```python
cors = CorsMiddleware(allow_origin="*", allow_methods="GET,POST")
app.add_middleware(cors)
```

## Error Response Processing

**New in v1.4.2:** Error responses now properly process through the middleware stack:

```python
class ErrorEnhancementMiddleware:
    async def process_response(self, request, response):
        if response.status >= 400:
            # Add error tracking headers
            response.header('X-Error-ID', generate_error_id())
            response.header('X-Request-ID', request.request_id)
        return response
```

This middleware will enhance ALL error responses, including:
- Custom error handlers
- Default framework error responses
- Exception responses

## Best Practices

1. **Keep middleware lightweight** - Heavy processing should be in route handlers
2. **Handle errors gracefully** - Don't let middleware crash the request
3. **Use parameters** - Prefer `add_middleware()` over subclassing for configuration
4. **Order matters** - Consider request/response processing order
5. **Clean up resources** - Use `process_response` for cleanup logic
