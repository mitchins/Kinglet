"""
Kinglet Core - Routing and application framework
"""

from __future__ import annotations

import logging
import re
import warnings
from collections.abc import Callable
from types import SimpleNamespace

from .asgi import send_response as _send_asgi_response
from .decorators import (
    RoutePolicyWarning,
    assert_route_security,
    mark_route_registered,
)
from .exceptions import HTTPError
from .http import Request, Response, is_workers_native_response
from .middleware import Middleware

logger = logging.getLogger(__name__)


class _FallbackRequest:
    """Minimal request stand-in when Request construction itself fails."""

    request_id = "unknown"
    env = type("Env", (), {})()
    method = "GET"
    path = "/"
    url = "/"
    scope = None

    def __init__(self) -> None:
        # Per-instance mutable state: class-level dicts would leak across
        # fallback requests when error-path middleware mutates them.
        self.headers: dict[str, str] = {}
        self.query_params: dict[str, str] = {}
        self.path_params: dict[str, str] = {}
        self.state = SimpleNamespace()

    def header(self, name: str, default: str | None = None) -> str | None:
        return self.headers.get(name, default)


class Route:
    """Represents a single route.

    A route executes exactly the callable registered at declaration time.
    Handlers are never recovered by module/global name lookup or wrapper
    inspection: security decorators must wrap the handler *before* route
    registration (route decorator outermost), and the built-in security
    decorators raise at import time if applied in the wrong order.
    """

    def __init__(
        self, path: str, handler: Callable, methods: list[str], public: bool = False
    ):
        self.path = path
        # Invariant: self.handler must remain the exact object passed to
        # mark_route_registered. The route-registered marker is a weak registry;
        # for bound-method handlers the entry survives only while this strong
        # reference does. Storing a re-wrapped/copied handler here while marking
        # the original would let the entry be collected early and silently
        # weaken the decorator-order guard (fail-loud -> fail-silent; still not
        # an auth bypass, since the route policy is the backstop).
        self.handler = mark_route_registered(handler)
        self.methods = [m.upper() for m in methods]
        self.public = public  # explicit access posture, preserved for include_router

        # Convert path to regex with parameter extraction
        self.regex, self.param_names = self._compile_path(path)

    def _compile_path(self, path: str) -> tuple[re.Pattern, list[str]]:
        """Convert path pattern to regex with parameter names"""
        param_names = []
        regex_pattern = path

        # Find path parameters like {id}, {slug}, etc.
        param_pattern = re.compile(r"\{([^}]+)\}")

        for match in param_pattern.finditer(path):
            param_name = match.group(1)
            param_names.append(param_name)

            # Support type hints like {id:int} or {slug:str}
            if ":" in param_name:
                param_name, param_type = param_name.split(":", 1)
                param_names[-1] = param_name  # Store clean name

                if param_type == "int":
                    replacement = r"(\d+)"
                elif param_type == "path":
                    replacement = r"(.*)"  # Match everything including slashes
                else:  # default to string
                    replacement = r"([^/]+)"
            else:
                replacement = r"([^/]+)"

            regex_pattern = regex_pattern.replace(match.group(0), replacement)

        # Ensure exact match
        if not regex_pattern.endswith("$"):
            regex_pattern += "$"
        if not regex_pattern.startswith("^"):
            regex_pattern = "^" + regex_pattern

        return re.compile(regex_pattern), param_names

    def matches(self, method: str, path: str) -> tuple[bool, dict[str, str]]:
        """Check if route matches method and path, return path params if match"""
        if method.upper() not in self.methods:
            return False, {}

        match = self.regex.match(path)
        if not match:
            return False, {}

        # Extract path parameters
        path_params = {}
        for i, param_name in enumerate(self.param_names):
            path_params[param_name] = match.group(i + 1)

        return True, path_params


