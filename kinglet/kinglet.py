"""
Kinglet - A lightweight routing framework for Python Workers
Modular version with clean separation of concerns
"""

# Re-export core components for backward compatibility
from .core import Kinglet, Route, Router
from .decorators import (
    geo_restrict,
    require_dev,
    require_field,
    validate_json_body,
    wrap_exceptions,
)
from .exceptions import DevOnlyError, GeoRestrictedError, HTTPError
from .http import Request, Response, error_response, generate_request_id
from .middleware import CorsMiddleware, Middleware, TimingMiddleware
from .storage import (
    d1_unwrap,
    d1_unwrap_results,
    r2_delete,
    r2_get_content_info,
    r2_get_metadata,
    r2_list,
    r2_put,
)
from .testing import TestClient

__version__ = "1.4.2"
__author__ = "Mitchell Currie"

# For backward compatibility - export everything that was in the original kinglet.py
__all__ = [
    # Core
    "Kinglet", "Router", "Route",
    # HTTP
    "Request", "Response", "error_response", "generate_request_id",
    # Exceptions
    "HTTPError", "GeoRestrictedError", "DevOnlyError",
    # Storage
    "d1_unwrap", "d1_unwrap_results",
    "r2_get_metadata", "r2_get_content_info", "r2_put", "r2_delete", "r2_list",
    # Testing
    "TestClient",
    # Middleware
    "Middleware", "CorsMiddleware", "TimingMiddleware",
    # Decorators
    "wrap_exceptions", "require_dev", "geo_restrict", "validate_json_body", "require_field"
]
