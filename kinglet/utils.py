"""
Kinglet Utility Functions - Caching, asset URLs, and other helpers
"""

from __future__ import annotations

import functools
import hashlib
import json
import re
import time
from collections.abc import Callable
from typing import Any, Protocol
from urllib.parse import urlparse

from .http import Request


async def async_noop() -> None:  # NOSONAR
    """
    No-operation coroutine for maintaining async function signatures.

    Use this when you have an async function that doesn't yet perform
    any actual async operations, but needs to maintain API compatibility.

    Example:
        async def my_function():
            await async_noop()  # Keeps function async-compliant
            return synchronous_operation()
    """
    return None


class CachePolicy(Protocol):
    """Protocol for cache policy implementations"""

    def should_cache(self, request: Request) -> bool:
        """Determine if caching should be enabled for this request"""
        ...


class EnvironmentCachePolicy:
    """Environment-aware cache policy that respects configuration"""

    def __init__(
        self,
        disable_in_dev: bool = True,
        cache_env_var: str = "USE_CACHE",
        environment_var: str = "ENVIRONMENT",
    ):
        self.disable_in_dev = disable_in_dev
        self.cache_env_var = cache_env_var
        self.environment_var = environment_var

    def should_cache(self, request: Request) -> bool:
        """Check if caching should be enabled based on environment configuration"""
        # Explicit cache configuration takes precedence
        use_cache = getattr(request.env, self.cache_env_var, None)
        if use_cache is not None:
            return str(use_cache).lower() in ("true", "1", "yes", "on")

        # Check environment-based policy
        if self.disable_in_dev:
            environment = getattr(
                request.env, self.environment_var, "production"
            ).lower()
            if environment in ("development", "dev", "test", "local"):
                return False

        # Default to caching enabled
        return True


class AlwaysCachePolicy:
    """Policy that always enables caching"""

    def should_cache(self, _request: Request) -> bool:
        return True


class NeverCachePolicy:
    """Policy that never enables caching"""

    def should_cache(self, _request: Request) -> bool:
        return False


# Default policy instance
_default_cache_policy = EnvironmentCachePolicy()


_DEFAULT_CACHE_VARY_HEADERS = (
    "authorization",
    "cookie",
    "x-api-key",
    "x-user-id",
    "x-tenant-id",
)


def _serialize_cache_component(value: Any) -> str:
    """Create a deterministic string representation for cache key components."""
    if isinstance(value, str):
        return value

    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    except Exception:
        return repr(value)


def _normalized_vary_headers(vary_headers: tuple[str, ...] | list[str] | None) -> list[str]:
    """Merge built-in and custom vary headers while preserving order."""
    headers: list[str] = []
    seen: set[str] = set()

    for header_name in (*_DEFAULT_CACHE_VARY_HEADERS, *(vary_headers or ())):
        normalized = str(header_name).lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            headers.append(normalized)

    return headers


async def _request_body_signature(request: Request) -> str | None:
    """Hash the request body when it is present."""
    if not hasattr(request, "text"):
        return None

    try:
        body = await request.text()
    except Exception:
        return None

    if not body:
        return None

    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _append_identity_parts(parts: list[str], source: Any, prefix: str) -> None:
    """Append stable identity hints from request or state objects."""
    if source is None:
        return

    for attr in ("user", "tenant", "tenant_id", "user_id", "auth", "identity"):
        if hasattr(source, attr):
            value = getattr(source, attr)
            if value is not None:
                parts.append(f"{prefix}_{attr}={_serialize_cache_component(value)}")


async def _request_cache_parts(
    request: Request, path_params: dict | None = None, vary_headers: tuple[str, ...] | None = None
) -> list[str]:
    """Build stable cache key components from the request context."""
    parts = [f"method={getattr(request, 'method', 'GET').upper()}"]

    path = getattr(request, "path", "")
    parts.append(f"path={path.rstrip('/')}")

    query_string = getattr(request, "query_string", "")
    if query_string:
        parts.append(f"query={query_string}")

    effective_path_params = path_params or getattr(request, "path_params", {}) or {}
    for key, value in sorted(effective_path_params.items()):
        parts.append(f"path_{key}={_serialize_cache_component(value)}")

    for header_name in _normalized_vary_headers(vary_headers):
        try:
            value = request.header(header_name)
        except Exception:
            value = None
        if value not in (None, ""):
            parts.append(f"header_{header_name}={_serialize_cache_component(value)}")

    _append_identity_parts(parts, request, "request")
    _append_identity_parts(parts, getattr(request, "state", None), "state")

    body_signature = await _request_body_signature(request)
    if body_signature:
        parts.append(f"body={body_signature}")

    return parts


