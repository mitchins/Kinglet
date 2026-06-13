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

from kinglet import (
    Kinglet,
    Response,
    Router,
    TestClient,
    geo_restrict,
    is_route_registered,
    require_dev,
    require_field,
    validate_json_body,
)
from kinglet.authz import (
    allow_public_or_owner,
    require_auth,
    require_claim,
    require_elevated_claim,
    require_elevated_session,
    require_owner,
    require_participant,
)

pytestmark = pytest.mark.route_policy

SECRET = "unit-test-secret"


async def _load_stub(req, rid):
    return None


# Every built-in security/access/validation decorator must reject a handler
# that is already route-registered. If a decorator loses its guard call, the
# parametrized test below goes red for exactly that decorator.
ALL_GUARDED_DECORATORS = [
    ("require_auth", lambda: require_auth),
    ("require_elevated_session", lambda: require_elevated_session),
    ("require_claim", lambda: require_claim("admin")),
    ("require_elevated_claim", lambda: require_elevated_claim("admin")),
    ("require_owner", lambda: require_owner(_load_stub)),
    ("require_participant", lambda: require_participant(_load_stub)),
    ("allow_public_or_owner", lambda: allow_public_or_owner(_load_stub)),
    ("require_dev", lambda: require_dev()),
    ("geo_restrict", lambda: geo_restrict(allowed=["US"])),
    ("validate_json_body", lambda: validate_json_body),
    ("require_field", lambda: require_field("name")),
]


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


class TestReversedDecoratorOrderFailsClosed:
    """Default (enforce_route_policy on): a security decorator above the route
    decorator leaves the route decorator innermost, so it registers a bare
    handler. The route policy rejects that handler at registration - before
    the request ever runs - so no route is left silently unprotected."""

    def test_single_reversed_raises(self):
        app = Kinglet()

        with pytest.raises(RuntimeError, match="security posture"):

            @require_auth
            @app.get("/secret")
            async def secret(request):
                return {"secret": True}

    def test_nested_reversed_raises(self):
        app = Kinglet()

        with pytest.raises(RuntimeError, match="security posture"):

            @require_auth
            @require_claim("admin", True)
            @app.get("/secret")
            async def secret(request):
                return {"secret": True}

    def test_router_reversed_raises(self):
        router = Router()

        with pytest.raises(RuntimeError, match="security posture"):

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

        try:
            globals()["endpoint"] = endpoint

            @app.get("/public", public=True)
            async def endpoint(request):
                return {"public": True}

            globals()["endpoint"] = endpoint

            client = TestClient(app, env={"JWT_SECRET": SECRET})

            status, _, body = client.request("GET", "/admin")
            assert status == 401, (
                "/admin must never execute the same-named public handler"
            )
            assert "admin" not in body

            status, _, body = client.request("GET", "/public")
            assert status == 200
            assert "public" in body

            status, _, body = client.request("GET", "/admin", headers=auth_header({}))
            assert status == 200
            assert "admin" in body
        finally:
            globals().pop("endpoint", None)

    def test_module_global_wrapper_is_never_recovered(self):
        """A module-level wrapper that captures the registered handler (via
        closure and __wrapped__) is ignored unless it was actually registered."""
        app = Kinglet(auto_wrap_exceptions=False)

        @app.get("/data", public=True)
        async def data(request):
            return Response({"original": True}, status=200)

        registered = data

        async def wrapper(request):
            return Response({"hijacked": True}, status=200) or await registered(request)

        wrapper.__name__ = "data"
        wrapper.__module__ = registered.__module__
        wrapper.__wrapped__ = registered
        try:
            globals()["data"] = wrapper

            handler, _ = app.router.resolve("GET", "/data")
            assert handler is registered

            client = TestClient(app)
            status, _, body = client.request("GET", "/data")
            assert status == 200
            assert "original" in body
            assert "hijacked" not in body
        finally:
            globals().pop("data", None)


class TestUnmarkableHandlers:
    """Callables that cannot carry attributes must still trip the guard."""

    def test_route_registered_bound_method_is_guarded(self):
        class Controller:
            async def secret(self, request):
                return {"secret": True}

        controller = Controller()
        router = Router()
        # Bound methods reject setattr; the weak registry must catch them.
        # public=True only satisfies the route policy; the route-registered
        # marker (what this test exercises) is independent of it.
        router.add_route("/secret", controller.secret, ["GET"], public=True)

        # Every `controller.secret` access creates a fresh bound-method object;
        # it must still be recognised via (instance, function) equality.
        assert is_route_registered(controller.secret)
        with pytest.raises(RuntimeError, match="require_auth"):
            require_auth(controller.secret)

    def test_unregistered_bound_method_is_not_flagged(self):
        class Controller:
            async def secret(self, request):
                return {"secret": True}

        assert not is_route_registered(Controller().secret)
        # Wrapping before registration stays allowed.
        require_auth(Controller().secret)

    def test_wraps_wrapper_of_registered_handler_is_not_route_registered(self):
        """The route-registered marker is a weak registry, not a function
        attribute, so functools.wraps does NOT propagate it. A wrapper that
        wraps a registered handler must not be falsely treated as registered
        (which would make the decorator-order guard reject it spuriously)."""
        import functools

        app = Kinglet()

        @app.get("/data", public=True)
        async def data(request):
            return {}

        assert is_route_registered(data)

        @functools.wraps(data)  # copies __dict__ - must NOT carry registration
        async def wrapper(request):
            return await data(request)

        assert not is_route_registered(wrapper)
        # Applying a security decorator to the wrapper must NOT falsely raise.
        require_auth(wrapper)


class TestEveryBuiltinDecoratorIsGuarded:
    """One red test per decorator if its guard call is ever removed."""

    @pytest.mark.parametrize(
        ("name", "factory"),
        ALL_GUARDED_DECORATORS,
        ids=[name for name, _ in ALL_GUARDED_DECORATORS],
    )
    def test_reversed_order_raises(self, name, factory):
        router = Router()

        # public=True lets the route register; the handler is then marked
        # route-registered, so applying a security decorator on top of it must
        # be rejected by that decorator's own guard (isolates the guard from
        # the route policy, which would otherwise also fire).
        @router.get("/guarded", public=True)
        async def handler(request):
            return {"ok": True}

        with pytest.raises(RuntimeError, match=name):
            factory()(handler)


class TestLegitimatePatternsStayAllowed:
    """Guard must not fire on supported usage - protects against an
    overzealous future guard (e.g. one added to wrap_exceptions or the
    route decorators themselves, which would break route stacking)."""

    def test_stacked_route_decorators_do_not_trip_guard(self):
        app = Kinglet()

        # Registering one handler for two methods is supported; the inner
        # route decorator marks the handler, the outer one re-wraps it.
        @app.get("/things")
        @app.post("/things")
        @require_auth
        async def things(request):
            return {"ok": True}

        client = TestClient(app, env={"JWT_SECRET": SECRET})
        for method in ("GET", "POST"):
            status, _, _ = client.request(method, "/things")
            assert status == 401, f"{method} /things must stay protected"
            status, _, _ = client.request(method, "/things", headers=auth_header({}))
            assert status == 200, f"{method} /things must work with auth"
