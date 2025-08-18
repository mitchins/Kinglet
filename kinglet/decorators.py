"""
Kinglet Decorators and Utility Functions
"""
import functools
from typing import Callable

from .exceptions import GeoRestrictedError, HTTPError
from .http import Response


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
                    should_expose = getattr(request.env, 'ENVIRONMENT', 'production') == 'development'

                error_message = str(e) if should_expose else "Internal server error"
                prefix = f"[{step}] " if step else ""

                return Response({
                    "error": f"{prefix}{error_message}",
                    "status_code": 500,
                    "request_id": getattr(request, 'request_id', 'unknown')
                }, status=500)
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
        @functools.wraps(handler)
        async def wrapped(request):
            env_name = getattr(request.env, 'ENVIRONMENT', 'production')

            if env_name not in ['development', 'dev', 'test']:
                # Security: In production, make dev endpoints a complete blackhole
                # Return 404 as if the endpoint doesn't exist at all
                from .exceptions import HTTPError
                raise HTTPError(404, "Not Found", getattr(request, 'request_id', None))

            return await handler(request)
        return wrapped
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
        @functools.wraps(handler)
        async def wrapped(request):
            # Get country from Cloudflare header (case-insensitive)
            country = request.header('cf-ipcountry', 'XX').upper()

            # Check blocked list first (takes precedence)
            if blocked and country in [c.upper() for c in blocked]:
                raise GeoRestrictedError(country, allowed, getattr(request, 'request_id', None))

            # Check allowed list
            if allowed and country not in [c.upper() for c in allowed]:
                raise GeoRestrictedError(country, allowed, getattr(request, 'request_id', None))

            return await handler(request)
        return wrapped
    return decorator


def validate_json_body(handler: Callable):
    """Decorator to validate that request has valid JSON body"""
    @functools.wraps(handler)
    async def wrapped(request):
        try:
            body = await request.json()
            # Check for None or empty dict (both considered "empty" for validation)
            if body is None or body == {}:
                return Response.error("Request body cannot be empty", 400, request.request_id)
        except Exception as e:
            return Response.error(f"Invalid JSON: {str(e)}", 400, request.request_id)

        return await handler(request)
    return wrapped


def require_field(field_name: str, field_type: type = str):
    """
    Decorator to validate that JSON body contains required field
    
    Args:
        field_name: Name of required field
        field_type: Expected type of field (str, int, bool, etc.)
    """
    def decorator(handler: Callable):
        @functools.wraps(handler)
        async def wrapped(request):
            try:
                body = await request.json()
                if body is None or field_name not in body:
                    return Response.error(f"Missing required field: {field_name}", 400, request.request_id)

                value = body[field_name]
                if not isinstance(value, field_type):
                    return Response.error(
                        f"Field '{field_name}' must be of type {field_type.__name__}",
                        400,
                        request.request_id
                    )

            except Exception as e:
                return Response.error(f"Invalid request: {str(e)}", 400, request.request_id)

            return await handler(request)
        return wrapped
    return decorator
