"""
Kinglet - A lightweight routing framework for Python Workers
"""

# Core framework
from .core import Kinglet, Router, Route

# HTTP primitives
from .http import Request, Response, error_response, generate_request_id

# Exceptions
from .exceptions import HTTPError, GeoRestrictedError, DevOnlyError

# Storage helpers
from .storage import (
    d1_unwrap, d1_unwrap_results,
    r2_get_metadata, r2_get_content_info, r2_put, r2_delete, r2_list
)

# Testing utilities
from .testing import TestClient

# Middleware
from .middleware import Middleware, CorsMiddleware, TimingMiddleware

# Decorators
from .decorators import wrap_exceptions, require_dev, geo_restrict, validate_json_body, require_field

# Utilities
from .utils import CacheService, cache_aside, asset_url, media_url

# Import specialized modules for FGA support and TOTP
from . import authz
from . import totp

__version__ = "1.4.2"
__author__ = "Mitchell Currie"

# Export commonly used items
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
    "wrap_exceptions", "require_dev", "geo_restrict", "validate_json_body", "require_field",
    # Utilities
    "CacheService", "cache_aside", "asset_url", "media_url",
    # Modules
    "authz", "totp"
]