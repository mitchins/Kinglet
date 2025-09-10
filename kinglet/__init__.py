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

# Pagination System
from .pagination import (
    CursorPaginator,
    PageInfo,
    PaginatedResult,
    PaginationConfig,
    PaginationMixin,
    Paginator,
    create_pagination_urls,
    paginate_queryset,
)

# Serialization System
from .serializers import (
    FieldTransforms,
    ModelSerializer,
    SerializationContext,
    SerializerConfig,
    SerializerMixin,
    serialize_model,
    serialize_models,
)

# Service Layer Utilities
from .services import (
    BaseService,
    ServiceException,
    ServiceResult,
    ValidationException,
    handle_service_exceptions,
)

# Storage helpers
from .storage import (
    arraybuffer_to_bytes,
    bytes_to_arraybuffer,
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
    cache_aside_d1,
    get_default_cache_policy,
    media_url,
    set_default_cache_policy,
)

# Validation System
from .validation import (
    LISTING_CREATION_SCHEMA,
    USER_LOGIN_SCHEMA,
    USER_REGISTRATION_SCHEMA,
    ChoicesValidator,
    DateValidator,
    EmailValidator,
    LengthValidator,
    PasswordValidator,
    RangeValidator,
    RegexValidator,
    RequiredValidator,
    ValidationResult,
    ValidationSchema,
    Validator,
    validate_email,
    validate_json,
    validate_password,
    validate_required_fields,
    validate_schema,
)

# D1 Cache (optional import)
try:
    from .cache_d1 import (  # noqa: F401
        D1CacheService,
        ensure_cache_table,
        generate_cache_key,
    )

    _d1_available = True
except ImportError:
    _d1_available = False

# Micro-ORM (optional import)
try:
    from .orm import (
        BooleanField,
        DateTimeField,
        Field,
        FloatField,
        IntegerField,
        JSONField,
        Manager,
        Model,
        QuerySet,
        SchemaManager,
        StringField,
    )

    _orm_available = True
except ImportError:
    _orm_available = False

__version__ = "1.7.0"
__author__ = "Mitchell Currie"

# Export commonly used items
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
    # Testing
    "TestClient",
    # Middleware
    "Middleware",
    "CorsMiddleware",
    "TimingMiddleware",
    # Decorators
    "wrap_exceptions",
    "require_dev",
    "geo_restrict",
    "validate_json_body",
    "require_field",
    # Utilities
    "CacheService",
    "cache_aside",
    "cache_aside_d1",
    "asset_url",
    "media_url",
    "EnvironmentCachePolicy",
    "AlwaysCachePolicy",
    "NeverCachePolicy",
    "set_default_cache_policy",
    "get_default_cache_policy",
    # Micro-ORM (conditionally exported if available)
    "Model",
    "Field",
    "StringField",
    "IntegerField",
    "BooleanField",
    "FloatField",
    "DateTimeField",
    "JSONField",
    "QuerySet",
    "Manager",
    "SchemaManager",
    # Service Layer
    "ServiceResult",
    "ServiceException",
    "ValidationException",
    "handle_service_exceptions",
    "BaseService",
    # Serialization
    "ModelSerializer",
    "SerializerConfig",
    "SerializationContext",
    "SerializerMixin",
    "FieldTransforms",
    "serialize_model",
    "serialize_models",
    # Pagination
    "PageInfo",
    "PaginatedResult",
    "PaginationConfig",
    "Paginator",
    "PaginationMixin",
    "CursorPaginator",
    "create_pagination_urls",
    "paginate_queryset",
    # Validation
    "Validator",
    "RequiredValidator",
    "EmailValidator",
    "LengthValidator",
    "RangeValidator",
    "RegexValidator",
    "PasswordValidator",
    "ChoicesValidator",
    "DateValidator",
    "ValidationSchema",
    "ValidationResult",
    "validate_schema",
    "validate_json",
    "validate_email",
    "validate_password",
    "validate_required_fields",
    "USER_REGISTRATION_SCHEMA",
    "USER_LOGIN_SCHEMA",
    "LISTING_CREATION_SCHEMA",
    # Modules
    "authz",
    "totp",
]

# Only export ORM items if they're available
if not _orm_available:
    orm_items = [
        "Model",
        "Field",
        "StringField",
        "IntegerField",
        "BooleanField",
        "FloatField",
        "DateTimeField",
        "JSONField",
        "QuerySet",
        "Manager",
        "SchemaManager",
    ]
    __all__ = [item for item in __all__ if item not in orm_items]
