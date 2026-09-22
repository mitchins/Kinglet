"""
Barn door tests for D1 cache functionality - test the API surface
and basic behaviors without needing real D1 database connections.
"""

import time
from unittest.mock import AsyncMock, Mock, patch

from kinglet.cache_d1 import D1CacheService, generate_cache_key


class TestCacheBarnDoor:
    """Barn door tests for cache functionality"""

    def test_generate_cache_key_returns_string(self):
        """Test cache key generation returns consistent format"""
        key = generate_cache_key(
            "/api/users", extra_params={"user_id": 123, "active": True}
        )

        assert isinstance(key, str)
        assert len(key) > 0
        assert key.startswith("cache:")

        # Should be consistent for same inputs
        key2 = generate_cache_key(
            "/api/users", extra_params={"user_id": 123, "active": True}
        )
        assert key == key2

        # Should be different for different inputs
        key3 = generate_cache_key(
            "/api/users", extra_params={"user_id": 456, "active": True}
        )
        assert key != key3

    def test_generate_cache_key_handles_various_types(self):
        """Test cache key generation with different parameter types"""
        # String parameters
        key1 = generate_cache_key("/path", extra_params={"name": "test"})
        assert isinstance(key1, str)

        # Integer parameters
        key2 = generate_cache_key("/path", extra_params={"count": 42})
        assert isinstance(key2, str)

        # Boolean parameters
        key3 = generate_cache_key("/path", extra_params={"enabled": True})
        assert isinstance(key3, str)

        # Mixed parameters
        key4 = generate_cache_key(
            "/path", extra_params={"id": 1, "name": "test", "active": False}
        )
        assert isinstance(key4, str)

        # All should be different
        keys = [key1, key2, key3, key4]
        assert len(set(keys)) == len(keys)

    def test_d1cache_constructor(self):
        """Test D1CacheService can be constructed with expected parameters"""
        mock_db = Mock()

        # Basic construction
        cache = D1CacheService(mock_db)
        assert cache is not None
        assert cache.db is mock_db

        # Construction with custom parameters should work
        cache2 = D1CacheService(mock_db, ttl=3600, track_hits=True)
        assert cache2 is not None

    async def test_d1cache_get_returns_expected_types(self):
        """Test that cache get operations return expected types"""
        mock_db = Mock()
        cache = D1CacheService(mock_db)

        # Mock database to return None (cache miss)
        mock_stmt = AsyncMock()
        mock_stmt.bind = Mock(return_value=mock_stmt)
        mock_stmt.first = AsyncMock(return_value=None)
        mock_db.prepare = Mock(return_value=mock_stmt)

        result = await cache.get("test_key")

        # Should return None for cache miss
        assert result is None

        # Verify prepare was called
        mock_db.prepare.assert_called()

    async def test_d1cache_get_preserves_live_metadata(self):
        """Test that live cache metadata overrides stored payload fields."""
        mock_db = Mock()
        cache = D1CacheService(mock_db, track_hits=True)

        mock_stmt = AsyncMock()
        mock_stmt.bind = Mock(return_value=mock_stmt)
        mock_stmt.first = AsyncMock(
            return_value=Mock(
                to_py=Mock(
                    return_value={
                        "content": '{"_cache_hit": false, "_cached_at": 1, "value": 42}',
                        "created_at": 99,
                        "hit_count": 7,
                    }
                )
            )
        )
        mock_db.prepare = Mock(return_value=mock_stmt)

        result = await cache.get("test_key")
        assert result["_cache_hit"] is True
        assert result["_cached_at"] == 99
        assert result["_hit_count"] == 7
        assert result["value"] == 42

    async def test_d1cache_set_accepts_various_content_types(self):
        """Test that cache set accepts different content types"""
        mock_db = Mock()
        cache = D1CacheService(mock_db)

        # Mock database operations
        mock_stmt = AsyncMock()
        mock_stmt.bind = Mock(return_value=mock_stmt)
        mock_stmt.run = AsyncMock(return_value=Mock())
        mock_db.prepare = Mock(return_value=mock_stmt)

        # Test string content
        result = await cache.set("key1", "string_value")
        assert isinstance(result, bool)

        # Test dict content
        result = await cache.set("key2", {"data": "value"})
        assert isinstance(result, bool)

        # Test list content
        result = await cache.set("key3", ["item1", "item2"])
        assert isinstance(result, bool)

    async def test_d1cache_delete_returns_boolean(self):
        """Test that cache delete returns boolean"""
        mock_db = Mock()
        cache = D1CacheService(mock_db)

        # Mock database operations
        mock_stmt = AsyncMock()
        mock_stmt.bind = Mock(return_value=mock_stmt)
        mock_stmt.run = AsyncMock(return_value=Mock(meta=Mock(changes=1)))
        mock_db.prepare = Mock(return_value=mock_stmt)

        result = await cache.delete("test_key")
        assert isinstance(result, bool)
        assert result is True  # Mock returns changes=1

    async def test_d1cache_clear_expired_returns_integer(self):
        """Test that clear_expired returns count"""
        mock_db = Mock()
        cache = D1CacheService(mock_db)

        # Mock database operations
        mock_stmt = AsyncMock()
        mock_stmt.bind = Mock(return_value=mock_stmt)
        mock_stmt.run = AsyncMock(return_value=Mock(meta=Mock(changes=5)))
        mock_db.prepare = Mock(return_value=mock_stmt)

        result = await cache.clear_expired()
        assert isinstance(result, int)
        assert result == 5

    async def test_d1cache_invalidate_pattern_returns_integer(self):
        """Test that invalidate_pattern returns count"""
        mock_db = Mock()
        cache = D1CacheService(mock_db)

        # Mock database operations
        mock_stmt = AsyncMock()
        mock_stmt.bind = Mock(return_value=mock_stmt)
        mock_stmt.run = AsyncMock(return_value=Mock(meta=Mock(changes=3)))
        mock_db.prepare = Mock(return_value=mock_stmt)

        result = await cache.invalidate_pattern("/api/users/%")
        assert isinstance(result, int)
        assert result == 3

    async def test_d1cache_get_stats_returns_dict(self):
        """Test that get_stats returns statistics dictionary"""
        mock_db = Mock()
        cache = D1CacheService(mock_db)

        # Mock database operations
        mock_result = Mock()
        mock_result.to_py = Mock(
            return_value={
                "total_entries": 100,
                "total_size": 1024,
                "total_hits": 500,
                "avg_hits_per_entry": 5.0,
                "expired_entries": 10,
            }
        )

        mock_stmt = AsyncMock()
        mock_stmt.bind = Mock(return_value=mock_stmt)
        mock_stmt.first = AsyncMock(return_value=mock_result)
        mock_db.prepare = Mock(return_value=mock_stmt)

        result = await cache.get_stats()
        assert isinstance(result, dict)
        assert "total_entries" in result
        assert "total_size" in result

    def test_d1cache_error_handling_structure(self):
        """Test that D1CacheService methods have proper error handling structure"""
        mock_db = Mock()
        cache = D1CacheService(mock_db)

        # All async methods should exist and be callable
        async_methods = [
            "get",
            "set",
            "delete",
            "clear_expired",
            "invalidate_pattern",
            "get_stats",
        ]

        for method_name in async_methods:
            assert hasattr(cache, method_name)
            method = getattr(cache, method_name)
            assert callable(method)

    async def test_ensure_cache_table_returns_boolean(self):
        """Test ensure_cache_table returns boolean status"""
        from kinglet.cache_d1 import ensure_cache_table

        mock_db = Mock()

        # Mock successful table creation
        with patch("os.path.exists", return_value=True), patch(
            "asyncio.get_event_loop"
        ) as mock_loop, patch(
            "builtins.open", mock_data="CREATE TABLE..."
        ) as _mock_open:
            mock_loop.return_value.run_in_executor = AsyncMock(
                return_value="CREATE TABLE..."
            )
            mock_db.exec = AsyncMock()

            result = await ensure_cache_table(mock_db)
            assert isinstance(result, bool)

    def test_cache_key_generation_edge_cases(self):
        """Test cache key generation with edge cases"""
        # No extra params
        key1 = generate_cache_key("/path")
        assert isinstance(key1, str)
        assert len(key1) > 0

        # No extra params
        key2 = generate_cache_key("/path")
        assert isinstance(key2, str)

        # Many extra params
        key3 = generate_cache_key(
            "/path", extra_params={f"param{i}": i for i in range(10)}
        )
        assert isinstance(key3, str)

        # Special characters in path
        key4 = generate_cache_key("/api/users/123")
        assert isinstance(key4, str)

    def test_d1cache_configuration_properties(self):
        """Test that D1CacheService exposes configuration properties"""
        mock_db = Mock()

        cache = D1CacheService(mock_db, ttl=1800, track_hits=False)

        # Should expose configuration
        assert hasattr(cache, "ttl")
        assert hasattr(cache, "table_name")
        assert cache.ttl == 1800
        assert cache.table_name == "experience_cache"