def _normalize_origin_url(origin: str) -> str | None:
    """Return a normalized absolute origin URL or None if invalid."""
    if not origin:
        return None

    candidate = origin.strip()
    if not candidate:
        return None

    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _is_loopback_host(host: str) -> bool:
    """Allow local development hosts without trusting arbitrary public hosts."""
    normalized = host.lower()
    return (
        normalized == "testserver"
        or normalized.startswith("localhost")
        or normalized.startswith("127.0.0.1")
        or normalized.startswith("[::1]")
        or normalized == "::1"
        or normalized.endswith(".localhost")
    )


def _safe_request_host(request: Request) -> str | None:
    """Return a syntactically safe host header if one is present."""
    host = request.header("host")
    if not host and hasattr(request, "_parsed_url"):
        host = getattr(request._parsed_url, "netloc", "")

    if not host:
        return None

    candidate = host.strip()
    if not candidate:
        return None

    if not re.fullmatch(r"(?:\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9.-]+)(?::\d+)?", candidate):
        return None

    return candidate


def _detect_protocol(request: Request) -> str:
    """Backward-compatible protocol detection for existing tests and callers."""
    forwarded = request.header("x-forwarded-proto")
    if forwarded:
        return str(forwarded).split(",", 1)[0].strip().lower()

    parsed_url = getattr(request, "_parsed_url", None)
    scheme = getattr(parsed_url, "scheme", "")
    if scheme:
        return str(scheme).lower()

    return "http"


def _get_host(request: Request) -> str:
    """Backward-compatible host lookup for existing tests and callers."""
    host = request.header("host")
    if host:
        return str(host).strip()

    parsed_url = getattr(request, "_parsed_url", None)
    return str(getattr(parsed_url, "netloc", "")).strip()


def _trusted_request_origin(request: Request) -> str | None:
    """Resolve a safe absolute origin for asset URLs."""
    env = getattr(request, "env", None)
    if env is not None:
        for attr_name in ("PUBLIC_ORIGIN", "APP_ORIGIN", "CANONICAL_ORIGIN", "BASE_URL"):
            configured = getattr(env, attr_name, None)
            origin = _normalize_origin_url(str(configured)) if configured else None
            if origin:
                return origin

    host = _safe_request_host(request)
    if not host:
        return None

    allowed_hosts = getattr(env, "ALLOWED_HOSTS", None) if env is not None else None
    if allowed_hosts:
        if isinstance(allowed_hosts, str):
            allowed = {
                item.strip().lower()
                for item in allowed_hosts.split(",")
                if item.strip()
            }
        else:
            allowed = {str(item).strip().lower() for item in allowed_hosts if str(item).strip()}

        if host.lower() not in allowed:
            return None
    elif not _is_loopback_host(host):
        return None

    scheme = "https" if getattr(getattr(request, "_parsed_url", None), "scheme", "") == "https" else "http"
    return f"{scheme}://{host}".rstrip("/")


