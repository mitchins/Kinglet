"""
Kinglet Decorators and Utility Functions
"""

import contextlib
import functools
import json
import weakref
from collections.abc import Callable

from .exceptions import GeoRestrictedError, HTTPError
from .http import Response

# Attribute set on every callable registered with a route. Security decorators
# use it to fail closed when applied in an order that cannot protect the route.
ROUTE_REGISTERED_ATTR = "__kinglet_route_registered__"

# Fallback registry for callables that cannot carry attributes (bound methods,
# functools.partial, ...). Weak references: entries vanish when the registered
# handler is garbage collected. Bound methods are ephemeral objects but hash
# and compare by (instance, function), so a fresh `obj.method` reference still
# matches the one the route registered.
_UNMARKABLE_ROUTE_HANDLERS: weakref.WeakSet = weakref.WeakSet()


def mark_route_registered(handler: Callable) -> Callable:
    """Mark a callable as registered with a route.

    Callables that reject attribute assignment are tracked in a weak registry
    instead, so the decorator-order guard still detects them.
    """
    try:
        setattr(handler, ROUTE_REGISTERED_ATTR, True)
    except (AttributeError, TypeError):
        # Not weakref-able or not hashable: best effort ends here.
        with contextlib.suppress(TypeError):
            _UNMARKABLE_ROUTE_HANDLERS.add(handler)
    return handler


def is_route_registered(handler: Callable) -> bool:
    """Return True if the callable was already registered with a route."""
    if getattr(handler, ROUTE_REGISTERED_ATTR, False):
        return True
    try:
        return handler in _UNMARKABLE_ROUTE_HANDLERS
    except TypeError:  # unhashable callable
        return False


def reject_if_route_registered(handler: Callable, decorator_name: str) -> None:
    """Fail closed when a security decorator is applied above a route decorator.

    Once a callable is registered, the route executes exactly that callable;
    wrapping it afterwards produces a wrapper the route never calls, silently
    leaving the route unprotected. Raise loudly instead.
    """
    if is_route_registered(handler):
        raise RuntimeError(
            f"@{decorator_name} was applied above/outside a route decorator. "
            f"The route has already been registered and would execute without "
            f"this protection. Apply the route decorator outermost:\n\n"
            f"    @app.get('/path')\n"
            f"    @{decorator_name}\n"
            f"    async def handler(request): ...\n"
        )


# ---------------------------------------------------------------------------
# Route security policy: default-deny route registration
#
# Under enforce_route_policy (default in 2.0), a route may only be registered
# if it is explicitly declared public (``public=True``) or its handler carries
# a recognized access-control marker. This makes the reversed-order custom
# decorator bypass fail closed *by default*, without any module/global name
# lookup: at registration time the handler is simply inspected for the marker.
# ---------------------------------------------------------------------------

# Set on the wrapper produced by a recognized access-control decorator. Stored
# as a normal function attribute so it lives in ``__dict__`` and therefore
# propagates outward through ``functools.wraps`` when decorators are stacked.
SECURED_ATTR = "__kinglet_secured__"

# Fallback registry for secured callables that cannot carry attributes.
_UNMARKABLE_SECURED_HANDLERS: weakref.WeakSet = weakref.WeakSet()


def mark_secured(handler: Callable) -> Callable:
    """Mark a callable as carrying an access-control posture.

    Recognized built-in access decorators call this on their wrapper, and
    :func:`security_decorator` calls it for custom decorators. The route
    policy then accepts the route without requiring ``public=True``.
    """
    try:
        setattr(handler, SECURED_ATTR, True)
    except (AttributeError, TypeError):
        with contextlib.suppress(TypeError):
            _UNMARKABLE_SECURED_HANDLERS.add(handler)
    return handler


def is_secured(handler: Callable) -> bool:
    """Return True if the callable carries a recognized access-control marker."""
    if getattr(handler, SECURED_ATTR, False):
        return True
    try:
        return handler in _UNMARKABLE_SECURED_HANDLERS
    except TypeError:
        return False


def security_decorator(decorator_fn: Callable) -> Callable:
    """Make a custom security decorator Kinglet-aware.

    Wrap your own access-control decorator so its output is recognized by the
    default-deny route policy and so applying it in reversed order fails fast::

        @security_decorator
        def require_admin(handler):
            @functools.wraps(handler)
            async def wrapped(request):
                ...
            return wrapped

        @app.get("/admin")   # correct order: enforced
        @require_admin
        async def admin(request): ...

        @require_admin        # reversed order: RuntimeError at import
        @app.get("/admin")
        async def admin(request): ...
    """

    @functools.wraps(decorator_fn)
    def aware_decorator(handler: Callable) -> Callable:
        reject_if_route_registered(
            handler, getattr(decorator_fn, "__name__", "decorator")
        )
        wrapped = decorator_fn(handler)
        return mark_secured(wrapped)

    return aware_decorator


def assert_route_security(handler: Callable, *, public: bool, path: str = "") -> None:
    """Fail closed if a route is neither explicitly public nor secured.

    Called at route registration. Deterministic: it only inspects the handler
    that will actually be dispatched - no module scanning, name lookup, or
    closure inspection.
    """
    if public or is_secured(handler):
        return
    where = f" for {path!r}" if path else ""
    raise RuntimeError(
        f"Route{where} has no declared security posture. Under the default "
        f"route policy every route must be explicitly public or protected by "
        f"a recognized access-control decorator.\n\n"
        f"  - Public endpoint:    @app.get('/path', public=True)\n"
        f"  - Built-in auth:      @app.get('/path')\n"
        f"                        @require_auth   # (route decorator outermost)\n"
        f"  - Custom decorator:   wrap it with @security_decorator so Kinglet\n"
        f"                        recognizes it as access control.\n\n"
        f"To opt out during migration: Kinglet(enforce_route_policy=False)."
    )


