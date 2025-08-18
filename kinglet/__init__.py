"""
Kinglet - A lightweight routing framework for Python Workers
"""

# Core framework
# Import specialized modules for FGA support and TOTP
from . import authz, totp
from .core import Kinglet, Route, Router

# Decorators
from .decorators import (
    geo_restrict,
    require_dev,
    require_field,
    validate_json_body,
    wrap_exceptions,
)

# Exceptions
from .exceptions import DevOnlyError, GeoRestrictedError, HTTPError

# HTTP primitives
from .http import Request, Response, error_response, generate_request_id

# Middleware
from .middleware import CorsMiddleware, Middleware, TimingMiddleware

# Storage helpers
from .storage import (
    d1_unwrap,
    d1_unwrap_results,
    r2_delete,
    r2_get_content_info,
    r2_get_metadata,
    r2_list,
    r2_put,
)

# Testing utilities
from .testing import TestClient

# Utilities
from .utils import (
    AlwaysCachePolicy,
    CacheService,
    EnvironmentCachePolicy,
    NeverCachePolicy,
    asset_url,
    cache_aside,
    get_default_cache_policy,
    media_url,
    set_default_cache_policy,
)

__version__ = "1.4.3"
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
    "EnvironmentCachePolicy", "AlwaysCachePolicy", "NeverCachePolicy",
    "set_default_cache_policy", "get_default_cache_policy",
    # Modules
    "authz", "totp"
]
