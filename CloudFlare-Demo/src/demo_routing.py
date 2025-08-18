"""
Kinglet Routing Demo - Basic routing features
"""
from kinglet import Kinglet, Response, Router

app = Kinglet()

# Basic routes
@app.get("/")
async def home(request):
    return {"message": "Kinglet Routing Demo", "version": "2"}

@app.get("/hello/{name}")
async def hello(request):
    name = request.path_params.get('name', 'World')
    return {"greeting": f"Hello, {name}!"}

@app.post("/echo")
async def echo(request):
    body = await request.json() or {}
    return {"echo": body, "method": "POST"}

# Router with prefix
api_router = Router()

@api_router.get("/status")
async def api_status(request):
    return {"status": "ok", "api_version": "v1"}

@api_router.get("/users")
async def list_users(request):
    return {
        "users": [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"}
        ]
    }

app.include_router("/api/v1", api_router)

# Error handling
@app.exception_handler(404)
async def not_found(request, error):
    return Response({"error": "Not found", "path": request.url.pathname}, status=404)

# Cloudflare Workers entry point
async def on_fetch(request, env):
    return await app(request, env)
