"""
Kinglet Decorators and Utility Functions
"""

import functools
import json
import warnings
import weakref
from collections.abc import Callable

from .exceptions import GeoRestrictedError, HTTPError
from .http import Response

# Registry of callables registered to a route, used by the decorator-order
# guard. A WeakSet (value-equality membership) so a fresh access of a registered
# bound method still matches via (instance, function) equality. Crucially,
# WeakSet membership is NOT copied by functools.wraps - unlike a function
# attribute, which wraps copies into outer wrappers and which previously made
# the order guard reject a wrapper that merely inherited the copied attribute.
#
# Contrast _SECURED_HANDLERS, which must use STRICT identity to stop value-
# equality laundering of the auth posture. Here value-equality is fine: it only
# ever over-triggers the fail-loud order guard (never a bypass), so matching a
# fresh bound-method access is the desired behaviour.
_ROUTE_REGISTERED_HANDLERS: weakref.WeakSet = weakref.WeakSet()


def mark_route_registered(handler: Callable) -> Callable:
    """Mark a callable as registered with a route.

    Membership is held weakly and is not propagated by functools.wraps, so the
    decorator-order guard recognizes exactly the registered callables (and fresh
    accesses of registered bound methods) without false positives from wrapping.
    """
    try:
        _ROUTE_REGISTERED_HANDLERS.add(handler)
    except TypeError:
        # Not weakref-able / not hashable: cannot be tracked, so the
        # decorator-order guard is skipped for this callable. Surface it for
        # consistency with mark_secured (still fail-loud only - never a bypass).
        warnings.warn(
            f"mark_route_registered: {handler!r} is not trackable; the "
            f"decorator-order guard is skipped for this callable.",
            RoutePolicyWarning,
            stacklevel=2,
        )
    return handler


def is_route_registered(handler: Callable) -> bool:
    """Return True if the callable was already registered with a route."""
    try:
        return handler in _ROUTE_REGISTERED_HANDLERS
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


class RoutePolicyWarning(UserWarning):
    """Emitted when the default-deny route policy is disabled.

    Disabling enforcement removes a framework-level guard against accidentally
    unprotected routes; the warning leaves an audit signal so an intentional
    opt-out is not mistaken for one forgotten during migration.
    """


# Registry of callables that a recognized access-control decorator actually
# produced. Keyed by ``id()`` and verified with ``is``, so membership is by true
# OBJECT IDENTITY - never value equality. This matters twice:
#
#   * ``functools.wraps`` copies ``__dict__`` and a few dunders but not registry
#     identity, so an unrelated outer wrapper (e.g. a short-circuiting cache /
#     maintenance / feature-flag decorator) cannot launder the "secured" posture
#     onto itself and bypass auth.
#   * A plain ``WeakSet`` would use the element's ``__eq__``/``__hash__``, so a
#     distinct callable that merely *compares equal* to a marked one (a callable
#     class with value-based equality, a bound method, ...) would pass the check
#     unmarked. Id-keying + an ``is`` check accepts only the exact object.
#
# Values are held weakly so entries die with the callable; the ``is`` check also
# guards against id reuse after garbage collection. The check runs synchronously
# at registration while the route holds a strong reference, so liveness is never
# a concern at check time.
_SECURED_HANDLERS: weakref.WeakValueDictionary = weakref.WeakValueDictionary()


def mark_secured(handler: Callable) -> Callable:
    """Mark a callable as carrying an access-control posture.

    Recognized built-in access decorators call this on their wrapper, and
    :func:`security_decorator` calls it for custom decorators. The route
    policy then accepts the route without requiring ``public=True``.

    The mark is recorded by object **identity** (not value or a copyable
    attribute), so wrapping the result in an unrelated decorator does NOT carry
    the posture across - the wrapper must enforce (or re-mark) auth itself. Two
    consequences for callers:

    - **Bound methods**: ``obj.method`` creates a NEW object on each access, so
      ``mark_secured(obj.method)`` marks one object while a later ``obj.method``
      is a different one that is not secured. Capture the reference once and
      pass the SAME object to both ``mark_secured`` and route registration::

          handler = controller.action
          mark_secured(handler)
          router.add_route("/x", handler, ["GET"])

    - **Non-weakref-able callables** cannot be tracked: the mark is skipped (a
      :class:`RoutePolicyWarning` is emitted) and the route must instead be
      declared ``public=True``. This fails closed.
    """
    try:
        _SECURED_HANDLERS[id(handler)] = handler
    except TypeError:
        # Not weakref-able (exotic callable): cannot be marked, so it is treated
        # as unsecured and the route must be declared public=True. Fail closed,
        # but surface it so the later "no security posture" error is not a
        # mystery.
        warnings.warn(
            f"mark_secured: {handler!r} is not weakref-able and cannot be "
            f"tracked as secured; the route must be declared public=True.",
            RoutePolicyWarning,
            stacklevel=2,
        )
    return handler


def is_secured(handler: Callable) -> bool:
    """Return True if this exact callable was produced by a recognized decorator."""
    return _SECURED_HANDLERS.get(id(handler)) is handler


