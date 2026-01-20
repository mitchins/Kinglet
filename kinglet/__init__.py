"""
Kinglet - A lightweight routing framework for Python Workers

Cold Start Optimization: Heavy modules (ORM, testing, serializers, pagination,
validation schemas) are lazy-loaded via __getattr__ to reduce Workers cold start.
"""

from typing import TYPE_CHECKING

# =============================================================================
# EAGER IMPORTS - Core framework essentials (always needed, fast to load)
# =============================================================================
# Core framework - minimal, always needed
from .core import Kinglet, Route, Router

# Decorators - small, commonly used
from .decorators import (
    geo_restrict,
    require_dev,
    require_field,
    validate_json_body,
    wrap_exceptions,
)

# Exceptions - minimal, always needed
from .exceptions import DevOnlyError, GeoRestrictedError, HTTPError

# HTTP primitives - minimal, always needed
from .http import Request, Response, error_response, generate_request_id

# Middleware - small, commonly used
from .middleware import CorsMiddleware, Middleware, TimingMiddleware

# Service Layer - commonly used
from .services import (
    BaseService,
    ServiceException,
    ServiceResult,
    ValidationException,
    handle_service_exceptions,
)

# Storage helpers - minimal, commonly needed for D1/R2
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

# Utilities - cache helpers are commonly used
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

# =============================================================================
# TYPE CHECKING IMPORTS - For static analysis only, no runtime cost
# =============================================================================

if TYPE_CHECKING:
    # ORM types
    # Specialized modules
    from . import authz, ses, totp

    # D1 Cache types
    from .cache_d1 import (  # noqa: F401
        D1CacheService,
        ensure_cache_table,
        generate_cache_key,
    )

    # OpenAPI types
    from .openapi import SchemaGenerator
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

    # Pagination types
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

    # Serialization types
    from .serializers import (
        FieldTransforms,
        ModelSerializer,
        SerializationContext,
        SerializerConfig,
        SerializerMixin,
        serialize_model,
        serialize_models,
    )

    # Testing types
    from .testing import (
        D1DatabaseError,
        D1ExecResult,
        D1MockError,
        D1PreparedStatementError,
        D1Result,
        D1ResultMeta,
        EmailMockError,
        MockD1Database,
        MockD1PreparedStatement,
        MockEmailSender,
        MockR2Bucket,
        MockR2Object,
        MockR2ObjectBody,
        MockSentEmail,
        R2MockError,
        R2MultipartAbortedError,
        R2MultipartCompletedError,
        R2MultipartUploadError,
        R2PartNotFoundError,
        R2TooManyKeysError,
        TestClient,
    )

    # Validation types
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

# =============================================================================
# LAZY LOADING INFRASTRUCTURE
# =============================================================================

# Module caches for lazy loading (avoid repeated imports)
_lazy_module_cache: dict = {}

# Availability flags (set on first access)
_orm_available: bool | None = None
_d1_available: bool | None = None
_openapi_available: bool | None = None

# Mapping of lazy-loaded attributes to their module and import name
_LAZY_IMPORTS = {
    # ORM (orm.py - 1,722 lines, heavy metaclass setup)
    "Model": ("orm", "Model"),
    "Field": ("orm", "Field"),
    "StringField": ("orm", "StringField"),
    "IntegerField": ("orm", "IntegerField"),
    "BooleanField": ("orm", "BooleanField"),
    "FloatField": ("orm", "FloatField"),
    "DateTimeField": ("orm", "DateTimeField"),
    "JSONField": ("orm", "JSONField"),
    "QuerySet": ("orm", "QuerySet"),
    "Manager": ("orm", "Manager"),
    "SchemaManager": ("orm", "SchemaManager"),
    # Testing (testing.py - 1,778 lines, mock classes with sqlite)
    "TestClient": ("testing", "TestClient"),
    "MockD1Database": ("testing", "MockD1Database"),
    "MockD1PreparedStatement": ("testing", "MockD1PreparedStatement"),
    "D1Result": ("testing", "D1Result"),
    "D1ResultMeta": ("testing", "D1ResultMeta"),
    "D1ExecResult": ("testing", "D1ExecResult"),
    "D1MockError": ("testing", "D1MockError"),
    "D1DatabaseError": ("testing", "D1DatabaseError"),
    "D1PreparedStatementError": ("testing", "D1PreparedStatementError"),
    "MockR2Bucket": ("testing", "MockR2Bucket"),
    "MockR2Object": ("testing", "MockR2Object"),
    "MockR2ObjectBody": ("testing", "MockR2ObjectBody"),
    "R2MockError": ("testing", "R2MockError"),
    "R2MultipartAbortedError": ("testing", "R2MultipartAbortedError"),
    "R2MultipartCompletedError": ("testing", "R2MultipartCompletedError"),
    "R2MultipartUploadError": ("testing", "R2MultipartUploadError"),
    "R2PartNotFoundError": ("testing", "R2PartNotFoundError"),
    "R2TooManyKeysError": ("testing", "R2TooManyKeysError"),
    "MockEmailSender": ("testing", "MockEmailSender"),
    "MockSentEmail": ("testing", "MockSentEmail"),
    "EmailMockError": ("testing", "EmailMockError"),
    # Pagination (pagination.py - moderate size)
    "PageInfo": ("pagination", "PageInfo"),
    "PaginatedResult": ("pagination", "PaginatedResult"),
    "PaginationConfig": ("pagination", "PaginationConfig"),
    "Paginator": ("pagination", "Paginator"),
    "PaginationMixin": ("pagination", "PaginationMixin"),
    "CursorPaginator": ("pagination", "CursorPaginator"),
    "create_pagination_urls": ("pagination", "create_pagination_urls"),
    "paginate_queryset": ("pagination", "paginate_queryset"),
    # Serialization (serializers.py - moderate size)
    "ModelSerializer": ("serializers", "ModelSerializer"),
    "SerializerConfig": ("serializers", "SerializerConfig"),
    "SerializationContext": ("serializers", "SerializationContext"),
    "SerializerMixin": ("serializers", "SerializerMixin"),
    "FieldTransforms": ("serializers", "FieldTransforms"),
    "serialize_model": ("serializers", "serialize_model"),
    "serialize_models": ("serializers", "serialize_models"),
    # Validation (validation.py - 518 lines, schema compilation)
    "Validator": ("validation", "Validator"),
    "RequiredValidator": ("validation", "RequiredValidator"),
    "EmailValidator": ("validation", "EmailValidator"),
    "LengthValidator": ("validation", "LengthValidator"),
    "RangeValidator": ("validation", "RangeValidator"),
    "RegexValidator": ("validation", "RegexValidator"),
    "PasswordValidator": ("validation", "PasswordValidator"),
    "ChoicesValidator": ("validation", "ChoicesValidator"),
    "DateValidator": ("validation", "DateValidator"),
    "ValidationSchema": ("validation", "ValidationSchema"),
    "ValidationResult": ("validation", "ValidationResult"),
    "validate_schema": ("validation", "validate_schema"),
    "validate_json": ("validation", "validate_json"),
    "validate_email": ("validation", "validate_email"),
    "validate_password": ("validation", "validate_password"),
    "validate_required_fields": ("validation", "validate_required_fields"),
    # Pre-built validation schemas (defer compilation)
    "USER_REGISTRATION_SCHEMA": ("validation", "USER_REGISTRATION_SCHEMA"),
    "USER_LOGIN_SCHEMA": ("validation", "USER_LOGIN_SCHEMA"),
    "LISTING_CREATION_SCHEMA": ("validation", "LISTING_CREATION_SCHEMA"),
    # D1 Cache (optional)
    "D1CacheService": ("cache_d1", "D1CacheService"),
    "ensure_cache_table": ("cache_d1", "ensure_cache_table"),
    "generate_cache_key": ("cache_d1", "generate_cache_key"),
    # OpenAPI (optional, requires ORM)
    "SchemaGenerator": ("openapi", "SchemaGenerator"),
    # Specialized modules (import as modules)
    "authz": (None, "authz"),
    "ses": (None, "ses"),
    "totp": (None, "totp"),
}


