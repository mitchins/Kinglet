"""
Portable Kinglet fixture app for real ASGI servers (uvicorn / hypercorn).

Import-safe without ``workers``/``js``/``pyodide``. Run with::

    uv run uvicorn tests.asgi_smoke_app:application
    uv run hypercorn tests.asgi_smoke_app:application --worker-class asyncio
"""

from __future__ import annotations

import asyncio

from kinglet import Response
from kinglet.asgi import with_env
from tests.asgi_harness import build_fixture_app

SMOKE_SECRET = "smoke-test-secret"

_app = build_fixture_app()


@_app.get("/stream-slow", public=True)
async def stream_slow(request):
    async def producer():
        yield b"first"
        await asyncio.sleep(1.0)
        yield b"second"

    return Response(producer(), content_type="text/plain")


application = with_env(
    _app.asgi,
    {"NAME": "smoke", "JWT_SECRET": SMOKE_SECRET, "ENVIRONMENT": "test"},
)