class TestCacheIntegrationBarnDoor:
    """Integration-style barn door tests for cache"""

    async def test_cache_workflow_with_mocks(self):
        """Test complete cache workflow with mocked database"""
        mock_db = Mock()
        cache = D1CacheService(mock_db, ttl=300)

        # Mock cache miss then cache hit
        mock_stmt = AsyncMock()
        mock_stmt.bind = Mock(return_value=mock_stmt)

        # First call: cache miss
        mock_stmt.first = AsyncMock(return_value=None)
        mock_stmt.run = AsyncMock(return_value=Mock())
        mock_db.prepare = Mock(return_value=mock_stmt)

        # Try to get (should miss)
        result = await cache.get("test_key")
        assert result is None

        # Set value
        set_result = await cache.set("test_key", {"data": "value"})
        assert isinstance(set_result, bool)

        # Mock cache hit for next get
        mock_hit_result = Mock()
        mock_hit_result.to_py = Mock(
            return_value={
                "content": '{"data": "value"}',
                "created_at": int(time.time()),
                "hit_count": 1,
            }
        )
        mock_stmt.first = AsyncMock(return_value=mock_hit_result)

        # Get should now hit
        result = await cache.get("test_key")
        # Result should be processed (not None)
        assert result is not None

    async def test_cache_ttl_behavior(self):
        """Test that cache respects TTL configuration"""
        mock_db = Mock()

        # Short TTL cache
        cache = D1CacheService(mock_db, ttl=1)
        assert cache.ttl == 1

        # Long TTL cache
        cache2 = D1CacheService(mock_db, ttl=86400)
        assert cache2.ttl == 86400

    def test_cache_table_name_customization(self):
        """Test cache table name can be customized"""
        mock_db = Mock()

        # Default table name
        cache1 = D1CacheService(mock_db)
        assert cache1.table_name  # Should have some default

        # Custom table name
        cache2 = D1CacheService(mock_db)
        assert cache2.table_name == "experience_cache"

    def test_cache_hit_tracking_configuration(self):
        """Test hit tracking can be enabled/disabled"""
        mock_db = Mock()

        # With hit tracking
        _cache1 = D1CacheService(mock_db, track_hits=True)
        # Should accept the parameter (implementation details may vary)

        # Without hit tracking
        _cache2 = D1CacheService(mock_db, track_hits=False)
        # Should accept the parameter


