"""
Kinglet + Cloudflare Workers Demo

Simple example showing Kinglet running on Cloudflare Workers
"""
from kinglet import Kinglet

app = Kinglet()

@app.get("/")
async def hello(request):
    return {
        "message": "Hello from Kinglet!",
        "edge": "Cloudflare Workers", 
        "request_id": request.request_id
    }

@app.get("/env")
async def env_info(request):
    return {
        "message": getattr(request.env, 'MESSAGE', 'No message set'),
        "environment": "Cloudflare Workers",
        "request_id": request.request_id
    }

@app.get("/health")
async def health_check(request):
    return {
        "status": "healthy",
        "framework": "Kinglet",
        "platform": "Cloudflare Workers",
        "request_id": request.request_id
    }

# Required: Cloudflare Workers entry point
async def on_fetch(request, env):
    return await app(request, env)