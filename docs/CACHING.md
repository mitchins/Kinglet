# Environment-Aware Caching

Kinglet provides intelligent caching that automatically adapts to your deployment environment, eliminating boilerplate and preventing cache pollution during development.

## Quick Start

### Basic Usage (Environment-Aware by Default)

```python
from kinglet import Kinglet, cache_aside

app = Kinglet()

@app.get("/api/expensive-data")
@cache_aside(cache_type="api_data", ttl=1800)  # Auto dev/prod awareness
async def get_data(request):
    # This endpoint automatically:
    # - Caches in production (30min TTL)
    # - Skips cache in development (fresh data)
    return await expensive_database_query()
```

### Environment Variables

Control caching behavior with environment variables:

```bash
# Explicit cache control (overrides environment detection)
USE_CACHE=true          # Force enable caching
USE_CACHE=false         # Force disable caching

# Environment-based auto-detection
ENVIRONMENT=development # Auto-disable caching
ENVIRONMENT=production  # Auto-enable caching
```

## Cache Policies

**New in v1.4.3:** Policy-based caching with dependency injection.

### Built-in Policies

```python
from kinglet import (
    EnvironmentCachePolicy,  # Smart dev/prod detection (default)
    AlwaysCachePolicy,       # Force caching enabled
    NeverCachePolicy,        # Force caching disabled
    set_default_cache_policy
)

# Global policy configuration (application startup)
set_default_cache_policy(EnvironmentCachePolicy(
    disable_in_dev=True,              # Disable in dev environments
    cache_env_var="USE_CACHE",        # Explicit override variable
    environment_var="ENVIRONMENT"     # Environment detection variable
))
```

### Per-Endpoint Policy Override

```python
# Force caching for critical production endpoint
@cache_aside(
    cache_type="critical_data", 
    ttl=3600, 
    policy=AlwaysCachePolicy()
)
async def critical_endpoint(request):
    return await mission_critical_query()

# Never cache sensitive data
@cache_aside(
    cache_type="sensitive", 
    ttl=900, 
    policy=NeverCachePolicy()
)
async def sensitive_endpoint(request):
    return await user_sensitive_data()
```

## Custom Cache Policies

Create policies for complex scenarios:

```python
class BusinessHoursCachePolicy:
    def should_cache(self, request):
        import datetime
        hour = datetime.datetime.now().hour
        return 9 <= hour <= 17  # Cache only during business hours

class FeatureFlagCachePolicy:
    def should_cache(self, request):
        return getattr(request.env, 'CACHE_FEATURE_ENABLED', True)

class UserRoleCachePolicy:
    def should_cache(self, request):
        user = getattr(request, 'user', None)
        return user and user.get('role') == 'premium'

# Use custom policies
@cache_aside(cache_type="reports", ttl=1800, policy=BusinessHoursCachePolicy())
async def business_reports(request):
    return await generate_reports()
```

## Storage Configuration

### Default Setup (CloudFlare Workers)

```python
# Kinglet automatically uses request.env.STORAGE
@cache_aside(cache_type="default", ttl=3600)
async def cached_endpoint(request):
    # Uses CloudFlare KV namespace bound as "STORAGE"
    return await data_query()
```

### Custom Storage Binding

```python
# Use different KV namespace
@cache_aside(storage_binding="CACHE_KV", cache_type="custom", ttl=1800)
async def custom_cached_endpoint(request):
    # Uses CloudFlare KV namespace bound as "CACHE_KV"
    return await data_query()
```

## Cache Keys & TTL

### Automatic Key Generation

Cache keys are automatically generated from:
- Function name
- Path parameters  
- Query parameters
- Cache type

```python
@cache_aside(cache_type="user_data", ttl=3600)
async def get_user_data(request):
    user_id = request.path_param("user_id")
    include_private = request.query("private", "false")
    # Key: cache:sha256(get_user_data|user_data|user_id=123|private=false)[:16]
    return await fetch_user(user_id, include_private)
```

### TTL Configuration

