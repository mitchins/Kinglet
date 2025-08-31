"""
Tests for HTTP module edge cases and uncovered branches
"""

from unittest.mock import Mock

import pytest

from kinglet.http import Request


class TestRequestInitialization:
    """Test Request initialization edge cases"""

    def test_request_fallback_initialization(self):
        """Test Request initialization with fallback path for test cases"""
        # Create a simple mock object that doesn't have the CloudFlare Worker request interface
        mock_request = Mock()
        mock_request.url = "https://example.com/test"
        mock_request.method = "POST"
        # Mock headers as empty dict to avoid iteration errors
        mock_request.headers = {}

        # This should trigger the fallback path (lines 37-40)
        request = Request(mock_request)

        assert request.url == "https://example.com/test"
        assert request.method == "POST"
        assert request._parsed_url is not None

    def test_request_fallback_defaults(self):
        """Test Request fallback uses defaults when attributes missing"""
        # Mock object with no url or method attributes
        mock_request = Mock(spec=[])  # Empty spec means no attributes

        # This should use fallback defaults
        request = Request(mock_request)

        assert request.url == "https://testserver/"
        assert request.method == "GET"


class TestHeaderExtraction:
    """Test header extraction edge cases"""

    def test_extract_headers_dict_with_missing_common_headers(self):
        """Test header extraction when common headers are missing"""
        mock_request = Mock()
        mock_request.url = "https://example.com"
        mock_request.method = "GET"

        # Mock headers object that has get() method but missing common headers
        mock_headers = {}  # Empty dict - has items() but no headers
        mock_request.headers = mock_headers

        request = Request(mock_request)

        # Should have tried to extract headers but found none
        assert len(request._headers) == 0  # No headers set since dict was empty

    def test_extract_headers_with_get_method(self):
        """Test header extraction using get() method path"""
        mock_request = Mock()
        mock_request.url = "https://example.com"
        mock_request.method = "GET"

        # Mock headers object that has get() method but not items()
        mock_headers = Mock()
        mock_headers.get = Mock(
            side_effect=lambda k: {"authorization": "Bearer token"}.get(k)
        )
        # Remove items method to force get() path
        del mock_headers.items
        mock_request.headers = mock_headers

        # Should use get() method path (lines 67-71)
        request = Request(mock_request)
        # Should have extracted authorization header
        assert request._headers.get("authorization") == "Bearer token"

    def test_extract_headers_iterable_format(self):
        """Test header extraction from iterable format"""
        mock_request = Mock()
        mock_request.url = "https://example.com"
        mock_request.method = "GET"

        # Mock headers as iterable of tuples (like some web frameworks)
        mock_headers = [
            ("Content-Type", "application/json"),
            ("Authorization", "Bearer token123"),
            ("Custom-Header", "value"),
        ]
        mock_request.headers = mock_headers

        request = Request(mock_request)

        # Headers should be extracted and lowercased
        assert request._headers["content-type"] == "application/json"
        assert request._headers["authorization"] == "Bearer token123"
        assert request._headers["custom-header"] == "value"

    def test_extract_headers_iterable_malformed(self):
        """Test header extraction handles malformed iterable gracefully"""
        mock_request = Mock()
        mock_request.url = "https://example.com"
        mock_request.method = "GET"

        # Mock headers with malformed entries (missing second element)
        mock_headers = [
            ("Content-Type",),  # Missing value - should cause IndexError
            ("Authorization", "Bearer token123"),
        ]
        mock_request.headers = mock_headers

        # Should handle IndexError gracefully
        request = Request(mock_request)
        # Only the valid header should be extracted
        assert len(request._headers) <= 1  # May have authorization, not content-type


