"""
Tests for CacheService and cache_aside decorator
"""

import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from kinglet import (
    CacheService,
    Kinglet,
    TestClient,
    cache_aside,
    asset_url,
    media_url,
    require_field,
    validate_json_body,
)


class MockStorage:
    """Mock R2 storage for testing"""

    def __init__(self):
        self.data = {}

    async def get(self, key):
        if key in self.data:
            mock_obj = Mock()
            mock_obj.text = AsyncMock(return_value=self.data[key])
            return mock_obj
        return None

    async def put(self, key, content, metadata=None):
        self.data[key] = content


class AssetRequest:
    """Minimal request stub for asset_url tests."""

    def __init__(self, host="localhost:8787", scheme="http", env=None, headers=None):
        self.env = env or SimpleNamespace()
        self._parsed_url = SimpleNamespace(
            path="/api", query="", scheme=scheme, netloc=host
        )
        self._headers = {k.lower(): v for k, v in (headers or {}).items()}

    def header(self, name, default=None):
        return self._headers.get(name.lower(), default)


def test_cache_service():
    """Test basic CacheService functionality"""
    import asyncio

    storage = MockStorage()
    cache = CacheService(storage, ttl=60)

    async def test_generator():
        return {"data": "fresh", "timestamp": time.time()}

    # First call should generate fresh data
    result1 = asyncio.run(cache.get_or_generate("test_key", test_generator))
    assert result1["_cache_hit"] is False
    assert "data" in result1

    # Second call should hit cache
    result2 = asyncio.run(cache.get_or_generate("test_key", test_generator))
    assert result2["_cache_hit"] is True


def test_cache_aside_decorator():
    """Test @cache_aside decorator"""
    app = Kinglet()
    storage = MockStorage()

    @app.get("/cached")
    @cache_aside(cache_type="test", ttl=60)
    async def cached_endpoint(request):
        return {"message": "generated", "timestamp": time.time()}

    client = TestClient(app, env={"STORAGE": storage, "ENVIRONMENT": "production"})

    # First request - cache miss
    status1, headers1, body1 = client.request("GET", "/cached")
    assert status1 == 200
    data1 = json.loads(body1)
    assert data1["_cache_hit"] is False

    # Second request - cache hit
    status2, headers2, body2 = client.request("GET", "/cached")
    assert status2 == 200
    data2 = json.loads(body2)
    assert data2["_cache_hit"] is True


def test_cache_aside_no_storage():
    """Test @cache_aside decorator when no storage available"""
    app = Kinglet()

    @app.get("/cached")
    @cache_aside()
    async def cached_endpoint(request):
        return {"message": "no cache"}

    client = TestClient(app)  # No storage in env

    status, headers, body = client.request("GET", "/cached")
    assert status == 200
    data = json.loads(body)
    assert "_cache_hit" not in data  # No caching happened


def test_media_url_generation():
    """Test environment-aware media_url function"""
    import os

    # Test with CDN_BASE_URL environment variable
    original_cdn = os.environ.get("CDN_BASE_URL")

    try:
        os.environ["CDN_BASE_URL"] = "https://media.example.com"
        result = media_url("test-uid-123")
        assert result == "https://media.example.com/test-uid-123"

        # Test with default fallback
        del os.environ["CDN_BASE_URL"]
        result = media_url("test-uid-123")
        assert result == "/api/media/test-uid-123"

    finally:
        # Restore original environment
        if original_cdn:
            os.environ["CDN_BASE_URL"] = original_cdn
        elif "CDN_BASE_URL" in os.environ:
            del os.environ["CDN_BASE_URL"]


def test_asset_url_uses_configured_origin():
    """Test asset_url prefers a configured canonical origin."""
    request = AssetRequest(
        host="evil.example",
        scheme="https",
        env=SimpleNamespace(PUBLIC_ORIGIN="https://cdn.example.com"),
        headers={"Host": "evil.example", "X-Forwarded-Proto": "http"},
    )

    result = asset_url(request, "test-uid-123")
    assert result == "https://cdn.example.com/api/media/test-uid-123"


