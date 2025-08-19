"""
Kinglet D1 Cache Example - Fast database-backed caching

This example demonstrates:
- D1-backed caching with automatic fallback to R2
- Environment-aware caching (disabled in dev by default)
- Cache invalidation patterns
- Performance monitoring
"""

import asyncio
from kinglet import Kinglet, cache_aside_d1, D1CacheService, ensure_cache_table

app = Kinglet(root_path="/api")

# Cache setup middleware
@app.middleware
async def setup_cache(request, handler):
    """Ensure cache table exists on first request"""
    if hasattr(request.env, 'DB'):
        await ensure_cache_table(request.env.DB)
    return await handler(request)

# Basic caching with D1 primary strategy
@app.get("/products")
@cache_aside_d1(cache_type="products", ttl=1800)  # 30 minutes
async def get_products(request):
    """Get products with D1 caching"""
    # Simulate expensive database query
    await asyncio.sleep(0.1)
    
    # Parse query parameters for filtering
    category = request.query("category")
    sort_by = request.query("sort", "name")
    limit = request.query_int("limit", 20)
    
    # Build response (this will be cached)
    products = [
        {"id": i, "name": f"Product {i}", "category": category or "general", "price": 10 + i}
        for i in range(1, limit + 1)
    ]
    
    return {
        "products": products,
        "total": len(products),
        "category": category,
        "sort_by": sort_by,
        "cache_info": "Cached with D1 for 30 minutes"
    }

# Dynamic route caching
@app.get("/products/{product_id}")
@cache_aside_d1(cache_type="product_detail", ttl=3600)  # 1 hour
async def get_product_detail(request):
    """Get product details with path-based cache key"""
    product_id = request.path_param("product_id")
    
    # Simulate database lookup
    await asyncio.sleep(0.05)
    
    return {
        "id": product_id,
        "name": f"Product {product_id}",
        "description": f"Detailed description of product {product_id}",
        "price": 10 + int(product_id),
        "stock": 100,
        "cache_info": "Cached per product ID for 1 hour"
    }

# Cache management endpoints
@app.get("/cache/stats")
async def get_cache_stats(request):
    """Get cache performance statistics"""
    if not hasattr(request.env, 'DB'):
        return {"error": "D1 database not available"}
    
    # Note: stats work regardless of hit tracking setting
    cache_service = D1CacheService(request.env.DB, track_hits=True)  # Enable for stats query
    stats = await cache_service.get_stats()
    
    return {
        "cache_stats": stats,
        "cache_backend": "D1 Primary",
        "hit_tracking_note": "Hit counts only updated when track_hits=True on cache operations"
    }

@app.post("/cache/cleanup")
async def cleanup_expired_cache(request):
    """Remove expired cache entries"""
    if not hasattr(request.env, 'DB'):
        return {"error": "D1 database not available"}
    
    cache_service = D1CacheService(request.env.DB)
    removed_count = await cache_service.clear_expired()
    
    return {
        "success": True,
        "removed_entries": removed_count,
        "message": f"Cleaned up {removed_count} expired cache entries"
    }

@app.delete("/cache/invalidate")
async def invalidate_cache_pattern(request):
    """Invalidate cache entries matching a pattern"""
    body = await request.json() or {}
    pattern = body.get("pattern")
    
    if not pattern:
        return {"error": "Pattern required"}, 400
    
    if not hasattr(request.env, 'DB'):
        return {"error": "D1 database not available"}
    
    cache_service = D1CacheService(request.env.DB)
    invalidated_count = await cache_service.invalidate_pattern(pattern)
    
    return {
        "success": True,
        "invalidated_entries": invalidated_count,
        "pattern": pattern,
        "message": f"Invalidated {invalidated_count} cache entries"
    }

# Example with custom cache policy for admin endpoints
from kinglet import AlwaysCachePolicy

@app.get("/admin/reports")
@cache_aside_d1(
    cache_type="admin_reports", 
    ttl=300,  # 5 minutes (shorter for admin data)
    policy=AlwaysCachePolicy(),  # Always cache even in dev
    track_hits=True  # Enable hit tracking for admin monitoring
)
async def get_admin_reports(request):
    """Admin reports with always-on caching and hit tracking"""
    # Simulate expensive report generation
    await asyncio.sleep(0.2)
    
    return {
        "reports": [
            {"name": "Sales Report", "generated_at": "2023-10-15T10:30:00Z"},
            {"name": "User Activity", "generated_at": "2023-10-15T10:30:00Z"},
            {"name": "Performance Metrics", "generated_at": "2023-10-15T10:30:00Z"}
        ],
        "cache_info": "Admin reports cached for 5 minutes with hit tracking"
    }

# Health check with cache info
@app.get("/")
async def health_check(request):
    """Health check with cache backend info"""
    import sys
    
    cache_backend = "None"
    if hasattr(request.env, 'DB'):
        cache_backend = "D1 Primary"
        if hasattr(request.env, 'STORAGE'):
            cache_backend += " + R2 Fallback"
    elif hasattr(request.env, 'STORAGE'):
        cache_backend = "R2 Only"
    
    return {
        "status": "healthy",
        "project": "Kinglet D1 Cache Demo",
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "runtime": "Pyodide" if hasattr(sys, '_emscripten_info') else "CPython",
        "cache_backend": cache_backend,
        "kinglet_version": "1.5.0"
    }

# CloudFlare Workers entry point
async def on_fetch(request, env):
    """CloudFlare Workers entry point"""
    return await app(request, env)

if __name__ == "__main__":
    import asyncio
    
    print("🚀 Kinglet D1 Cache Example")
    print("📊 Features:")
    print("  - D1-backed caching with R2 fallback")
    print("  - URL path + query parameter cache keys")
    print("  - Environment-aware caching policies")
    print("  - Cache statistics and management")
    print("  - Automatic TTL expiration")
    print("  - Pattern-based invalidation")
    print()
    print("💡 Usage:")
    print("  GET  /api/products?category=electronics&sort=price")
    print("  GET  /api/products/123")
    print("  GET  /api/cache/stats")
    print("  POST /api/cache/cleanup")
    print("  DELETE /api/cache/invalidate {\"pattern\": \"d1:products%\"}")