class Router:
    """HTTP router for organizing routes"""

    def __init__(self, enforce_route_policy: bool = True):
        self.routes: list[Route] = []
        self.sub_routers: list[Router] = []
        # Default-deny: every route must be explicitly public or carry a
        # recognized access-control marker. Opt out for staged migration or
        # middleware-based authorization.
        self.enforce_route_policy = enforce_route_policy
        if not enforce_route_policy:
            warnings.warn(
                "Route security policy is disabled (enforce_route_policy=False): "
                "routes may register without declaring a security posture. This "
                "removes a guard against accidentally unprotected routes - ensure "
                "authorization is enforced elsewhere (e.g. middleware).",
                RoutePolicyWarning,
                stacklevel=2,
            )

    def add_route(
        self, path: str, handler: Callable, methods: list[str], public: bool = False
    ):
        """Add a route to the router"""
        if self.enforce_route_policy:
            assert_route_security(handler, public=public, path=path)
        route = Route(path, handler, methods, public=public)
        self.routes.append(route)

    def route(self, path: str, methods: list[str] = None, *, public: bool = False):
        """Decorator for adding routes"""
        if methods is None:
            methods = ["GET"]

        def decorator(handler):
            self.add_route(path, handler, methods, public=public)
            return handler

        return decorator

    def get(self, path: str, *, public: bool = False):
        """Decorator for GET routes"""
        return self.route(path, ["GET"], public=public)

    def post(self, path: str, *, public: bool = False):
        """Decorator for POST routes"""
        return self.route(path, ["POST"], public=public)

    def put(self, path: str, *, public: bool = False):
        """Decorator for PUT routes"""
        return self.route(path, ["PUT"], public=public)

    def delete(self, path: str, *, public: bool = False):
        """Decorator for DELETE routes"""
        return self.route(path, ["DELETE"], public=public)

    def patch(self, path: str, *, public: bool = False):
        """Decorator for PATCH routes"""
        return self.route(path, ["PATCH"], public=public)

    def head(self, path: str, *, public: bool = False):
        """Decorator for HEAD routes"""
        return self.route(path, ["HEAD"], public=public)

    def options(self, path: str, *, public: bool = False):
        """Decorator for OPTIONS routes"""
        return self.route(path, ["OPTIONS"], public=public)

    def include_router(self, prefix: str, router: Router):
        """Include another router with a path prefix.

        Routes are re-validated against *this* router's policy as they are
        merged (strict wins), so a sub-router built with
        ``enforce_route_policy=False`` must still declare each route
        ``public=True`` or secured before it can be included into an enforcing
        parent - otherwise ``include_router`` raises ``RuntimeError``.
        """
        # Normalize prefix: ensure it starts with / and doesn't end with /
        if not prefix.startswith("/"):
            prefix = "/" + prefix
        prefix = prefix.rstrip("/")

        for route in router.routes:
            # Combine prefix with route path. Routes were already validated at
            # their own registration; propagate their declared public posture
            # so the merge does not re-reject intentionally public routes.
            new_path = prefix + route.path
            self.add_route(new_path, route.handler, route.methods, public=route.public)

    def resolve(self, method: str, path: str) -> tuple[Callable | None, dict[str, str]]:
        """Find matching route and return handler with path params"""
        for route in self.routes:
            matches, path_params = route.matches(method, path)
            if matches:
                return route.handler, path_params
        return None, {}

    def get_routes(self):
        """Get all registered routes as tuples (path, methods, handler)"""
        return [(route.path, route.methods, route.handler) for route in self.routes]


