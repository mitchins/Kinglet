"""
Kinglet Routing Demo - Basic routing features

# ⚠️ DEMO ONLY — NO AUTHENTICATION on the data endpoints below.
# This file demonstrates routing primitives (path params, routers, prefixes).
# Do not copy these routes to production without adding @require_auth (or your
# own @security_decorator) to any endpoint that returns real user data.
"""

from kinglet import Kinglet, Response, Router

app = Kinglet()


# Basic routes
@app.get("/", public=True)
async def home(request):
    return {"message": "Kinglet Routing Demo", "version": "2"}


@app.get("/hello/{name}", public=True)
async def hello(request):
    name = request.path_params.get("name", "World")
    return {"greeting": f"Hello, {name}!"}


@app.post("/echo", public=True)
async def echo(request):
    body = await request.json() or {}
    return {"echo": body, "method": "POST"}


# Router with prefix
api_router = Router()


@api_router.get("/status", public=True)
async def api_status(request):
    return {"status": "ok", "api_version": "v1"}


# ⚠️ DEMO ONLY — NO AUTHENTICATION. Do not copy to production. Real deployments
# must add @require_auth (or your own @security_decorator) before exposing user data.
@api_router.get("/users", public=True)
async def list_users(request):
    return {"users": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]}


app.include_router("/api/v1", api_router)


# Error handling
@app.exception_handler(404)
async def not_found(request, error):
    return Response({"error": "Not found", "path": request.url.pathname}, status=404)


# Cloudflare Workers entry point
async def on_fetch(request, env):
    return await app(request, env)
