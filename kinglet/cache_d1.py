"""
Kinglet D1-backed Cache Service - Fast, cost-effective caching with CloudFlare D1
"""
import json
import time
import hashlib
from typing import Any, Optional, Dict
from .storage import d1_unwrap_results, d1_unwrap


class D1CacheService:
    """
    D1-backed cache service for CloudFlare Workers
    
    Features:
    - Fast database-backed caching
    - Automatic TTL expiration  
    - Cache hit tracking
    - Size monitoring
    - Batch operations
    """
    
    def __init__(self, db, ttl: int = 3600, max_size: int = 1048576, track_hits: bool = False):
        """
        Initialize D1 cache service
        
        Args:
            db: D1 database binding
            ttl: Time to live in seconds (default: 1 hour)
            max_size: Maximum cache entry size in bytes (default: 1MB)
            track_hits: Whether to track hit counts (default: False, adds write operations)
        """
        self.db = db
        self.ttl = ttl
        self.max_size = max_size
        self.track_hits = track_hits
        self.table_name = "experience_cache"
    
    async def get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get value from cache with optional hit tracking"""
        try:
            current_time = int(time.time())
            
            if self.track_hits:
                # Get from cache and update hit count atomically
                stmt = self.db.prepare(f"""
                    UPDATE {self.table_name} 
                    SET hit_count = hit_count + 1 
                    WHERE cache_key = ? AND expires_at > ?
                    RETURNING content, created_at, hit_count
                """)
                result = await stmt.bind(cache_key, current_time).first()
                
                if result:
                    result_dict = d1_unwrap(result)
                    return {
                        "_cached_at": result_dict.get("created_at"),
                        "_cache_hit": True,
                        "_hit_count": result_dict.get("hit_count"),
                        **json.loads(result_dict.get("content", "{}"))
                    }
            else:
                # Read-only cache lookup (no write operations)
                stmt = self.db.prepare(f"""
                    SELECT content, created_at 
                    FROM {self.table_name} 
                    WHERE cache_key = ? AND expires_at > ?
                """)
                result = await stmt.bind(cache_key, current_time).first()
                
                if result:
                    result_dict = d1_unwrap(result)
                    return {
                        "_cached_at": result_dict.get("created_at"),
                        "_cache_hit": True,
                        **json.loads(result_dict.get("content", "{}"))
                    }
            
            return None
            
        except Exception as e:
            # Cache failures should not break the application
            print(f"D1 cache get error: {e}")
            return None
    
    async def set(self, cache_key: str, value: Dict[str, Any]) -> bool:
        """Set value in cache with TTL"""
        try:
            content = json.dumps(value)
            content_size = len(content.encode('utf-8'))
            
            # Check size limit
            if content_size > self.max_size:
                print(f"Cache entry too large: {content_size} > {self.max_size}")
                return False
            
            current_time = int(time.time())
            expires_at = current_time + self.ttl
            
            # Upsert cache entry
            stmt = self.db.prepare(f"""
                INSERT OR REPLACE INTO {self.table_name} 
                (cache_key, content, created_at, expires_at, size_bytes)
                VALUES (?, ?, ?, ?, ?)
            """)
            
            await stmt.bind(cache_key, content, current_time, expires_at, content_size).run()
            return True
            
        except Exception as e:
            print(f"D1 cache set error: {e}")
            return False
    
    async def delete(self, cache_key: str) -> bool:
        """Delete specific cache entry"""
        try:
            stmt = self.db.prepare(f"DELETE FROM {self.table_name} WHERE cache_key = ?")
            result = await stmt.bind(cache_key).run()
            return result.changes > 0
        except Exception as e:
            print(f"D1 cache delete error: {e}")
            return False
    
    async def clear_expired(self) -> int:
        """Remove expired cache entries and return count removed"""
        try:
            current_time = int(time.time())
            stmt = self.db.prepare(f"DELETE FROM {self.table_name} WHERE expires_at <= ?")
            result = await stmt.bind(current_time).run()
            return result.changes
        except Exception as e:
            print(f"D1 cache cleanup error: {e}")
            return 0
    
    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate cache entries matching a pattern (e.g., '/api/games/%')"""
        try:
            stmt = self.db.prepare(f"DELETE FROM {self.table_name} WHERE cache_key LIKE ?")
            result = await stmt.bind(pattern).run()
            return result.changes
        except Exception as e:
            print(f"D1 cache invalidate error: {e}")
            return 0
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring"""
        try:
            stmt = self.db.prepare(f"""
                SELECT 
                    COUNT(*) as total_entries,
                    SUM(size_bytes) as total_size,
                    SUM(hit_count) as total_hits,
                    AVG(hit_count) as avg_hits_per_entry,
                    COUNT(*) FILTER (WHERE expires_at <= ?) as expired_entries
                FROM {self.table_name}
            """)
            
            current_time = int(time.time())
            result = await stmt.bind(current_time).first()
            
            if result:
                return d1_unwrap(result)
            
            return {"total_entries": 0, "total_size": 0, "total_hits": 0}
            
        except Exception as e:
            print(f"D1 cache stats error: {e}")
            return {"error": str(e)}
    
    async def get_or_generate(self, cache_key: str, generator_func, **kwargs):
        """Get from cache or generate fresh data (compatible with existing decorator)"""
        try:
            # Try cache first
            cached_data = await self.get(cache_key)
            if cached_data:
                return cached_data
            
            # Generate fresh data
            fresh_data = await generator_func(**kwargs)
            
            # Add cache metadata
            fresh_data['_cached_at'] = int(time.time())
            fresh_data['_cache_hit'] = False
            
            # Store in cache (async, don't wait)
            await self.set(cache_key, fresh_data)
            
            return fresh_data
            
        except Exception as e:
            # If cache fails, just return fresh data
            print(f"D1 cache get_or_generate error: {e}")
            return await generator_func(**kwargs)


def generate_cache_key(path: str, query_params: Dict[str, Any] = None, extra_params: Dict[str, Any] = None) -> str:
    """
    Generate cache key from URL path and parameters
    
    Args:
        path: URL path (e.g., '/api/games/action')
        query_params: Query parameters dict
        extra_params: Additional parameters (user_id, etc.)
    
    Returns:
        Cache key string
    """
    # Start with clean path
    key_parts = [path.rstrip('/')]
    
    # Add sorted query params
    if query_params:
        sorted_params = sorted(query_params.items())
        for key, value in sorted_params:
            key_parts.append(f"{key}={value}")
    
    # Add extra params
    if extra_params:
        sorted_extras = sorted(extra_params.items())
        for key, value in sorted_extras:
            key_parts.append(f"_{key}={value}")
    
    # Create deterministic key
    key_string = "|".join(key_parts)
    
    # Hash for consistent length and avoid special characters
    return f"cache:{hashlib.sha256(key_string.encode()).hexdigest()[:32]}"


async def ensure_cache_table(db) -> bool:
    """Ensure the experience_cache table exists"""
    try:
        # Read the schema file
        import os
        schema_path = os.path.join(os.path.dirname(__file__), "cache_d1.sql")
        
        if os.path.exists(schema_path):
            with open(schema_path, 'r') as f:
                schema_sql = f.read()
            
            # Execute schema (D1 supports multiple statements)
            await db.exec(schema_sql)
            return True
        else:
            # Fallback inline schema
            await db.exec("""
                CREATE TABLE IF NOT EXISTS experience_cache (
                    cache_key TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    content_type TEXT DEFAULT 'application/json',
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    hit_count INTEGER DEFAULT 0,
                    size_bytes INTEGER DEFAULT 0
                );
                
                CREATE INDEX IF NOT EXISTS idx_experience_cache_expires 
                ON experience_cache(expires_at);
            """)
            return True
            
    except Exception as e:
        print(f"Failed to create cache table: {e}")
        return False