```python
# Different TTL for different data types
@cache_aside(cache_type="static_data", ttl=86400)     # 24 hours
async def static_content(request):
    return await fetch_static_data()

@cache_aside(cache_type="dynamic_data", ttl=300)      # 5 minutes  
async def dynamic_content(request):
    return await fetch_live_data()

@cache_aside(cache_type="realtime_data", ttl=30)      # 30 seconds
async def realtime_content(request):
    return await fetch_realtime_data()
```

## Development vs Production

### Development Environment
```python
# ENVIRONMENT=development or ENVIRONMENT=dev
@cache_aside(cache_type="api_data", ttl=1800)
async def get_api_data(request):
    # ✅ Cache bypassed - always fresh data
    # ✅ No stale data during development
    # ✅ Database changes reflected immediately
    return await fresh_database_query()
```

### Production Environment
```python
# ENVIRONMENT=production (default)
@cache_aside(cache_type="api_data", ttl=1800)
async def get_api_data(request):
    # ✅ Cache enabled - 30 minute TTL
    # ✅ Reduced database load
    # ✅ Faster response times
    return await cached_database_query()
```

## Migration Guide

### From Manual Environment Checking

**Before (v1.4.2 and earlier):**
```python
def conditional_cache(cache_type, ttl):
    def decorator(func):
        async def wrapper(request):
            if request.env.ENVIRONMENT == 'development':
                return await func(request)
            return await cache_aside(cache_type, ttl)(func)(request)
        return wrapper
    return decorator

@conditional_cache(cache_type="games", ttl=1800)
async def get_games(request):
    return await fetch_games()
```

**After (v1.4.3):**
```python
@cache_aside(cache_type="games", ttl=1800)  # Environment-aware automatically!
async def get_games(request):
    return await fetch_games()
```

### Removing Boilerplate

Delete custom cache wrappers and environment checking code:

```python
# ❌ Remove this boilerplate
def dev_aware_cache(cache_type, ttl):
    # Custom environment checking logic
    pass

# ✅ Replace with this
@cache_aside(cache_type="data", ttl=1800)  # Smart by default
```

## Advanced Configuration

### Application-Wide Policy

```python
# main.py - Application startup
from kinglet import set_default_cache_policy, EnvironmentCachePolicy

# Configure for your deployment
set_default_cache_policy(EnvironmentCachePolicy(
    disable_in_dev=True,
    cache_env_var="MY_CACHE_SETTING", 
    environment_var="APP_ENVIRONMENT"
))

# All @cache_aside decorators now use this policy
```

### Dynamic Policy Selection

```python
class MultiEnvironmentCachePolicy:
    def should_cache(self, request):
        env = getattr(request.env, 'ENVIRONMENT', 'production').lower()
        
        if env in ('test', 'unittest'):
            return False  # Never cache in tests
        elif env == 'staging':
            return True   # Cache in staging
        elif env == 'development':
            return getattr(request.env, 'DEV_CACHE_ENABLE', False)
        else:
            return True   # Cache in production
```

## Best Practices

1. **Use default policy** - `EnvironmentCachePolicy` handles most scenarios
2. **Set TTL appropriately** - Balance freshness vs performance
3. **Cache expensive operations** - Database queries, API calls, computations
4. **Avoid caching user-specific data** - Unless properly scoped
5. **Test cache behavior** - Verify dev/prod differences
6. **Monitor cache hit rates** - Optimize TTL based on usage patterns

## Troubleshooting

### Cache Not Working in Production
```bash
# Check environment variables
echo $ENVIRONMENT    # Should be 'production' 
echo $USE_CACHE      # Should be unset or 'true'
```

### Cache Not Disabled in Development  
```bash
# Set explicit environment
export ENVIRONMENT=development

# Or force disable
export USE_CACHE=false
```

### Custom Storage Issues
```python
# Verify storage binding exists
@cache_aside(storage_binding="MY_STORAGE", cache_type="test", ttl=300)
async def test_cache(request):
    # Check that request.env.MY_STORAGE is available
    if not hasattr(request.env, 'MY_STORAGE'):
        print("Storage binding missing!")
    return {"test": "data"}
```