class TestBasicAuthentication:
    """Test Basic authentication parsing edge cases"""

    def test_basic_auth_success(self):
        """Test successful Basic auth parsing"""
        mock_request = Mock()
        mock_request.url = "https://example.com"
        mock_request.method = "GET"
        mock_request.headers = {
            "authorization": "Basic dXNlcjpwYXNz"
        }  # user:pass in base64

        request = Request(mock_request)
        auth = request.basic_auth()

        assert auth == ("user", "pass")

    def test_basic_auth_no_auth_header(self):
        """Test Basic auth when no authorization header"""
        mock_request = Mock()
        mock_request.url = "https://example.com"
        mock_request.method = "GET"
        mock_request.headers = {}

        request = Request(mock_request)
        auth = request.basic_auth()

        assert auth is None

    def test_basic_auth_not_basic(self):
        """Test Basic auth when authorization is not Basic"""
        mock_request = Mock()
        mock_request.url = "https://example.com"
        mock_request.method = "GET"
        mock_request.headers = {"authorization": "Bearer token123"}

        request = Request(mock_request)
        auth = request.basic_auth()

        assert auth is None

    def test_basic_auth_invalid_base64(self):
        """Test Basic auth with invalid base64 encoding"""
        mock_request = Mock()
        mock_request.url = "https://example.com"
        mock_request.method = "GET"
        mock_request.headers = {"authorization": "Basic invalid!!!base64"}

        request = Request(mock_request)
        auth = request.basic_auth()

        # Should handle exception gracefully and return None
        assert auth is None

    def test_basic_auth_no_colon(self):
        """Test Basic auth when decoded value has no colon separator"""
        mock_request = Mock()
        mock_request.url = "https://example.com"
        mock_request.method = "GET"
        # "useronly" in base64
        mock_request.headers = {"authorization": "Basic dXNlcm9ubHk="}

        request = Request(mock_request)
        auth = request.basic_auth()

        # Should return None when no colon separator
        assert auth is None


class TestRequestBodyHandling:
    """Test request body handling methods"""

    def test_body_method_delegates_to_text(self):
        """Test body() method delegates to text()"""
        mock_request = Mock()
        mock_request.url = "https://example.com"
        mock_request.method = "POST"
        mock_request.headers = {}

        # Mock the raw request to have text() method
        async def mock_text():
            return "test body content"

        mock_request.text = mock_text

        request = Request(mock_request)

        # body() should delegate to text()
        import asyncio

        result = asyncio.run(request.body())
        assert result == "test body content"


class TestHeaderExtractionErrorHandling:
    """Test header extraction error handling"""

    def test_headers_attribute_error_handling(self):
        """Test Request handles missing headers attribute gracefully"""
        mock_request = Mock()
        mock_request.url = "https://example.com"
        mock_request.method = "GET"
        # Remove headers attribute to trigger AttributeError
        del mock_request.headers

        # Should not raise exception, just use empty headers
        request = Request(mock_request)
        assert isinstance(request._headers, dict)
        assert len(request._headers) == 0


class TestPathParameterMethods:
    """Test path parameter helper methods"""

    def test_path_param_missing_parameter(self):
        """Test path_param with missing parameter returns default"""
        mock_request = Mock()
        mock_request.url = "https://example.com/users/123"
        mock_request.method = "GET"
        mock_request.headers = {}

        # No path_params provided
        request = Request(mock_request)

        # Should return None for missing parameter
        result = request.path_param("id")
        assert result is None

        # Should return custom default
        result = request.path_param("id", "default_value")
        assert result == "default_value"

    def test_path_param_int_invalid_conversion(self):
        """Test path_param_int with value that cannot be converted"""
        mock_request = Mock()
        mock_request.url = "https://example.com/users/abc"
        mock_request.method = "GET"
        mock_request.headers = {}

        request = Request(mock_request, path_params={"id": "not-a-number"})

        # Should raise HTTPError with chained exception
        from kinglet.http import HTTPError

        with pytest.raises(HTTPError) as exc_info:
            request.path_param_int("id")

        assert exc_info.value.status_code == 400
        assert "id" in str(exc_info.value.message)
