"""
Kinglet Utility Functions - Caching, asset URLs, and other helpers
"""

from __future__ import annotations

import functools
import hashlib
import json
import time
from collections.abc import Callable
from typing import Any, Protocol

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
            cache_key = _generate_cache_key(
                func.__name__, cache_type, args, kwargs, path_params
            )

            storage = getattr(request.env, storage_binding, None)
            if not storage:
                return await func(*args, **kwargs)

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


def _detect_protocol(request: Request) -> str:
    """Detect if we're running on HTTPS"""
    if request.header("x-forwarded-proto") == "https" or (
        hasattr(request, "_parsed_url") and request._parsed_url.scheme == "https"
    ):
        return "https"
    return "http"


def _get_host(request: Request) -> str:
    """Get host from header, fallback to parsed URL if available"""
    host = request.header("host")
    if not host and hasattr(request, "_parsed_url"):
        host = request._parsed_url.netloc
    return host


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

        # Build full URL with protocol and host
        protocol = _detect_protocol(request)
        host = _get_host(request)

        if host:
            return f"{protocol}://{host}{path}"
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


def _generate_cache_key(
    func_name: str, cache_type: str, args: tuple, kwargs: dict, path_params: dict = None
) -> str:
    """Generate a cache key from function name and arguments"""
    # Create a string representation of arguments
    key_parts = [func_name, cache_type]

    # Add path parameters (most important for route-based caching)
    if path_params:
        for k, v in sorted(path_params.items()):
            key_parts.append(f"path_{k}={v}")

    # Add positional args (skip request object)
    for arg in args[1:]:  # Skip first arg which is usually request
        if hasattr(arg, "__dict__"):
            continue  # Skip complex objects
        key_parts.append(str(arg))

    # Add keyword args
    for k, v in sorted(kwargs.items()):
        if not hasattr(v, "__dict__"):  # Skip complex objects
            key_parts.append(f"{k}={v}")

    # Generate hash for consistent key length
    key_string = "|".join(key_parts)
    return f"cache:{hashlib.sha256(key_string.encode()).hexdigest()[:16]}"


def cache_aside_d1(
    db_binding: str = "DB",
    cache_type: str = "default",
    ttl: int = 3600,
    policy: CachePolicy | None = None,
    track_hits: bool = False,
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

            cache_key = _generate_d1_cache_key(request, cache_type)

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


def _generate_d1_cache_key(request: Request, cache_type: str = "default") -> str:
    """Generate cache key optimized for D1 from request"""
    # Use path as primary key component
    path = getattr(request, "path", "")

    # Include query parameters for cache differentiation
    query_params = {}
    if hasattr(request, "query_string") and request.query_string:
        # Parse common query params that affect cache
        for param in ["sort", "limit", "offset", "page", "filter", "search"]:
            value = getattr(request, "query", lambda _x, d=None: d)(param)
            if value is not None:
                query_params[param] = value

    # Include path parameters
    path_params = getattr(request, "path_params", {})

    # Build cache key
    key_parts = [cache_type, path.rstrip("/")]

    # Add path parameters (most specific)
    for k, v in sorted(path_params.items()):
        key_parts.append(f"path_{k}={v}")

    # Add query parameters
    for k, v in sorted(query_params.items()):
        key_parts.append(f"query_{k}={v}")

    # Generate shorter hash for D1 efficiency
    key_string = "|".join(key_parts)
    return f"d1:{hashlib.sha256(key_string.encode()).hexdigest()[:24]}"
