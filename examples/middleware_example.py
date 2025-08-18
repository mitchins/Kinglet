"""
Kinglet Middleware Examples (v1.4.2+)

Demonstrates flexible middleware configuration with parameters
and the new add_middleware() method.
"""

import time

from kinglet import CorsMiddleware, Kinglet

app = Kinglet(debug=True)

# Example 1: Parameterized CORS Middleware (v1.4.2+)
cors_middleware = CorsMiddleware(
    allow_origin="https://example.com",
    allow_methods="GET,POST,PUT,DELETE",
    allow_headers="Content-Type,Authorization",
    allow_credentials=True,
    max_age=86400
)
app.add_middleware(cors_middleware)

# Example 2: Custom Timing Middleware
class TimingMiddleware:
    def __init__(self, header_name="X-Response-Time"):
        self.header_name = header_name

    async def process_request(self, request):
        request.start_time = time.time()
        return request

    async def process_response(self, request, response):
        if hasattr(request, 'start_time'):
            duration = time.time() - request.start_time
            response.header(self.header_name, f'{duration:.3f}s')
        return response

# Add timing middleware with custom header name
timing = TimingMiddleware(header_name="X-API-Time")
app.add_middleware(timing)

# Example 3: Error Enhancement Middleware (v1.4.2+ error processing)
class ErrorEnhancementMiddleware:
    async def process_response(self, request, response):
        if response.status >= 400:
            # Add debugging headers to all error responses
            response.header('X-Error-Timestamp', str(int(time.time())))
            response.header('X-Request-Path', request.path)

            # Log errors (would integrate with your logging system)
            print(f"Error {response.status}: {request.method} {request.path}")

        return response

app.add_middleware(ErrorEnhancementMiddleware())

# Example 4: Authentication Middleware
class AuthMiddleware:
    def __init__(self, exempt_paths=None):
        self.exempt_paths = exempt_paths or ['/health', '/public']

    async def process_request(self, request):
        # Skip auth for exempt paths
        if any(request.path.startswith(path) for path in self.exempt_paths):
            return request

        # Check for API key
        api_key = request.header('X-API-Key')
        if not api_key or api_key != 'demo-key':
            from kinglet import Response
            return Response({'error': 'API key required'}, status=401)

        # Add user info to request
        request.user = {'id': 'demo-user', 'api_key': api_key}
        return request

auth = AuthMiddleware(exempt_paths=['/health', '/public'])
app.add_middleware(auth)

# Routes to test middleware
@app.get("/health")
async def health_check(request):
    return {"status": "healthy", "middleware": "working"}

@app.get("/api/protected")
async def protected_endpoint(request):
    # This will require X-API-Key header
    user = getattr(request, 'user', None)
    return {"message": "Access granted", "user": user}

@app.get("/api/data")
async def api_data(request):
    # Simulate some processing time to see timing middleware
    import asyncio
    await asyncio.sleep(0.1)
    return {"data": "example", "processing_time": "~100ms"}

# Example 5: Traditional decorator style still works
@app.middleware
class LegacyMiddleware:
    def __init__(self):
        pass

    async def process_request(self, request):
        request.legacy_processed = True
        return request

if __name__ == "__main__":
    # Test with curl:
    # curl http://localhost:8000/health
    # curl -H "X-API-Key: demo-key" http://localhost:8000/api/protected
    # curl http://localhost:8000/api/data
    print("Middleware examples ready!")
    print("Test endpoints:")
    print("  GET /health (public)")
    print("  GET /api/protected (requires X-API-Key: demo-key)")
    print("  GET /api/data (shows timing)")
