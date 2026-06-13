"""
Release gates for the 2.0 default-deny route policy.

The Codex finding "Custom auth decorators can be bypassed after route binding
change" reproduced this PoC against 1.9: a custom security decorator applied
above a route decorator imported successfully and the route served
unauthenticated. Under the default route policy that exact PoC now fails closed
at registration. These tests pin that, plus the full supported matrix.

The whole module keeps the production default (enforce_route_policy=True); the
conftest relaxation that the rest of the suite uses does NOT apply here.
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
    RoutePolicyWarning,
    Router,
    TestClient,
    is_secured,
    require_dev,
    security_decorator,
)
from kinglet.authz import require_auth, require_claim

pytestmark = pytest.mark.route_policy

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


def custom_require_admin(handler):
    """A custom security decorator that does NOT opt into Kinglet's guard -
    exactly the shape the Codex PoC used."""

    async def wrapped(request):
        if request.header("x-admin-token") != "valid":
            return Response({"error": "forbidden"}, status=403)
        return await handler(request)

    return wrapped


class TestScannerPoCFailsClosedByDefault:
    """The exact reproduction from the finding must raise on a default app."""

    def test_custom_unguarded_decorator_reversed_raises_at_registration(self):
        app = Kinglet()

        with pytest.raises(RuntimeError, match="security posture"):

            @custom_require_admin
            @app.get("/admin")
            async def admin(request):
                return {"secret": True}

    def test_custom_unguarded_decorator_correct_order_also_raises(self):
        """Even in the correct order, an unrecognized custom decorator does not
        declare a security posture, so the route is refused. The fix is to make
        the decorator Kinglet-aware (see TestSecurityDecorator) or mark public."""
        app = Kinglet()

        with pytest.raises(RuntimeError, match="security posture"):

            @app.get("/admin")
            @custom_require_admin
            async def admin(request):
                return {"secret": True}

    def test_no_admin_route_is_registered_after_failure(self):
        app = Kinglet()
        try:

            @custom_require_admin
            @app.get("/admin")
            async def admin(request):
                return {"secret": True}
        except RuntimeError:
            pass
        handler, _ = app.router.resolve("GET", "/admin")
        assert handler is None, "No route may survive a failed policy check"


class TestBareRoutesRequireExplicitPublic:
    def test_bare_route_raises(self):
        app = Kinglet()
        with pytest.raises(RuntimeError, match="security posture"):

            @app.get("/anything")
            async def anything(request):
                return {"ok": True}

    def test_public_route_serves(self):
        app = Kinglet()

        @app.get("/health", public=True)
        async def health(request):
            return {"ok": True}

        status, _, body = TestClient(app).request("GET", "/health")
        assert status == 200
        assert "ok" in body

    def test_validation_only_route_is_not_secured(self):
        """Validation decorators are not access control - a route carrying only
        validation still needs an explicit public/secured declaration."""
        from kinglet import validate_json_body

        app = Kinglet()
        with pytest.raises(RuntimeError, match="security posture"):

            @app.post("/submit")
            @validate_json_body
            async def submit(request):
                return {"ok": True}


class TestBuiltinDecoratorsSatisfyPolicy:
    def test_require_auth_correct_order(self):
        app = Kinglet()

        @app.get("/secret")
        @require_auth
        @require_claim("admin", True)
        async def secret(request):
            return {"secret": True}

        client = TestClient(app, env={"JWT_SECRET": SECRET})
        assert client.request("GET", "/secret")[0] == 401
        assert client.request("GET", "/secret", headers=auth_header({}))[0] == 403
        assert (
            client.request("GET", "/secret", headers=auth_header({"admin": True}))[0]
            == 200
        )

    def test_require_dev_marks_secured(self):
        app = Kinglet()

        @app.get("/debug")
        @require_dev()
        async def debug(request):
            return {"debug": True}

        # Registered without public=True because require_dev marks it secured.
        status, _, _ = TestClient(app, env={"ENVIRONMENT": "production"}).request(
            "GET", "/debug"
        )
        assert status == 404  # dev blackhole in production


class TestSecurityDecorator:
    """@security_decorator is the one-line fix for custom decorators."""

    def test_marked_custom_decorator_correct_order_enforces(self):
        app = Kinglet()
        guarded_admin = security_decorator(custom_require_admin)

        @app.get("/admin")
        @guarded_admin
        async def admin(request):
            return {"secret": True}

        client = TestClient(app)
        assert client.request("GET", "/admin")[0] == 403
        status, _, body = client.request(
            "GET", "/admin", headers={"x-admin-token": "valid"}
        )
        assert status == 200
        assert "secret" in body

    def test_marked_custom_decorator_reversed_raises(self):
        app = Kinglet()
        guarded_admin = security_decorator(custom_require_admin)

        with pytest.raises(RuntimeError):

            @guarded_admin
            @app.get("/admin")
            async def admin(request):
                return {"secret": True}

    def test_security_decorator_output_is_marked(self):
        guarded = security_decorator(custom_require_admin)

        async def handler(request):
            return {"ok": True}

        assert is_secured(guarded(handler))

    def test_parameterized_factory_via_inner_decorator(self):
        """A factory (require_role(role)) is made Kinglet-aware by wrapping its
        INNER decorator with @security_decorator (CodeRabbit/Gemini)."""

        def require_role(role):
            @security_decorator
            def deco(handler):
                async def wrapped(request):
                    user = await __import__(
                        "kinglet.authz", fromlist=["get_user"]
                    ).get_user(request)
                    if not user or user.get("claims", {}).get("role") != role:
                        return Response({"error": "forbidden"}, status=403)
                    return await handler(request)

                return wrapped

            return deco

        app = Kinglet()

        @app.get("/admin")
        @require_role("admin")
        async def admin(request):
            return {"secret": True}

        client = TestClient(app, env={"JWT_SECRET": SECRET})
        assert client.request("GET", "/admin")[0] == 403  # no token → forbidden
        assert client.request("GET", "/admin", headers=auth_header({}))[0] == 403
        assert (
            client.request("GET", "/admin", headers=auth_header({"role": "admin"}))[0]
            == 200
        )

    def test_security_decorator_on_factory_raises_typeerror(self):
        """Applying @security_decorator to a factory (not its inner decorator)
        fails loudly instead of silently mis-marking the factory."""

        @security_decorator
        def require_role(role):  # WRONG: factory, not a simple decorator
            def deco(handler):
                return handler

            return deco

        with pytest.raises(TypeError, match="factory"):
            require_role("admin")  # invoked with a non-callable role string


class TestGeoRestrictIsNotAPosture:
    """CodeRabbit S1: geo_restrict is a forgeable network filter (fails OPEN in
    production), not an identity control, so it must not satisfy the policy."""

    def test_geo_restrict_alone_is_refused(self):
        from kinglet import geo_restrict

        app = Kinglet()
        with pytest.raises(RuntimeError, match="security posture"):

            @app.get("/geo")
            @geo_restrict(allowed=["US"])
            async def geo(request):
                return {"ok": True}

    def test_require_dev_alone_is_accepted(self):
        """Contrast: require_dev fails CLOSED (404 in prod) so it IS a posture."""
        from kinglet import require_dev

        app = Kinglet()

        @app.get("/debug")
        @require_dev()
        async def debug(request):
            return {"debug": True}

        # 404 blackhole in production - registered without public=True.
        assert (
            TestClient(app, env={"ENVIRONMENT": "production"}).request("GET", "/debug")[
                0
            ]
            == 404
        )


class TestPolicyErrorMessage:
    """CodeRabbit R2: the registration error must name the offending handler."""

    def test_error_names_handler_and_security_decorator(self):
        app = Kinglet()
        try:

            @app.get("/x")
            async def my_unprotected_view(request):
                return {"ok": True}
        except RuntimeError as e:
            msg = str(e)
            assert "my_unprotected_view" in msg
            assert "security_decorator" in msg
        else:
            raise AssertionError("expected RuntimeError")


class TestOptOutWarns:
    """CodeRabbit S3: disabling the policy must leave an audit signal."""

    def test_disabling_policy_warns(self):
        with pytest.warns(RoutePolicyWarning):
            Kinglet(enforce_route_policy=False)

    def test_router_disabling_policy_warns(self):
        with pytest.warns(RoutePolicyWarning):
            Router(enforce_route_policy=False)


class TestHeadOptionsVerbs:
    """CodeRabbit: Kinglet.head/options existed only on Router - API gap."""

    def test_app_head_and_options_accept_public(self):
        app = Kinglet()

        @app.head("/h", public=True)
        async def h(request):
            return {}

        @app.options("/o", public=True)
        async def o(request):
            return {}

        assert app.router.resolve("HEAD", "/h")[0] is not None
        assert app.router.resolve("OPTIONS", "/o")[0] is not None


class TestOptOut:
    """enforce_route_policy=False restores legacy registration for staged
    migration / middleware-based authorization."""

    def test_opt_out_allows_bare_routes(self):
        with pytest.warns(RoutePolicyWarning):
            app = Kinglet(enforce_route_policy=False)

        @app.get("/anything")
        async def anything(request):
            return {"ok": True}

        assert TestClient(app).request("GET", "/anything")[0] == 200

    def test_production_default_is_enforce_on(self):
        # The default that ships and that the scanner evaluates.
        assert Kinglet().enforce_route_policy is True
        assert Router().enforce_route_policy is True


class TestIncludeRouterPreservesPosture:
    def test_public_subroute_survives_include(self):
        app = Kinglet()
        router = Router()

        @router.get("/health", public=True)
        async def health(request):
            return {"ok": True}

        app.include_router("/api", router)
        assert TestClient(app).request("GET", "/api/health")[0] == 200

    def test_secured_subroute_survives_include(self):
        app = Kinglet()
        router = Router()

        @router.get("/secret")
        @require_auth
        async def secret(request):
            return {"secret": True}

        app.include_router("/api", router)
        assert (
            TestClient(app, env={"JWT_SECRET": SECRET}).request("GET", "/api/secret")[0]
            == 401
        )