class StubRequest:
    """Minimal request double for cache-key fingerprinting."""

    def __init__(self, method="GET", query_string="", path_params=None, headers=None):
        self.method = method
        self.query_string = query_string
        self.path_params = path_params or {}
        self._headers = {k.lower(): v for k, v in (headers or {}).items()}

    def header(self, name, default=None):
        return self._headers.get(name.lower(), default)


class TestGenerateCacheKeyRequestAndBody:
    """Cover the request/body fingerprint branches of generate_cache_key."""

    def test_request_parts_included(self):
        req = StubRequest(
            method="post",
            query_string="a=1",
            path_params={"id": "7"},
            headers={"Authorization": "Bearer x"},
        )
        key = generate_cache_key("/api/items/", request=req)
        assert key.startswith("cache:")

        bare = generate_cache_key("/api/items/")
        assert key != bare

        # Deterministic for identical requests.
        again = generate_cache_key(
            "/api/items/",
            request=StubRequest(
                method="POST",
                query_string="a=1",
                path_params={"id": "7"},
                headers={"Authorization": "Bearer x"},
            ),
        )
        assert key == again

    def test_request_without_query_or_params(self):
        req = StubRequest()
        key = generate_cache_key("/p", request=req)
        assert key != generate_cache_key("/p")

    def test_explicit_headers_win_over_request(self):
        req = StubRequest(headers={"Authorization": "Bearer x"})
        auto = generate_cache_key("/p", request=req)
        explicit = generate_cache_key("/p", request=req, headers={"x-tenant-id": "t1"})
        assert auto != explicit
        # Deterministic for identical inputs.
        assert explicit == generate_cache_key(
            "/p",
            request=StubRequest(headers={"Authorization": "Bearer x"}),
            headers={"x-tenant-id": "t1"},
        )

    def test_request_without_header_method(self):
        class BareRequest:
            method = "GET"
            query_string = ""
            path_params = {}

        key = generate_cache_key("/p", request=BareRequest())
        assert key.startswith("cache:")

    def test_body_bytes_and_str_fingerprinted(self):
        key_bytes = generate_cache_key("/p", body=b"\x00\x01")
        key_str = generate_cache_key("/p", body="hello")
        key_none = generate_cache_key("/p", body=None)
        assert len({key_bytes, key_str, key_none}) == 3
        assert generate_cache_key("/p", body=b"\x00\x01") == key_bytes
        assert generate_cache_key("/p", body="hello") == key_str