class CacheService:
    """Cache service for storing and retrieving data with TTL"""

    def __init__(self, storage, ttl: int = 3600):
        """
        Initialize cache service

        Args:
            storage: Storage backend (e.g., KV namespace)
            ttl: Time to live in seconds
        """
        self.storage = storage
        self.ttl = ttl

    async def get(self, key: str) -> Any | None:
        """Get value from cache"""
        try:
            if hasattr(self.storage, "get"):
                value = await self.storage.get(key)
                if value:
                    cached_data = json.loads(value)

                    # Check if expired
                    if time.time() < cached_data.get("expires_at", 0):
                        return cached_data.get("data")
        except (json.JSONDecodeError, AttributeError):
            # Invalid cache, treat as miss
            return None
        return None

    async def set(self, key: str, value: Any) -> None:
        """Set value in cache with TTL"""
        try:
            if hasattr(self.storage, "put"):
                cache_data = {
                    "data": value,
                    "expires_at": time.time() + self.ttl,
                    "created_at": time.time(),
                }
                await self.storage.put(key, json.dumps(cache_data))
        except Exception:
            # Ignore cache failures
            return None

    async def get_or_generate(self, cache_key: str, generator_func: Callable, **kwargs):
        """Get from cache or generate fresh data"""
        try:
            # Try cache first
            obj = await self.storage.get(f"cache/{cache_key}")
            if obj:
                try:
                    if hasattr(obj, "text"):
                        cached_data = json.loads(await obj.text())
                    else:
                        # Mock storage returns string directly
                        cached_data = json.loads(obj)
                    # Check if still valid
                    if time.time() - cached_data.get("_cached_at", 0) < self.ttl:
                        cached_data["_cache_hit"] = True
                        return cached_data
                except (json.JSONDecodeError, AttributeError):
                    # Invalid cache entry; regenerate
                    pass

            # Generate fresh data
            fresh_data = await generator_func(**kwargs)
            fresh_data["_cached_at"] = time.time()
            fresh_data["_cache_hit"] = False

            # Store in cache
            await self.storage.put(
                f"cache/{cache_key}",
                json.dumps(fresh_data),
                {"httpMetadata": {"contentType": "application/json"}},
            )

            return fresh_data

        except Exception:
            # If cache fails, just return fresh data
            return await generator_func(**kwargs)


def cache_aside(
    storage_binding: str = "STORAGE",
    cache_type: str = "default",
    ttl: int = 3600,
    policy: CachePolicy | None = None,
    vary_headers: tuple[str, ...] | None = None,
):
    """
    Policy-driven cache-aside decorator for expensive operations

    Args:
        storage_binding: Name of storage binding in env
        cache_type: Type of cache for key prefixing
        ttl: Time to live in seconds
        policy: Cache policy to determine when to cache (default: EnvironmentCachePolicy)
    """
    # Use default policy if none provided
    cache_policy = policy or _default_cache_policy

    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapped(*args, **kwargs):
            request = next((arg for arg in args if hasattr(arg, "env")), None)
        if not request or not cache_policy.should_cache(request):
            return await func(*args, **kwargs)

            path_params = getattr(request, "path_params", {})

            storage = getattr(request.env, storage_binding, None)
            if not storage:
                return await func(*args, **kwargs)

            cache_key = await _generate_cache_key(
                func.__name__,
                cache_type,
                args,
                kwargs,
                getattr(request, "path_params", {}),
                request=request,
                vary_headers=vary_headers,
            )

            cache = CacheService(storage, ttl)

            async def generator():
                return await func(*args, **kwargs)

            return await cache.get_or_generate(cache_key, generator)

        return wrapped

    return decorator


def set_default_cache_policy(policy: CachePolicy):
    """Set the global default cache policy for cache_aside decorators"""
    global _default_cache_policy
    _default_cache_policy = policy


def get_default_cache_policy() -> CachePolicy:
    """Get the current global default cache policy"""
    return _default_cache_policy


def _build_asset_path(uid: str, asset_type: str) -> str:
    """Build asset path based on type"""
    if asset_type == "media":
        return f"/api/media/{uid}"
    elif asset_type == "static":
        return f"/assets/{uid}"
    else:
        return f"/{asset_type}/{uid}"


def _get_cdn_url(request: Request, path: str, asset_type: str) -> str | None:
    """Get CDN URL if available for media assets"""
    if asset_type == "media" and hasattr(request.env, "CDN_BASE_URL"):
        cdn_base = request.env.CDN_BASE_URL.rstrip("/")
        return f"{cdn_base}{path}"
    return None