class Kinglet:
    """Main application class"""

    def __init__(
        self,
        test_mode=False,
        root_path="",
        debug=False,
        auto_wrap_exceptions=True,
        enforce_route_policy=True,
    ):
        self.router = Router(enforce_route_policy=enforce_route_policy)
        self.middleware_stack: list[Middleware] = []
        self.error_handlers: dict[int, Callable] = {}
        self.test_mode = test_mode
        self.root_path = root_path.rstrip("/")  # Remove trailing slash
        self.debug = debug
        self.auto_wrap_exceptions = auto_wrap_exceptions
        self.enforce_route_policy = enforce_route_policy

    def route(self, path: str, methods: list[str] = None, *, public: bool = False):
        """Add route decorator"""

        def decorator(handler):
            # Auto-wrap with exception handling if enabled. functools.wraps in
            # wrap_exceptions preserves any access-control marker on the inner
            # handler, so the policy check below still sees it.
            if self.auto_wrap_exceptions:
                from .decorators import wrap_exceptions

                handler = wrap_exceptions(expose_details=self.debug)(handler)

            self.router.add_route(
                self.root_path + path, handler, methods or ["GET"], public=public
            )
            return handler

        return decorator

    def get(self, path: str, *, public: bool = False):
        """GET route decorator"""
        return self.route(path, ["GET"], public=public)

    def post(self, path: str, *, public: bool = False):
        """POST route decorator"""
        return self.route(path, ["POST"], public=public)

    def put(self, path: str, *, public: bool = False):
        """PUT route decorator"""
        return self.route(path, ["PUT"], public=public)

    def delete(self, path: str, *, public: bool = False):
        """DELETE route decorator"""
        return self.route(path, ["DELETE"], public=public)

    def patch(self, path: str, *, public: bool = False):
        """PATCH route decorator"""
        return self.route(path, ["PATCH"], public=public)

    def head(self, path: str, *, public: bool = False):
        """HEAD route decorator"""
        return self.route(path, ["HEAD"], public=public)

    def options(self, path: str, *, public: bool = False):
        """OPTIONS route decorator"""
        return self.route(path, ["OPTIONS"], public=public)

    def include_router(self, prefix: str, router: Router):
        """Include a sub-router with path prefix.

        Routes are re-validated against the app's policy as they are merged, so
        a sub-router built with ``enforce_route_policy=False`` must still declare
        each route ``public=True`` or secured before it can be included into an
        enforcing app - otherwise this raises ``RuntimeError``.
        """
        self.router.include_router(self.root_path + prefix, router)

    def exception_handler(self, status_code: int):
        """Decorator for custom error handlers"""

        def decorator(handler):
            self.error_handlers[status_code] = handler
            return handler

        return decorator

    def middleware(self, middleware_class):
        """Decorator for adding middleware classes"""
        middleware_instance = middleware_class()
        self.middleware_stack.append(middleware_instance)
        return middleware_class

    def add_middleware(self, middleware_instance):
        """Add an already instantiated middleware instance"""
        self.middleware_stack.append(middleware_instance)
        return middleware_instance

    async def _process_request_middleware(self, request: Request):
        """Process request through middleware stack, return response if short-circuited"""
        for middleware in self.middleware_stack:
            result = await middleware.process_request(request)
            if result is not None:
                return result
        return None

    async def _handle_route(self, request: Request):
        """Handle route resolution and execution"""
        handler, path_params = self.router.resolve(request.method, request.path)

        if not handler:
            return Response({"error": "Not found"}, status=404)

        # Add path parameters and call handler
        request.path_params = path_params
        response = await handler(request)

        # Foreign platform responses (Workers-native) pass through untouched
        # for the legacy boundary to convert; the ASGI boundary rejects them.
        if isinstance(response, Response):
            return response
        if is_workers_native_response(response):
            return response

        # Convert dict/string responses to Response objects
        return Response(response)

    async def _process_response_middleware(
        self, request: Request, response: Response
    ) -> Response:
        """Process response through middleware stack"""
        for middleware in reversed(self.middleware_stack):
            response = await middleware.process_response(request, response)
        return response

    def _convert_to_workers_response(self, response):
        """Convert response to Workers format (legacy Worker boundary only)."""
        # Foreign platform responses pass through directly, including a
        # Kinglet Response that merely wraps foreign content.
        if is_workers_native_response(response):
            return response
        if isinstance(response, Response) and is_workers_native_response(
            response.content
        ):
            return response.content

        try:
            return response.to_workers_response()
        except ImportError:
            return response

    async def _render_custom_error(
        self, request, exception: Exception, status_code: int
    ):
        """Render an exception with a custom error handler, if registered.

        Transport-neutral: returns a Kinglet Response, a foreign platform
        response (legacy pass-through), or None when no handler applies.
        Response middleware runs over Kinglet Responses, matching the main
        pipeline; foreign responses return untouched.
        """
        if status_code not in self.error_handlers:
            return None

        try:
            response = await self.error_handlers[status_code](request, exception)
            if is_workers_native_response(response):
                return response

            if not isinstance(response, Response):
                response = Response(response)

            return await self._process_response_middleware(request, response)
        except Exception:
            return None  # Fall through to default handler

    async def _handle_custom_error(
        self, request: Request, exception: Exception, status_code: int
    ):
        """Handle exception with custom error handler (legacy boundary)."""
        rendered = await self._render_custom_error(request, exception, status_code)
        if rendered is None:
            return None
        return self._convert_to_workers_response(rendered)

    def _create_default_error_response(
        self, request: Request, exception: Exception, status_code: int
    ) -> Response:
        """Create default error response"""
        if isinstance(exception, HTTPError):
            error_message = exception.message
        else:
            error_message = str(exception) if self.debug else "Internal server error"

        return Response(
            {
                "error": error_message,
                "status_code": status_code,
                "request_id": getattr(request, "request_id", "unknown"),
            },
            status=status_code,
        )

    async def _dispatch(self, request: Request):
        """Transport-neutral dispatch shared by the Worker and ASGI entries.

        Runs request middleware (with short-circuiting), exact-callable route
        dispatch, response middleware, and the error pipeline over Kinglet
        ``Request``/``Response`` objects. No Workers or ASGI conversion
        happens here; each entry point adapts the result at its boundary.
        Foreign platform responses pass through for the legacy boundary; the
        ASGI boundary rejects them explicitly.
        """
        try:
            # Process middleware (request phase)
            middleware_response = await self._process_request_middleware(request)
            if middleware_response:
                response = middleware_response
            else:
                # Handle route
                response = await self._handle_route(request)

            # Process response middleware
            return await self._process_response_middleware(request, response)
        except Exception as exc:
            return await self._dispatch_error(request, exc)

    async def _dispatch_error(self, request, exception: Exception):
        """Build the error result for a dispatch failure (no conversion)."""
        status_code = getattr(exception, "status_code", 500)

        # Try custom error handler first
        custom_response = await self._render_custom_error(
            request, exception, status_code
        )
        if custom_response is not None:
            return custom_response

        # Default error response
        error_resp = self._create_default_error_response(
            request, exception, status_code
        )
        return await self._process_response_middleware(request, error_resp)

    async def asgi(self, scope, receive, send) -> None:
        """Explicit ASGI callable (ASGI 3 single-callable interface).

        Exposed for both Cloudflare's official ``workers.asgi`` bridge and
        ordinary ASGI servers/test harnesses::

            from application import application  # application = app.asgi

            # worker.py (Cloudflare)
            from workers import asgi
            Default = asgi.entrypoint(application)

            # ordinary server
            # uv run uvicorn application:application

        ``http`` scopes converge on :meth:`_dispatch`, the same core as the
        legacy ``await app(request, env)`` entry point. ``lifespan`` scopes
        receive a correct, inexpensive acknowledgement only: no migrations,
        cache warming or remote reads run at startup, startup is never assumed
        to run once per isolate, and no global "already started" flag is kept
        (the Cloudflare SDK currently runs a lifespan cycle per HTTP request).
        WebSocket and other scope types are rejected explicitly.
        """
        scope_type = scope.get("type", "http") if isinstance(scope, dict) else "http"
        if scope_type == "lifespan":
            await self._handle_lifespan(receive, send)
        elif scope_type == "http":
            await self._handle_asgi_http(scope, receive, send)
        else:
            raise RuntimeError(
                f"Unsupported ASGI scope type {scope_type!r}: Kinglet supports "
                "'http' and 'lifespan' scopes only."
            )

    async def _handle_asgi_http(self, scope, receive, send) -> None:
        """Serve one ASGI HTTP request through the shared dispatch core."""
        request = None
        try:
            request = await Request.from_asgi(scope, receive)
            response = await self._dispatch(request)
        except Exception as exc:
            if request is None:
                request = _FallbackRequest()
            response = await self._dispatch_error(request, exc)
        # Failures from here on mean transmission already started (or the
        # transport is gone): they propagate, never becoming a second response.
        await _send_asgi_response(send, response)

    async def _handle_lifespan(self, receive, send) -> None:
        """Acknowledge ASGI lifespan without inventing lifecycle guarantees.

        Each lifespan is independent: core route/security configuration is
        expected to be valid before serving, and HTTP works whether or not
        the host initiates lifespan. Failures are reported explicitly with
        ``lifespan.startup.failed`` / ``lifespan.shutdown.failed`` rather
        than a bare raise, which some bridges interpret as unsupported
        lifespan and continue past.
        """
        started = False
        try:
            while True:
                message = await receive()
                message_type = (
                    message.get("type") if isinstance(message, dict) else None
                )
                if message_type == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                    started = True
                elif message_type == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
                # Unknown lifespan messages are ignored.
        except Exception as exc:
            failure = {
                "type": (
                    "lifespan.shutdown.failed" if started else "lifespan.startup.failed"
                ),
                "message": str(exc) or repr(exc),
            }
            try:
                await send(failure)
            except Exception:
                # The transport is gone; log rather than swallow silently.
                logger.debug("Failed to report lifespan failure", exc_info=True)

    async def __call__(self, request, env):
        """Legacy Cloudflare Worker entry point: ``await app(request, env)``.

        Preserved for backward compatibility. Wraps the raw request, runs the
        shared :meth:`_dispatch` core, and converts the result to a Workers
        response at this boundary.
        """
        kinglet_request = None
        try:
            # Wrap the raw request
            kinglet_request = Request(request, env)

            # Shared dispatch core, then Workers conversion at the boundary.
            response = await self._dispatch(kinglet_request)
            return self._convert_to_workers_response(response)

        except Exception as e:
            status_code = getattr(e, "status_code", 500)
            if kinglet_request is None:
                kinglet_request = _FallbackRequest()

            # Try custom error handler first
            custom_response = await self._handle_custom_error(
                kinglet_request, e, status_code
            )
            if custom_response:
                return custom_response

            # Default error response
            error_resp = self._create_default_error_response(
                kinglet_request, e, status_code
            )
            error_resp = await self._process_response_middleware(
                kinglet_request, error_resp
            )
            return self._convert_to_workers_response(error_resp)