def _import_module(module_name: str):
    """Import a submodule and cache it."""
    if module_name not in _lazy_module_cache:
        import importlib

        _lazy_module_cache[module_name] = importlib.import_module(
            f".{module_name}", __name__
        )
    return _lazy_module_cache[module_name]


def __getattr__(name: str):
    """
    Lazy-load heavy modules on first access.

    This reduces cold start time by deferring imports of:
    - ORM (~1,722 lines with metaclass setup)
    - Testing (~1,778 lines with SQLite mocks)
    - Pagination, Serialization, Validation
    """
    global _orm_available, _d1_available, _openapi_available

    if name in _LAZY_IMPORTS:
        module_name, attr_name = _LAZY_IMPORTS[name]

        # Handle module imports (authz, ses, totp)
        if module_name is None:
            return _import_module(attr_name)

        # Handle attribute imports from modules
        try:
            module = _import_module(module_name)
            attr = getattr(module, attr_name)

            # Cache in globals for subsequent fast access
            globals()[name] = attr
            return attr
        except ImportError as e:
            # Track availability for optional modules
            if module_name == "orm":
                _orm_available = False
            elif module_name == "cache_d1":
                _d1_available = False
            elif module_name == "openapi":
                _openapi_available = False
            raise AttributeError(
                f"module 'kinglet' has no attribute '{name}' "
                f"(optional module '{module_name}' not available)"
            ) from e

    raise AttributeError(f"module 'kinglet' has no attribute '{name}'")


def __dir__():
    """Include lazy-loaded attributes in dir() output."""
    return list(globals().keys()) + list(_LAZY_IMPORTS.keys())


# =============================================================================
# VERSION AND METADATA
# =============================================================================

__version__ = "1.8.3"
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
    # Testing - D1 Mock (lazy-loaded)
    "MockD1Database",
    "MockD1PreparedStatement",
    "D1Result",
    "D1ResultMeta",
    "D1ExecResult",
    "D1MockError",
    "D1DatabaseError",
    "D1PreparedStatementError",
    # Testing - R2 Mock (lazy-loaded)
    "TestClient",
    "MockR2Bucket",
    "MockR2Object",
    "MockR2ObjectBody",
    "R2MockError",
    "R2MultipartAbortedError",
    "R2MultipartCompletedError",
    "R2MultipartUploadError",
    "R2PartNotFoundError",
    "R2TooManyKeysError",
    # Testing - Email Mock (lazy-loaded)
    "MockEmailSender",
    "MockSentEmail",
    "EmailMockError",
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
    # Micro-ORM (lazy-loaded, conditionally exported if available)
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
    # Serialization (lazy-loaded)
    "ModelSerializer",
    "SerializerConfig",
    "SerializationContext",
    "SerializerMixin",
    "FieldTransforms",
    "serialize_model",
    "serialize_models",
    # Pagination (lazy-loaded)
    "PageInfo",
    "PaginatedResult",
    "PaginationConfig",
    "Paginator",
    "PaginationMixin",
    "CursorPaginator",
    "create_pagination_urls",
    "paginate_queryset",
    # Validation (lazy-loaded)
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
    # Modules (lazy-loaded)
    "authz",
    "ses",
    "totp",
    # OpenAPI (lazy-loaded)
    "SchemaGenerator",
]
