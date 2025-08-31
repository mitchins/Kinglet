"""
Tests for kinglet.utils module
"""

from unittest.mock import Mock

from kinglet.utils import (
    _build_asset_path,
    _detect_protocol,
    _get_cdn_url,
    _get_host,
    asset_url,
    media_url,
)


class TestAssetURLGeneration:
    """Test asset URL generation functions"""

    def test_build_asset_path_types(self):
        """Test asset path building for different types"""
        assert _build_asset_path("123", "media") == "/api/media/123"
        assert _build_asset_path("style.css", "static") == "/assets/style.css"
        assert _build_asset_path("doc.pdf", "docs") == "/docs/doc.pdf"

    def test_get_cdn_url_with_cdn_base(self):
        """Test CDN URL generation when CDN_BASE_URL is available"""
        request = Mock()
        request.env.CDN_BASE_URL = "https://cdn.example.com/"

        result = _get_cdn_url(request, "/api/media/123", "media")
        assert result == "https://cdn.example.com/api/media/123"

    def test_get_cdn_url_without_cdn_base(self):
        """Test CDN URL generation when CDN_BASE_URL is not available"""
        request = Mock()
        request.env = Mock(spec=[])  # No CDN_BASE_URL

        result = _get_cdn_url(request, "/api/media/123", "media")
        assert result is None

    def test_get_cdn_url_non_media_asset(self):
        """Test CDN URL generation for non-media assets"""
        request = Mock()
        request.env.CDN_BASE_URL = "https://cdn.example.com"

        result = _get_cdn_url(request, "/assets/style.css", "static")
        assert result is None

    def test_detect_protocol_https_header(self):
        """Test HTTPS detection via x-forwarded-proto header"""
        request = Mock()
        request.header = Mock(return_value="https")

        result = _detect_protocol(request)
        assert result == "https"
        request.header.assert_called_with("x-forwarded-proto")

    def test_detect_protocol_https_parsed_url(self):
        """Test HTTPS detection via parsed URL"""
        request = Mock()
        request.header = Mock(return_value=None)
        request._parsed_url = Mock()
        request._parsed_url.scheme = "https"

        result = _detect_protocol(request)
        assert result == "https"

    def test_detect_protocol_http_default(self):
        """Test protocol detection defaulting to HTTP"""
        request = Mock()
        request.header = Mock(return_value=None)
        # No _parsed_url attribute

        result = _detect_protocol(request)
        assert result == "http"

    def test_get_host_from_header(self):
        """Test getting host from header"""
        request = Mock()
        request.header = Mock(return_value="example.com")

        result = _get_host(request)
        assert result == "example.com"
        request.header.assert_called_with("host")

    def test_get_host_from_parsed_url(self):
        """Test getting host from parsed URL as fallback"""
        request = Mock()
        request.header = Mock(return_value=None)
        request._parsed_url = Mock()
        request._parsed_url.netloc = "example.com"

        result = _get_host(request)
        assert result == "example.com"


class TestAssetURLIntegration:
    """Test full asset URL generation"""

    def test_asset_url_with_cdn(self):
        """Test full asset URL generation with CDN"""
        request = Mock()
        request.env.CDN_BASE_URL = "https://cdn.example.com"

        result = asset_url(request, "123", "media")
        assert result == "https://cdn.example.com/api/media/123"

    def test_media_url_fallback_to_host(self):
        """Test media URL generation falling back to host detection"""
        request = Mock()
        request.env = Mock(spec=[])  # No CDN
        request.header = Mock(
            side_effect=lambda h: "example.com"
            if h == "host"
            else "https"
            if h == "x-forwarded-proto"
            else None
        )

        result = media_url(request, "456")
        assert result == "https://example.com/api/media/456"