def test_asset_url_allows_loopback_hosts():
    """Test asset_url still works for local development hosts."""
    request = AssetRequest(host="localhost:8787", scheme="http")

    result = asset_url(request, "test-uid-123")
    assert result == "http://localhost:8787/api/media/test-uid-123"


def test_asset_url_rejects_untrusted_host_header():
    """Test asset_url falls back to a relative path for unsafe hosts."""
    request = AssetRequest(host="evil.example", scheme="https")

    result = asset_url(request, "test-uid-123")
    assert result == "/api/media/test-uid-123"


def test_validate_json_body():
    """Test @validate_json_body decorator"""
    app = Kinglet()

    @app.post("/validate")
    @validate_json_body
    async def validate_endpoint(request):
        data = await request.json()
        return {"received": data}

    client = TestClient(app)

    # Valid JSON
    status, headers, body = client.request("POST", "/validate", json={"test": "data"})
    assert status == 200

    # Invalid JSON (empty)
    status, headers, body = client.request("POST", "/validate", json={})
    assert status == 400
    data = json.loads(body)
    assert "empty" in data["error"]


def test_require_field():
    """Test @require_field decorator"""
    app = Kinglet()

    @app.post("/require")
    @require_field("email", str)
    @require_field("age", int)
    async def require_endpoint(request):
        return {"status": "valid"}

    client = TestClient(app)

    # Valid data
    status, headers, body = client.request(
        "POST", "/require", json={"email": "test@example.com", "age": 25}
    )
    assert status == 200

    # Missing field
    status, headers, body = client.request(
        "POST", "/require", json={"email": "test@example.com"}
    )
    assert status == 400
    data = json.loads(body)
    assert "age" in data["error"]

    # Wrong type
    status, headers, body = client.request(
        "POST", "/require", json={"email": "test@example.com", "age": "25"}
    )
    assert status == 400
    data = json.loads(body)
    assert "int" in data["error"]


def test_dynamic_path_caching():
    """Test @cache_aside with dynamic path parameters"""
    app = Kinglet()
    storage = MockStorage()

    @app.get("/game/{slug}")
    @cache_aside(cache_type="game_detail", ttl=60)
    async def game_detail(request):
        slug = request.path_param("slug")
        return {
            "game": slug,
            "details": f"Details for {slug}",
            "timestamp": time.time(),
        }

    client = TestClient(app, env={"STORAGE": storage, "ENVIRONMENT": "production"})

    # Request for wild-west-shootout
    status1, headers1, body1 = client.request("GET", "/game/wild-west-shootout")
    assert status1 == 200
    data1 = json.loads(body1)
    assert data1["_cache_hit"] is False
    assert data1["game"] == "wild-west-shootout"

    # Same game should hit cache
    status2, headers2, body2 = client.request("GET", "/game/wild-west-shootout")
    assert status2 == 200
    data2 = json.loads(body2)
    assert data2["_cache_hit"] is True

    # Different game should be cache miss
    status3, headers3, body3 = client.request("GET", "/game/space-adventure")
    assert status3 == 200
    data3 = json.loads(body3)
    assert data3["_cache_hit"] is False
    assert data3["game"] == "space-adventure"