def wrap_exceptions(step: str = None, expose_details: bool = None):
    """
    Decorator to automatically wrap exceptions in standardized error responses.

    Args:
        step: Optional step name for debugging (e.g., "validation", "database")
        expose_details: Whether to expose exception details. If None, uses app debug setting.
    """

    def decorator(handler):
        @functools.wraps(handler)
        async def wrapped(request):
            try:
                return await handler(request)
            except HTTPError:
                # Re-raise HTTP errors as-is (already properly formatted)
                raise
            except Exception as e:
                # Determine if we should expose details
                should_expose = expose_details
                if should_expose is None:
                    # Fall back to checking request environment or app debug setting
                    should_expose = (
                        getattr(request.env, "ENVIRONMENT", "production")
                        == "development"
                    )

                error_message = str(e) if should_expose else "Internal server error"
                prefix = f"[{step}] " if step else ""

                return Response(
                    {
                        "error": f"{prefix}{error_message}",
                        "status_code": 500,
                        "request_id": getattr(request, "request_id", "unknown"),
                    },
                    status=500,
                )

        return wrapped

    return decorator


def require_dev():
    """
    Decorator to restrict endpoint to development environments only.

    Usage:
        @app.get("/admin/debug")
        @require_dev()
        async def debug_endpoint(request):
            return {"debug_info": "sensitive data"}
    """

    def decorator(handler: Callable):
        reject_if_route_registered(handler, "require_dev()")

        @functools.wraps(handler)
        async def wrapped(request):
            env_name = str(getattr(request.env, "ENVIRONMENT", "production")).lower()

            if env_name not in ["development", "dev", "test"]:
                # Security: In production, make dev endpoints a complete blackhole
                # Return 404 as if the endpoint doesn't exist at all
                from .exceptions import HTTPError

                raise HTTPError(404, "Not Found", getattr(request, "request_id", None))

            return await handler(request)

        return mark_secured(wrapped)

    return decorator


def geo_restrict(*, allowed: list = None, blocked: list = None):
    """
    Decorator to restrict access based on country codes

    Args:
        allowed: List of allowed country codes (2-letter ISO)
        blocked: List of blocked country codes (2-letter ISO)

    Note: blocked takes precedence over allowed
    """

    def decorator(handler: Callable):
        reject_if_route_registered(handler, "geo_restrict(...)")

        @functools.wraps(handler)
        async def wrapped(request):
            # Get country from Cloudflare header (case-insensitive)
            country = request.header("cf-ipcountry", "XX").upper()

            # Check blocked list first (takes precedence)
            if blocked and country in [c.upper() for c in blocked]:
                raise GeoRestrictedError(
                    country, allowed, getattr(request, "request_id", None)
                )

            # Check allowed list
            if allowed and country not in [c.upper() for c in allowed]:
                raise GeoRestrictedError(
                    country, allowed, getattr(request, "request_id", None)
                )

            return await handler(request)

        return mark_secured(wrapped)

    return decorator


def validate_json_body(handler: Callable):
    """Decorator to validate that request has valid JSON body"""
    reject_if_route_registered(handler, "validate_json_body")

    @functools.wraps(handler)
    async def wrapped(request):
        try:
            raw_text = await request.text()
            stripped = raw_text.strip() if raw_text else ""
            if stripped == "":
                return Response.error(
                    "Request body cannot be empty", 400, request.request_id
                )
            if stripped == "null":
                return await handler(request)

            body = await request.json()
            if body is None:
                try:
                    body = json.loads(stripped)
                except json.JSONDecodeError:
                    return Response.error("Invalid JSON body", 400, request.request_id)
            if body == {}:
                return Response.error(
                    "Request body cannot be empty", 400, request.request_id
                )
        except Exception:
            return Response.error("Invalid JSON body", 400, request.request_id)

        return await handler(request)

    return wrapped


def require_field(field_name: str, field_type: type | tuple[type, ...] = str):
    """
    Decorator to validate that JSON body contains required field

    Args:
        field_name: Name of required field
        field_type: Expected type of field (str, int, bool, etc.)
    """

    def decorator(handler: Callable):
        reject_if_route_registered(handler, f"require_field({field_name!r})")

        @functools.wraps(handler)
        async def wrapped(request):
            try:
                body = await request.json()
                if body is None or field_name not in body:
                    return Response.error(
                        f"Missing required field: {field_name}", 400, request.request_id
                    )

                value = body[field_name]
                if not isinstance(value, field_type):
                    type_names = (
                        " or ".join(t.__name__ for t in field_type)
                        if isinstance(field_type, tuple)
                        else field_type.__name__
                    )
                    return Response.error(
                        f"Field '{field_name}' must be of type {type_names}",
                        400,
                        request.request_id,
                    )

            except Exception as e:
                return Response.error(
                    f"Invalid request: {str(e)}", 400, request.request_id
                )

            return await handler(request)

        return wrapped

    return decorator
