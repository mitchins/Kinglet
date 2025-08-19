-- Kinglet D1 Cache Table
-- Single table for all cache-aside operations
-- Optimized for fast lookups and automatic TTL cleanup

CREATE TABLE IF NOT EXISTS experience_cache (
    cache_key TEXT PRIMARY KEY,           -- Unique cache key (path + query hash)
    content TEXT NOT NULL,                -- Cached JSON content
    content_type TEXT DEFAULT 'application/json',  -- Content type
    created_at INTEGER NOT NULL,          -- Unix timestamp
    expires_at INTEGER NOT NULL,          -- Unix timestamp for TTL
    hit_count INTEGER DEFAULT 0,          -- Cache hit tracking
    size_bytes INTEGER DEFAULT 0          -- Content size for monitoring
);

-- Index for efficient TTL cleanup
CREATE INDEX IF NOT EXISTS idx_experience_cache_expires 
ON experience_cache(expires_at);

-- Index for monitoring cache usage
CREATE INDEX IF NOT EXISTS idx_experience_cache_created 
ON experience_cache(created_at);

-- Cleanup trigger to remove expired entries
-- This will be handled by the cache service, not triggers
-- as CloudFlare D1 has limited trigger support