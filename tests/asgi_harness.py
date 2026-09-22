"""
Shared helpers for Kinglet ASGI tests.

Not collected by pytest (no ``test_`` prefix): scope builders, an in-process
ASGI event harness, a portable fixture application, and a JWT minter.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
from typing import Any

from kinglet import Kinglet, Response
from kinglet.asgi import with_env
from kinglet.authz import require_auth, require_claim


def http_scope(
    path: str = "/",
    method: str = "GET",
    headers: dict[str, str] | list[tuple[str, str]] | None = None,
    query: bytes = b"",
    root_path: str = "",
    scheme: str = "http",
    server: tuple[str, int] | None = ("testserver", 80),
    state: dict[str, Any] | None = None,
    env: Any = None,
    raw_path: bytes | None = None,
) -> dict[str, Any]:
    """Build a minimal ASGI HTTP scope with explicit distinctions."""
    if headers is None:
        items: list[tuple[str, str]] = []
    elif isinstance(headers, dict):
        items = list(headers.items())
    else:
        items = list(headers)
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": scheme,
        "path": path,
        "query_string": bytes(query),
        "root_path": root_path,
        "headers": [
            (name.lower().encode("latin-1"), value.encode("latin-1"))
            for name, value in items
        ],
        "server": server,
        "client": ("client", 50000),
    }
    if raw_path is not None:
        scope["raw_path"] = bytes(raw_path)
    if state is not None:
        scope["state"] = dict(state)
    if env is not None:
        scope["env"] = env
    return scope


def body_messages(body: bytes, chunk_size: int = 0) -> list[dict[str, Any]]:
    """Split a body into ``http.request`` events (0 = single event)."""
    if chunk_size <= 0 or len(body) <= chunk_size:
        return [{"type": "http.request", "body": bytes(body), "more_body": False}]
    messages = []
    for offset in range(0, len(body), chunk_size):
        chunk = body[offset : offset + chunk_size]
        messages.append(
            {
                "type": "http.request",
                "body": chunk,
                "more_body": offset + chunk_size < len(body),
            }
        )
    return messages


class Harness:
    """In-process ASGI harness: scripted receives, recorded sends."""

    def __init__(
        self,
        scope: dict[str, Any],
        incoming: list[dict[str, Any]] | None = None,
        on_send: Any = None,
    ):
        self.scope = scope
        self._incoming = list(incoming or [])
        self.sent: list[dict[str, Any]] = []
        self._on_send = on_send

    async def receive(self) -> dict[str, Any]:
        if not self._incoming:
            raise AssertionError("ASGI receive called with no scripted message left")
        message = self._incoming.pop(0)
        if isinstance(message, Exception):
            raise message
        await asyncio.sleep(0)
        return message

    async def send(self, message: dict[str, Any]) -> None:
        self.sent.append(message)
        if self._on_send is not None:
            await self._on_send(message)
        await asyncio.sleep(0)


async def run_asgi(
    app: Kinglet,
    scope: dict[str, Any],
    incoming: list[dict[str, Any]] | None = None,
    on_send: Any = None,
) -> list[dict[str, Any]]:
    """Run ``app.asgi`` over scripted events; return emitted events."""
    harness = Harness(scope, incoming, on_send)
    await app.asgi(scope, harness.receive, harness.send)
    return harness.sent


def response_body(sent: list[dict[str, Any]]) -> bytes:
    """Concatenate ``http.response.body`` payloads from emitted events."""
    return b"".join(
        message.get("body", b"")
        for message in sent
        if message.get("type") == "http.response.body"
    )


def response_start(sent: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the single ``http.response.start`` event."""
    starts = [m for m in sent if m.get("type") == "http.response.start"]
    assert len(starts) == 1, f"expected one response start, got {len(starts)}"
    return starts[0]


def sent_headers(sent: list[dict[str, Any]]) -> list[tuple[bytes, bytes]]:
    """Return raw response header pairs from the start event."""
    return list(response_start(sent)["headers"])


def mint_jwt(secret: str, claims: dict[str, Any]) -> str:
    """Mint an HS256 JWT readable by ``kinglet.authz``."""
    header_b64 = (
        base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode())
        .decode()
        .rstrip("=")
    )
    payload_b64 = (
        base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    )
    signing_input = f"{header_b64}.{payload_b64}".encode()
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{header_b64}.{payload_b64}.{signature_b64}"


def build_fixture_app() -> Kinglet:
    """Portable fixture application: no ``workers``/``js``/``pyodide`` use."""
    app = Kinglet()

    @app.get("/health", public=True)
    async def health(request):
        return {"ok": True}

    @app.get("/echo-method", public=True)
    async def echo_method(request):
        return {
            "method": request.method,
            "path": request.path,
            "full_path": request.full_path,
        }

    @app.post("/echo-text", public=True)
    async def echo_text(request):
        return {
            "text": await request.text(),
            "body_type": type(await request.body()).__name__,
        }

    @app.post("/echo-bytes", public=True)
    async def echo_bytes(request):
        data = await request.bytes()
        return Response(data, content_type="application/octet-stream")

    @app.post("/echo-json", public=True)
    async def echo_json(request):
        return {"received": await request.json()}

    @app.get("/cookies", public=True)
    async def cookies(request):
        response = Response({"ok": True})
        response.append_header("Set-Cookie", "a=1; Path=/")
        response.append_header("Set-Cookie", "b=2; Path=/")
        return response

    @app.get("/stream", public=True)
    async def stream(request):
        async def producer():
            yield b"chunk-one-"
            yield "chunk-two-"
            yield b"chunk-three"

        return Response(producer(), content_type="text/plain")

    @app.get("/empty", public=True)
    async def empty(request):
        return Response(None, status=204)

    @app.get("/whoami")
    @require_auth
    async def whoami(request):
        return {"id": request.state.user["id"]}

    @app.get("/admin")
    @require_claim("role", "admin")
    async def admin(request):
        return {"admin": True, "id": request.state.user["id"]}

    @app.get("/env-name", public=True)
    async def env_name(request):
        return {"name": request.env.NAME}

    @app.get("/slow", public=True)
    async def slow(request):
        marker = request.query("m", "")
        request.state.marker = marker
        await asyncio.sleep(0.05)
        return {"marker": request.state.marker, "env": request.env.NAME}

    @app.get("/boom", public=True)
    async def boom(request):
        raise RuntimeError("secret-sauce-failure")

    return app


def build_smoke_scope_env() -> dict[str, Any]:
    """Nonsecret test bindings for smoke/integration runs."""
    return {"NAME": "smoke", "JWT_SECRET": "smoke-test-secret", "ENVIRONMENT": "test"}


def fixed_exp() -> int:
    """Far-future JWT expiry so time-based tests stay deterministic."""
    return int(time.time()) + 3600


__all__ = [
    "Harness",
    "body_messages",
    "build_fixture_app",
    "build_smoke_scope_env",
    "fixed_exp",
    "http_scope",
    "mint_jwt",
    "response_body",
    "response_start",
    "run_asgi",
    "sent_headers",
    "with_env",
]
