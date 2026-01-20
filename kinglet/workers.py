"""
Kinglet Workers - Minimal import alias for Cloudflare Workers

This module is a convenience alias. The main `kinglet` module now uses lazy
loading, so you can simply use:

    from kinglet import Kinglet, Request, Response, Router

Heavy modules (ORM, Testing, Pagination, Serializers, Validation) are only
loaded when first accessed, providing the same cold start optimization.

For absolute minimal imports (avoiding even the lazy-loading __getattr__),
import directly from submodules:

    from kinglet.core import Kinglet, Router
    from kinglet.http import Request, Response
    from kinglet.storage import d1_unwrap
"""

# Re-export from main module (which now uses lazy loading)
from . import (
    DevOnlyError,
    GeoRestrictedError,
    HTTPError,
    Kinglet,
    Request,
    Response,
    Route,
    Router,
    arraybuffer_to_bytes,
    bytes_to_arraybuffer,
    d1_unwrap,
    d1_unwrap_results,
    error_response,
    generate_request_id,
    r2_delete,
    r2_get_content_info,
    r2_get_metadata,
    r2_list,
    r2_put,
)

__all__ = [
    # Core
    "Kinglet",
    "Router",
    "Route",
    # HTTP
    "Request",
    "Response",
    "error_response",
    "generate_request_id",
    # Exceptions
    "HTTPError",
    "GeoRestrictedError",
    "DevOnlyError",
    # Storage
    "d1_unwrap",
    "d1_unwrap_results",
    "r2_get_metadata",
    "r2_get_content_info",
    "r2_put",
    "r2_delete",
    "r2_list",
    "bytes_to_arraybuffer",
    "arraybuffer_to_bytes",
]