def test_cache_aside_vary_by_query_and_authorization():
    """Test cache_aside varies by full query string and auth header."""
    app = Kinglet()
    storage = MockStorage()

    @app.get("/search")
    @cache_aside(cache_type="search", ttl=60)
    async def search_endpoint(request):
        return {
            "q": request.query("q"),
            "auth": request.header("authorization"),
            "timestamp": time.time(),
        }

    client = TestClient(app, env={"STORAGE": storage, "ENVIRONMENT": "production"})

    status1, _, body1 = client.request(
        "GET", "/search?q=alice", headers={"Authorization": "Bearer alice"}
    )
    assert status1 == 200
    data1 = json.loads(body1)
    assert data1["_cache_hit"] is False
    assert data1["q"] == "alice"

    status2, _, body2 = client.request(
        "GET", "/search?q=alice", headers={"Authorization": "Bearer alice"}
    )
    assert status2 == 200
    data2 = json.loads(body2)
    assert data2["_cache_hit"] is True

    status3, _, body3 = client.request(
        "GET", "/search?q=bob", headers={"Authorization": "Bearer alice"}
    )
    assert status3 == 200
    data3 = json.loads(body3)
    assert data3["_cache_hit"] is False
    assert data3["q"] == "bob"

    status4, _, body4 = client.request(
        "GET", "/search?q=alice", headers={"Authorization": "Bearer bob"}
    )
    assert status4 == 200
    data4 = json.loads(body4)
    assert data4["_cache_hit"] is False
    assert data4["auth"] == "Bearer bob"


def test_cache_aside_vary_by_request_body():
    """Test cache_aside varies by request body for POST routes."""
    app = Kinglet()
    storage = MockStorage()

    @app.post("/submit")
    @cache_aside(cache_type="submit", ttl=60)
    async def submit_endpoint(request):
        data = await request.json()
        return {"value": data["value"], "timestamp": time.time()}

    client = TestClient(app, env={"STORAGE": storage, "ENVIRONMENT": "production"})

    status1, _, body1 = client.request("POST", "/submit", json={"value": "one"})
    assert status1 == 200
    data1 = json.loads(body1)
    assert data1["_cache_hit"] is False
    assert data1["value"] == "one"

    status2, _, body2 = client.request("POST", "/submit", json={"value": "one"})
    assert status2 == 200
    data2 = json.loads(body2)
    assert data2["_cache_hit"] is True

    status3, _, body3 = client.request("POST", "/submit", json={"value": "two"})
    assert status3 == 200
    data3 = json.loads(body3)
    assert data3["_cache_hit"] is False
    assert data3["value"] == "two"


def test_combined_decorators():
    """Test combining multiple decorators"""
    app = Kinglet()
    storage = MockStorage()

    @app.post("/combined")
    @cache_aside(storage_binding="STORAGE", cache_type="combined")
    @validate_json_body
    @require_field("name", str)
    async def combined_endpoint(request):
        data = await request.json()
        return {"processed": data["name"], "timestamp": time.time()}

    client = TestClient(app, env={"STORAGE": storage, "ENVIRONMENT": "production"})

    # Valid request
    status, headers, body = client.request("POST", "/combined", json={"name": "test"})
    assert status == 200
    data = json.loads(body)
    assert data["_cache_hit"] is False
    assert data["processed"] == "test"

    # Same request should hit cache
    status, headers, body = client.request("POST", "/combined", json={"name": "test"})
    assert status == 200
    data = json.loads(body)
    assert data["_cache_hit"] is True


if __name__ == "__main__":
    # Add a simple async runner to TestClient if it doesn't exist
    if not hasattr(TestClient, "_run_async"):
        import asyncio

        TestClient._run_async = lambda coro: asyncio.run(coro)

    # Run tests manually if pytest not available
    import sys

    try:
        import pytest

        pytest.main([__file__, "-v"])
    except ImportError:
        print("Running tests manually (install pytest for better output)")

        test_functions = [
            test_cache_service,
            test_cache_aside_decorator,
            test_cache_aside_no_storage,
            test_media_url_generation,
            test_validate_json_body,
            test_require_field,
            test_dynamic_path_caching,
            test_combined_decorators,
        ]

        passed = 0
        failed = 0

        for test_func in test_functions:
            try:
                test_func()
                print(f"✅ {test_func.__name__}")
                passed += 1
            except Exception as e:
                print(f"❌ {test_func.__name__}: {e}")
                failed += 1

        print(f"\nResults: {passed} passed, {failed} failed")
        sys.exit(0 if failed == 0 else 1)