def asset_url(request: Request, uid: str, asset_type: str = "media") -> str:
    """
    Generate asset URL based on environment and type

    Args:
        request: Request object with environment info
        uid: Asset unique identifier
        asset_type: Type of asset (media, static, etc.)

    Returns:
        Complete URL for the asset
    """
    path = _build_asset_path(uid, asset_type)

    try:
        # Check if CDN_BASE_URL is available for media assets
        cdn_url = _get_cdn_url(request, path, asset_type)
        if cdn_url:
            return cdn_url

        # Only emit an absolute URL when we have a trusted canonical origin.
        origin = _trusted_request_origin(request)
        if origin:
            return f"{origin}{path}"
    except Exception:
        # Fall through to return path-only
        return path

    return path


def media_url(uid: str) -> str:
    """
    Generate media URL for assets using environment configuration

    Args:
        uid: Media asset unique identifier

    Returns:
        Complete media URL
    """
    import os

    # Use CDN_BASE_URL from environment directly
    cdn_base = os.environ.get("CDN_BASE_URL", "/api/media").rstrip("/")
    return f"{cdn_base}/{uid}"


async def _generate_cache_key(
    func_name: str,
    cache_type: str,
    args: tuple,
    kwargs: dict,
    path_params: dict | None = None,
    *,
    request: Request | None = None,
    vary_headers: tuple[str, ...] | None = None,
) -> str:
    """Generate a cache key from function name, request context, and arguments."""
    key_parts = [func_name, cache_type]

    if request is not None:
        key_parts.extend(await _request_cache_parts(request, path_params, vary_headers))
    elif path_params:
        for k, v in sorted(path_params.items()):
            key_parts.append(f"path_{k}={_serialize_cache_component(v)}")

    # Add positional args (skip request object)
    for arg in args[1:]:  # Skip first arg which is usually request
        if hasattr(arg, "__dict__"):
            continue  # Skip complex objects
        key_parts.append(_serialize_cache_component(arg))

    # Add keyword args
    for k, v in sorted(kwargs.items()):
        if not hasattr(v, "__dict__"):  # Skip complex objects
            key_parts.append(f"{k}={_serialize_cache_component(v)}")

    # Generate hash for consistent key length
    key_string = "|".join(key_parts)
    return f"cache:{hashlib.sha256(key_string.encode()).hexdigest()[:16]}"


def cache_aside_d1(
    db_binding: str = "DB",
    cache_type: str = "default",
    ttl: int = 3600,
    policy: CachePolicy | None = None,
    track_hits: bool = False,
    vary_headers: tuple[str, ...] | None = None,
):
    """
    D1 database caching decorator

    Args:
        db_binding: Name of D1 database binding in env (default: "DB")
        cache_type: Type of cache for monitoring
        ttl: Time to live in seconds
        policy: Cache policy (default: EnvironmentCachePolicy)
        track_hits: Whether to track hit counts (default: False, reduces write operations)
    """
    cache_policy = policy or _default_cache_policy

    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapped(*args, **kwargs):
            request = next((arg for arg in args if hasattr(arg, "env")), None)
            if not request or not cache_policy.should_cache(request):
                return await func(*args, **kwargs)

            db = getattr(request.env, db_binding, None)
            if not db:
                return await func(*args, **kwargs)

            cache_key = await _generate_d1_cache_key(
                request, cache_type, vary_headers=vary_headers
            )

            try:
                from .cache_d1 import D1CacheService

                cache_service = D1CacheService(db, ttl, track_hits=track_hits)

                async def generator():
                    return await func(*args, **kwargs)

                return await cache_service.get_or_generate(cache_key, generator)
            except ImportError:
                print("D1 cache service not available")
            except Exception as e:
                print(f"D1 cache error: {e}")

            return await func(*args, **kwargs)

        return wrapped

    return decorator


async def _generate_d1_cache_key(
    request: Request,
    cache_type: str = "default",
    *,
    vary_headers: tuple[str, ...] | None = None,
) -> str:
    """Generate a cache key optimized for D1 from the full request context."""
    key_parts = [cache_type]
    key_parts.extend(await _request_cache_parts(request, vary_headers=vary_headers))

    # Generate shorter hash for D1 efficiency
    key_string = "|".join(key_parts)
    return f"d1:{hashlib.sha256(key_string.encode()).hexdigest()[:24]}"
