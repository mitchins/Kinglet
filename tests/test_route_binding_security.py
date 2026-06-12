"""
Release gates for the route/auth handler-binding invariant.

A Route executes exactly the callable registered at route declaration time.
Handlers are never recovered by module/global name lookup, __wrapped__
traversal, or closure inspection. Built-in security decorators applied
above/outside a route decorator fail loudly at import time instead of
leaving the route silently unprotected.
"""

import base64
import hashlib
import hmac
import json
import time

import pytest

from kinglet import Kinglet, Response, Router, TestClient
from kinglet.authz import require_auth, require_claim

SECRET = "unit-test-secret"


def make_jwt(payload: dict, secret: str = SECRET) -> str:
    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode().rstrip("=")

    header_b64 = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload_b64 = b64(json.dumps(payload).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode()
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{b64(signature)}"


def auth_header(claims: dict) -> dict:
    payload = {"sub": "user-123", "exp": int(time.time()) + 3600, **claims}
    return {"Authorization": f"Bearer {make_jwt(payload)}"}


class TestCorrectDecoratorOrder:
    def _build_app(self):
        app = Kinglet()

        @app.get("/secret")
        @require_auth
        @require_claim("admin", True)
        async def secret(request):
            return {"secret": True}

        return app

    def test_no_token_returns_401(self):
        client = TestClient(self._build_app(), env={"JWT_SECRET": SECRET})
        status, _, _ = client.request("GET", "/secret")
        assert status == 401

    def test_non_admin_token_returns_403(self):
        client = TestClient(self._build_app(), env={"JWT_SECRET": SECRET})
        status, _, body = client.request("GET", "/secret", headers=auth_header({}))
        assert status == 403
        assert "MISSING_CLAIM" in body

    def test_admin_token_returns_200(self):
        client = TestClient(self._build_app(), env={"JWT_SECRET": SECRET})
        status, _, body = client.request(
            "GET", "/secret", headers=auth_header({"admin": True})
        )
        assert status == 200
        assert "secret" in body


class TestReversedDecoratorOrderFailsAtImport:
    def test_single_security_decorator_above_route_raises(self):
        app = Kinglet()

        with pytest.raises(RuntimeError) as exc_info:

            @require_auth
            @app.get("/secret")
            async def secret(request):
                return {"secret": True}

        message = str(exc_info.value)
        assert "require_auth" in message
        assert "@app.get('/path')" in message  # explains the correct order

    def test_nested_security_decorators_above_route_raise(self):
        """The innermost security decorator sees the registered handler and
        raises immediately - no route is left silently unprotected."""
        app = Kinglet()

        with pytest.raises(RuntimeError, match="require_claim"):

            @require_auth
            @require_claim("admin", True)
            @app.get("/secret")
            async def secret(request):
                return {"secret": True}

    def test_router_decorators_are_guarded_too(self):
        router = Router()

        with pytest.raises(RuntimeError, match="require_auth"):

            @require_auth
            @router.get("/secret")
            async def secret(request):
                return {"secret": True}


class TestNoHandlerRebinding:
    def test_same_name_functions_do_not_rebind(self):
        app = Kinglet()

        @app.get("/admin")
        @require_auth
        async def endpoint(request):
            return {"admin": True}

        globals()["endpoint"] = endpoint

        @app.get("/public")
        async def endpoint(request):
            return {"public": True}

        globals()["endpoint"] = endpoint

        client = TestClient(app, env={"JWT_SECRET": SECRET})

        status, _, body = client.request("GET", "/admin")
        assert status == 401, "/admin must never execute the same-named public handler"
        assert "admin" not in body

        status, _, body = client.request("GET", "/public")
        assert status == 200
        assert "public" in body

        status, _, body = client.request("GET", "/admin", headers=auth_header({}))
        assert status == 200
        assert "admin" in body
        globals().pop("endpoint", None)

    def test_module_global_wrapper_is_never_recovered(self):
        """A module-level wrapper that captures the registered handler (via
        closure and __wrapped__) is ignored unless it was actually registered."""
        app = Kinglet(auto_wrap_exceptions=False)

        @app.get("/data")
        async def data(request):
            return Response({"original": True}, status=200)

        registered = data

        async def wrapper(request):
            return Response({"hijacked": True}, status=200) or await registered(request)

        wrapper.__name__ = "data"
        wrapper.__module__ = registered.__module__
        wrapper.__wrapped__ = registered
        globals()["data"] = wrapper

        handler, _ = app.router.resolve("GET", "/data")
        assert handler is registered

        client = TestClient(app)
        status, _, body = client.request("GET", "/data")
        assert status == 200
        assert "original" in body
        assert "hijacked" not in body
        globals().pop("data", None)