def security_decorator(decorator_fn: Callable) -> Callable:
    """Make a custom *simple* security decorator Kinglet-aware.

    A simple decorator has the shape ``def deco(handler) -> wrapped``. Wrapping
    it with ``@security_decorator`` makes its output satisfy the default-deny
    route policy and makes reversed decorator order fail fast::

        @security_decorator
        def require_admin(handler):
            @functools.wraps(handler)
            async def wrapped(request): ...
            return wrapped

        @app.get("/admin")   # correct order: enforced
        @require_admin
        async def admin(request): ...

        @require_admin        # reversed order: RuntimeError at import
        @app.get("/admin")
        async def admin(request): ...

    **Parameterized factories** (``def require_role(role) -> deco -> wrapped``)
    take an argument, so they are NOT simple decorators. Apply
    ``@security_decorator`` to the *inner* decorator the factory returns, not to
    the factory itself::

        def require_role(role):
            @security_decorator
            def deco(handler):
                @functools.wraps(handler)
                async def wrapped(request): ...
                return wrapped
            return deco

        @app.get("/admin")
        @require_role("admin")   # works: the inner deco is the secured one
        async def admin(request): ...

    Applying ``@security_decorator`` directly to a factory is rejected at call
    time with a ``TypeError`` (rather than silently mis-marking the factory
    instead of the handler, which would leave the route unprotected).
    """

    @functools.wraps(decorator_fn)
    def aware_decorator(handler: Callable) -> Callable:
        if not callable(handler):
            raise TypeError(
                f"@security_decorator expects a simple decorator "
                f"`def {getattr(decorator_fn, '__name__', 'deco')}(handler): ...`, "
                f"but it was invoked with a non-callable argument {handler!r}. "
                f"This usually means it was applied to a decorator FACTORY "
                f"(e.g. require_role('admin')). Apply @security_decorator to the "
                f"INNER decorator the factory returns instead - see its docstring."
            )
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
    name = getattr(handler, "__name__", None) or repr(handler)
    raise RuntimeError(
        f"Route{where} (handler {name!r}) has no declared security posture. "
        f"Under the default route policy every route must be explicitly public "
        f"or protected by a recognized access-control decorator. If {name!r} is "
        f"protected by a custom decorator, that decorator must be wrapped with "
        f"@security_decorator to be recognized.\n\n"
        f"  - Public endpoint:    @app.get('/path', public=True)\n"
        f"  - Built-in auth:      @app.get('/path')\n"
        f"                        @require_auth   # (route decorator outermost)\n"
        f"  - Custom decorator:   wrap it with @security_decorator so Kinglet\n"
        f"                        recognizes it as access control.\n\n"
        f"Note: geo_restrict is a network filter, not an identity check - a\n"
        f"geo-restricted route still needs public=True or a real auth decorator.\n\n"
        f"To opt out during migration: Kinglet(enforce_route_policy=False)."
    )


def _should_expose_details(request, expose_details: bool | None) -> bool:
    """Resolve whether exception detail should be exposed in the response."""
    if expose_details is not None:
        return expose_details
    # Fall back to the request environment / app debug setting.
    return getattr(request.env, "ENVIRONMENT", "production") == "development"


def _exception_error_response(exc: Exception, request, step, expose_details):
    """Build the standardized 500 response for a handler exception."""
    error_message = (
        str(exc)
        if _should_expose_details(request, expose_details)
        else ("Internal server error")
    )
    prefix = f"[{step}] " if step else ""
    return Response(
        {
            "error": f"{prefix}{error_message}",
            "status_code": 500,
            "request_id": getattr(request, "request_id", "unknown"),
        },
        status=500,
    )


def wrap_exceptions(step: str = None, expose_details: bool = None):
    """
    Decorator to automatically wrap exceptions in standardized error responses.

    Args:
        step: Optional step name for debugging (e.g., "validation", "database")
        expose_details: Whether to expose exception details. If None, uses app debug setting.
    """

    def decorator(handler):
        # wrap_exceptions is framework-applied, transparent infrastructure: it
        # ALWAYS calls the inner handler (try/except around it), so it cannot
        # hide an access check. It must therefore preserve the inner handler's
        # security posture - otherwise auto-wrapping every route would strip the
        # marker and break auth'd routes. Capture it before wrapping and re-mark
        # by identity. (An ordinary user decorator is NOT trusted this way - only
        # this provably-transparent wrapper is.)
        inner_secured = is_secured(handler)

        @functools.wraps(handler)
        async def wrapped(request):
            try:
                return await handler(request)
            except HTTPError:
                # Re-raise HTTP errors as-is (already properly formatted)
                raise
            except Exception as e:
                return _exception_error_response(e, request, step, expose_details)

        if inner_secured:
            mark_secured(wrapped)
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
                # (HTTPError is imported at module top.)
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

        # Deliberately NOT mark_secured: geo-restriction is a forgeable
        # network-layer hint (CF-IPCountry; bypassable via VPN or off-Cloudflare
        # header spoofing), not an identity/authorization control. It fails OPEN
        # in production, so it cannot by itself satisfy the route security
        # policy. A geo-restricted route must also be public=True or carry a
        # real auth decorator. (Contrast require_dev, which fails CLOSED -> 404
        # in production - and so does mark the route secured.)
        return wrapped

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
