"""
Tests for D1CacheService error paths and exception handling
"""

from unittest.mock import AsyncMock, Mock

import pytest

from kinglet.cache_d1 import D1CacheService


class TestD1CacheServiceErrorPaths:
    """Test error handling and exception paths in D1CacheService"""

    @pytest.mark.asyncio
    async def test_get_with_track_hits_success(self):
        """Test cache get with track_hits=True - covers missing success path"""
        mock_db = Mock()
        cache = D1CacheService(mock_db, track_hits=True)

        # Mock successful database response with hit tracking
        mock_stmt = AsyncMock()
        mock_result = {
            "content": '{"data": "test"}',
            "created_at": "2023-01-01",
            "hit_count": 5,
        }

        mock_stmt.bind = Mock(return_value=mock_stmt)
        mock_stmt.first = AsyncMock(return_value=mock_result)
        mock_db.prepare = AsyncMock(return_value=mock_stmt)

        result = await cache.get("test_key")

        # Should return cached data with metadata
        assert result is not None
        assert result["_cached_at"] == "2023-01-01"
        assert result["_cache_hit"] is True
        assert result["_hit_count"] == 5
        assert result["data"] == "test"

    @pytest.mark.asyncio
    async def test_get_exception_handling(self):
        """Test cache get error handling - covers exception path"""
        mock_db = Mock()
        cache = D1CacheService(mock_db)

        # Mock database to raise exception
        mock_db.prepare = AsyncMock(side_effect=Exception("DB connection failed"))

        result = await cache.get("test_key")

        # Should return None on error and not propagate exception
        assert result is None

    @pytest.mark.asyncio
    async def test_get_with_track_hits_exception(self):
        """Test cache get with track_hits=True exception handling"""
        mock_db = Mock()
        cache = D1CacheService(mock_db, track_hits=True)

        # Mock database to raise exception in track_hits path
        mock_db.prepare = AsyncMock(side_effect=Exception("Hit tracking failed"))

        result = await cache.get("test_key")

        # Should return None on error and not propagate exception
        assert result is None

    @pytest.mark.asyncio
    async def test_set_size_limit_exceeded(self):
        """Test cache set with content too large - covers size limit path"""
        mock_db = Mock()
        cache = D1CacheService(mock_db, max_size=10)  # Very small size limit

        large_value = {"data": "x" * 1000}  # Exceeds 10 byte limit

        result = await cache.set("test_key", large_value)

        # Should return False when content is too large
        assert result is False

    @pytest.mark.asyncio
    async def test_set_exception_handling(self):
        """Test cache set error handling - covers exception path"""
        mock_db = Mock()
        cache = D1CacheService(mock_db)

        # Mock database to raise exception
        mock_db.prepare = AsyncMock(side_effect=Exception("DB write failed"))

        result = await cache.set("test_key", {"data": "test"})

        # Should return False on error and not propagate exception
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_exception_handling(self):
        """Test cache delete error handling - covers exception path"""
        mock_db = Mock()
        cache = D1CacheService(mock_db)

        # Mock database to raise exception
        mock_db.prepare = AsyncMock(side_effect=Exception("DB delete failed"))

        result = await cache.delete("test_key")

        # Should return False on error and not propagate exception
        assert result is False

    @pytest.mark.asyncio
    async def test_clear_expired_exception_handling(self):
        """Test cache clear_expired error handling - covers exception path"""
        mock_db = Mock()
        cache = D1CacheService(mock_db)

        # Mock database to raise exception
        mock_db.prepare = AsyncMock(side_effect=Exception("Clear expired failed"))

        result = await cache.clear_expired()

        # Should return 0 on error and not propagate exception
        assert result == 0

    @pytest.mark.asyncio
    async def test_invalidate_pattern_exception_handling(self):
        """Test cache invalidate_pattern error handling - covers exception path"""
        mock_db = Mock()
        cache = D1CacheService(mock_db)

        # Mock database to raise exception
        mock_db.prepare = AsyncMock(side_effect=Exception("Invalidate pattern failed"))

        result = await cache.invalidate_pattern("test_*")

        # Should return 0 on error and not propagate exception
        assert result == 0

    @pytest.mark.asyncio
    async def test_get_stats_exception_handling(self):
        """Test cache get_stats error handling - covers exception path"""
        mock_db = Mock()
        cache = D1CacheService(mock_db)

        # Mock database to raise exception
        mock_db.prepare = AsyncMock(side_effect=Exception("Stats query failed"))

        result = await cache.get_stats()

        # Should return error dict on error and not propagate exception
        assert result == {"error": "Stats query failed"}
