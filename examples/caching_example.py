"""
Kinglet Environment-Aware Caching Examples

Demonstrates intelligent caching that adapts to deployment environments
with policy-based configuration.
"""

import asyncio
import time

from kinglet import (
    AlwaysCachePolicy,
    EnvironmentCachePolicy,
    Kinglet,
    NeverCachePolicy,
    cache_aside,
    set_default_cache_policy,
)

app = Kinglet(debug=True)

# Configure global cache policy (optional - EnvironmentCachePolicy is default)
set_default_cache_policy(
    EnvironmentCachePolicy(
        disable_in_dev=True, cache_env_var="USE_CACHE", environment_var="ENVIRONMENT"
    )
)


# Example 1: Basic Environment-Aware Caching
@app.get("/api/basic-data")
@cache_aside(cache_type="basic_data", ttl=1800)  # 30 minutes
async def get_basic_data(request):
    """
    Automatically adapts based on environment:
    - Development: Cache disabled (fresh data)
    - Production: Cache enabled (30min TTL)
    """
    # Simulate expensive operation
    await asyncio.sleep(0.5)
    return {
        "data": "expensive_computation_result",
        "timestamp": time.time(),
        "environment": "auto-detected",
    }


# Example 2: Always Cache (Critical Production Data)
@app.get("/api/critical-data")
@cache_aside(
    cache_type="critical_data",
    ttl=3600,  # 1 hour
    policy=AlwaysCachePolicy(),
)
async def get_critical_data(request):
    """
    Always cached regardless of environment.
    Useful for expensive operations that must be cached.
    """
    await asyncio.sleep(1.0)  # Simulate expensive DB query
    return {
        "critical_info": "mission_critical_data",
        "computed_at": time.time(),
        "cache_policy": "always",
    }


# Example 3: Never Cache (Sensitive Data)
@app.get("/api/sensitive-data")
@cache_aside(
    cache_type="sensitive_data",
    ttl=300,  # TTL ignored due to policy
    policy=NeverCachePolicy(),
)
async def get_sensitive_data(request):
    """
    Never cached for security reasons.
    Always returns fresh data.
    """
    return {
        "user_data": "always_fresh_sensitive_info",
        "generated_at": time.time(),
        "cache_policy": "never",
    }


# Example 4: Custom Cache Policy
class BusinessHoursCachePolicy:
    """Cache only during business hours (9 AM - 5 PM)"""

    def should_cache(self, request):
        import datetime

        hour = datetime.datetime.now().hour
        return 9 <= hour <= 17


@app.get("/api/business-reports")
@cache_aside(cache_type="business_reports", ttl=1800, policy=BusinessHoursCachePolicy())
async def get_business_reports(request):
    """
    Custom caching logic: only cache during business hours.
    """
    await asyncio.sleep(0.3)
    return {
        "report_data": "quarterly_business_metrics",
        "generated_at": time.time(),
        "cache_policy": "business_hours_only",
    }


# Example 5: Feature Flag Cache Policy
class FeatureFlagCachePolicy:
    """Cache based on feature flag"""

    def should_cache(self, request):
        # Check feature flag in environment
        return getattr(request.env, "FEATURE_CACHE_ENABLED", True)


@app.get("/api/feature-data")
@cache_aside(
    cache_type="feature_data",
    ttl=900,  # 15 minutes
    policy=FeatureFlagCachePolicy(),
)
async def get_feature_data(request):
    """
    Cache based on feature flag configuration.
    """
    return {
        "feature_data": "experimental_feature_result",
        "timestamp": time.time(),
        "cache_policy": "feature_flag_controlled",
    }


# Example 6: Different TTL for Different Data Types
@app.get("/api/static-config")
@cache_aside(cache_type="static_config", ttl=86400)  # 24 hours
async def get_static_config(request):
    """Long-lived cache for configuration data"""
    return {"config": "rarely_changing_settings", "version": "1.0"}


@app.get("/api/live-stats")
@cache_aside(cache_type="live_stats", ttl=30)  # 30 seconds
async def get_live_stats(request):
    """Short-lived cache for frequently changing data"""
    return {"stats": "real_time_metrics", "timestamp": time.time()}


# Example 7: Cache with Path Parameters
@app.get("/api/user/{user_id}/profile")
@cache_aside(cache_type="user_profile", ttl=1800)
async def get_user_profile(request):
    """
    Cache automatically includes path parameters in key generation.
    Each user_id gets its own cache entry.
    """
    user_id = request.path_param("user_id")
    await asyncio.sleep(0.2)  # Simulate DB lookup
    return {
        "user_id": user_id,
        "profile": f"profile_data_for_user_{user_id}",
        "loaded_at": time.time(),
    }


# Example 8: Cache with Query Parameters
@app.get("/api/search")
@cache_aside(cache_type="search_results", ttl=600)  # 10 minutes
async def search_data(request):
    """
    Cache automatically includes query parameters in key generation.
    Different search terms get separate cache entries.
    """
    query = request.query("q", "")
    limit = request.query_int("limit", 10)

    await asyncio.sleep(0.3)  # Simulate search operation
    return {
        "query": query,
        "limit": limit,
        "results": f"search_results_for_{query}",
        "searched_at": time.time(),
    }


# Example 9: Custom Storage Binding
@app.get("/api/custom-storage")
@cache_aside(
    storage_binding="CUSTOM_CACHE",  # Use different KV namespace
    cache_type="custom_data",
    ttl=1200,
)
async def get_custom_storage_data(request):
    """
    Use custom storage binding instead of default "STORAGE".
    Requires CUSTOM_CACHE KV namespace in environment.
    """
    return {
        "data": "stored_in_custom_kv_namespace",
        "storage": "CUSTOM_CACHE",
        "timestamp": time.time(),
    }


# Example 10: Cache Status Endpoint
@app.get("/api/cache-status")
async def cache_status(request):
    """
    Helper endpoint to check cache configuration.
    Not cached - always returns current status.
    """
    from kinglet import get_default_cache_policy

    policy = get_default_cache_policy()
    policy_name = type(policy).__name__

    # Check if caching would be enabled
    would_cache = policy.should_cache(request)

    return {
        "cache_policy": policy_name,
        "would_cache": would_cache,
        "environment": getattr(request.env, "ENVIRONMENT", "production"),
        "use_cache_override": getattr(request.env, "USE_CACHE", None),
        "timestamp": time.time(),
    }


if __name__ == "__main__":
    print("Environment-Aware Caching Examples Ready!")
    print()
    print("Test different environments:")
    print("  ENVIRONMENT=development  # Cache disabled")
    print("  ENVIRONMENT=production   # Cache enabled")
    print("  USE_CACHE=false         # Force disable")
    print("  USE_CACHE=true          # Force enable")
    print()
    print("Test endpoints:")
    print("  GET /api/basic-data      (environment-aware)")
    print("  GET /api/critical-data   (always cached)")
    print("  GET /api/sensitive-data  (never cached)")
    print("  GET /api/cache-status    (check current config)")
    print("  GET /api/user/123/profile (path params)")
    print("  GET /api/search?q=test   (query params)")
