"""
Tests for Kinglet 1.3.0 D1 and R2 helper functions
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from kinglet import (
    asset_url,
    d1_unwrap,
    d1_unwrap_results,
    r2_get_content_info,
    r2_get_metadata,
)


class TestD1Helpers:
    """Test D1 database helper functions"""

    def test_d1_unwrap_dict(self):
        """Test d1_unwrap with regular dict"""
        data = {"id": 1, "name": "test"}
        result = d1_unwrap(data)
        assert result == data

    def test_d1_unwrap_none(self):
        """Test d1_unwrap with None"""
        result = d1_unwrap(None)
        assert result == {}

    def test_d1_unwrap_mock_proxy(self):
        """Test d1_unwrap with mock D1 proxy object"""
        class MockD1Proxy:
            def to_py(self):
                return {"id": 1, "title": "Game"}

        proxy = MockD1Proxy()
        result = d1_unwrap(proxy)
        assert result == {"id": 1, "title": "Game"}

    def test_d1_unwrap_object_with_keys(self):
        """Test d1_unwrap with object that has keys() method"""
        class MockObject:
            def keys(self):
                return ["id", "name"]
            def __getitem__(self, key):
                return {"id": 1, "name": "test"}[key]

        obj = MockObject()
        result = d1_unwrap(obj)
        assert result == {"id": 1, "name": "test"}

    def test_d1_unwrap_to_py_failure_raises(self):
        """Test d1_unwrap raises when .to_py() fails"""
        class MockBadProxy:
            def to_py(self):
                raise RuntimeError("Proxy conversion failed")

        proxy = MockBadProxy()
        try:
            d1_unwrap(proxy)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Failed to unwrap D1 object via .to_py()" in str(e)

    def test_d1_unwrap_unknown_type_raises(self):
        """Test d1_unwrap raises ValueError for unknown types"""
        try:
            d1_unwrap("some string")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Cannot unwrap D1 object of type str" in str(e)

    def test_d1_unwrap_results_with_results_array(self):
        """Test d1_unwrap_results generator with D1 .all() format"""
        class MockD1Results:
            def __init__(self, results):
                self.results = results

        mock_results = MockD1Results([
            {"id": 1, "name": "Game 1"},
            {"id": 2, "name": "Game 2"}
        ])

        # Test as generator
        result_gen = d1_unwrap_results(mock_results)
        result_list = list(result_gen)
        assert len(result_list) == 2
        assert result_list[0] == {"id": 1, "name": "Game 1"}
        assert result_list[1] == {"id": 2, "name": "Game 2"}

        # Test list version (manual conversion)
        result_list = list(d1_unwrap_results(MockD1Results([
            {"id": 1, "name": "Game 1"},
            {"id": 2, "name": "Game 2"}
        ])))
        assert len(result_list) == 2
        assert result_list[0] == {"id": 1, "name": "Game 1"}

    def test_d1_unwrap_results_with_list(self):
        """Test d1_unwrap_results generator with direct list"""
        data = [{"id": 1}, {"id": 2}]
        result_list = list(d1_unwrap_results(data))
        assert result_list == data

    def test_d1_unwrap_results_empty(self):
        """Test d1_unwrap_results generator with empty/None input"""
        assert list(d1_unwrap_results(None)) == []
        assert list(d1_unwrap_results([])) == []


class TestR2Helpers:
    """Test R2 storage helper functions"""

    def test_r2_get_metadata_simple(self):
        """Test r2_get_metadata with simple object"""
        obj = {"size": 1024, "httpMetadata": {"contentType": "image/png"}}

        assert r2_get_metadata(obj, "size") == 1024
        assert r2_get_metadata(obj, "httpMetadata.contentType") == "image/png"
        assert r2_get_metadata(obj, "missing", "default") == "default"

    def test_r2_get_metadata_none(self):
        """Test r2_get_metadata with None object"""
        assert r2_get_metadata(None, "any.path", "default") == "default"

    def test_r2_get_metadata_mock_r2_object(self):
        """Test r2_get_metadata with mock R2 object"""
        class MockR2Object:
            def __init__(self):
                self.size = 2048
                self.httpEtag = "abc123"
                self.httpMetadata = MockMetadata()

        class MockMetadata:
            contentType = "image/jpeg"

        obj = MockR2Object()
        assert r2_get_metadata(obj, "size") == 2048
        assert r2_get_metadata(obj, "httpEtag") == "abc123"
        assert r2_get_metadata(obj, "httpMetadata.contentType") == "image/jpeg"

    def test_r2_get_metadata_dict_access(self):
        """Test r2_get_metadata with nested dictionary access"""
        obj = {"httpMetadata": {"contentType": "text/plain"}}
        assert r2_get_metadata(obj, "httpMetadata.contentType") == "text/plain"

    def test_r2_get_content_info(self):
        """Test r2_get_content_info helper"""
        class MockR2Object:
            def __init__(self):
                self.size = 1024
                self.httpEtag = "etag123"
                self.uploaded = "2023-01-01T00:00:00Z"
                self.httpMetadata = MockMetadata()
                self.customMetadata = {"author": "test"}

        class MockMetadata:
            contentType = "image/png"

        obj = MockR2Object()
        info = r2_get_content_info(obj)

        assert info["content_type"] == "image/png"
        assert info["size"] == 1024
        assert info["etag"] == "etag123"
        assert info["last_modified"] == "2023-01-01T00:00:00Z"
        assert info["custom_metadata"] == {"author": "test"}

    def test_r2_get_content_info_defaults(self):
        """Test r2_get_content_info with missing properties"""
        info = r2_get_content_info({})

        assert info["content_type"] == "application/octet-stream"
        assert info["size"] is None
        assert info["etag"] is None
        assert info["last_modified"] is None
        assert info["custom_metadata"] == {}


class TestAssetUrlHelper:
    """Test asset URL generation helper"""

    def test_asset_url_media_dev(self):
        """Test asset_url for media in development"""
        class MockRequest:
            def __init__(self):
                self.env = MockEnv()
            def header(self, name, default=None):
                headers = {"host": "localhost:8787"}
                return headers.get(name, default)

        class MockEnv:
            pass  # No CDN_BASE_URL

        request = MockRequest()
        url = asset_url(request, "abc123", "media")
        assert url == "http://localhost:8787/api/media/abc123"

    def test_asset_url_media_production(self):
        """Test asset_url for media in production with CDN"""
        class MockRequest:
            def __init__(self):
                self.env = MockEnv()

        class MockEnv:
            CDN_BASE_URL = "https://cdn.example.com"

        request = MockRequest()
        url = asset_url(request, "abc123", "media")
        assert url == "https://cdn.example.com/api/media/abc123"

    def test_asset_url_static(self):
        """Test asset_url for static assets"""
        class MockRequest:
            def __init__(self):
                self.env = MockEnv()
            def header(self, name, default=None):
                return {"host": "localhost:8787"}.get(name, default)

        class MockEnv:
            pass

        request = MockRequest()
        url = asset_url(request, "style.css", "static")
        assert url == "http://localhost:8787/assets/style.css"

    def test_asset_url_custom_type(self):
        """Test asset_url with custom asset type"""
        class MockRequest:
            def __init__(self):
                self.env = MockEnv()
            def header(self, name, default=None):
                return {"host": "localhost:8787"}.get(name, default)

        class MockEnv:
            pass

        request = MockRequest()
        url = asset_url(request, "logo.png", "uploads")
        assert url == "http://localhost:8787/uploads/logo.png"

    def test_asset_url_https_detection(self):
        """Test asset_url HTTPS detection"""
        class MockRequest:
            def __init__(self):
                self.env = MockEnv()
            def header(self, name, default=None):
                headers = {
                    "host": "api.example.com",
                    "x-forwarded-proto": "https"
                }
                return headers.get(name, default)

        class MockEnv:
            pass

        request = MockRequest()
        url = asset_url(request, "test.jpg", "media")
        assert url == "https://api.example.com/api/media/test.jpg"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__])
