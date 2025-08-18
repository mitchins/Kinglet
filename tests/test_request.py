"""
Tests for Kinglet Request wrapper
"""
import json
from unittest.mock import Mock

import pytest

from kinglet import Request


class MockHeaders:
    """Mock headers object"""

    def __init__(self, headers_dict):
        self._headers = {k.lower(): v for k, v in headers_dict.items()}

    def items(self):
        return self._headers.items()

    def get(self, key, default=None):
        return self._headers.get(key.lower(), default)


class MockWorkerRequest:
    """Mock Workers request object"""

    def __init__(self, method="GET", url="http://localhost/", headers=None, body=""):
        self.method = method
        self.url = url
        self.headers = MockHeaders(headers or {})
        self._body = body

    async def text(self):
        return self._body

    async def formData(self):
        # Mock form data parsing
        if self._body:
            pairs = self._body.split('&')
            form_data = {}
            for pair in pairs:
                if '=' in pair:
                    key, value = pair.split('=', 1)
                    form_data[key] = value
            return form_data
        return {}


class TestRequest:
    """Test Request wrapper"""

    @pytest.fixture
    def mock_env(self):
        return Mock()

    def test_basic_request_creation(self, mock_env):
        """Test basic request creation"""
        raw_request = MockWorkerRequest("GET", "http://localhost/api/test")
        request = Request(raw_request, mock_env)

        assert request.method == "GET"
        assert request.path == "/api/test"
        assert request.url == "http://localhost/api/test"
        assert request.env == mock_env

    def test_url_parsing(self, mock_env):
        """Test URL component parsing"""
        raw_request = MockWorkerRequest(
            "GET",
            "http://localhost:8080/api/users?page=1&limit=10#section1"
        )
        request = Request(raw_request, mock_env)

        assert request.path == "/api/users"
        assert request.query_string == "page=1&limit=10"

    def test_query_parameter_parsing(self, mock_env):
        """Test query parameter parsing"""
        raw_request = MockWorkerRequest(
            "GET",
            "http://localhost/search?q=test&category=books&category=movies&limit=10"
        )
        request = Request(raw_request, mock_env)

        # Test query() for single values
        assert request.query("q") == "test"
        assert request.query("limit") == "10"
        assert request.query("nonexistent") is None
        assert request.query("nonexistent", "default") == "default"

    def test_header_access(self, mock_env):
        """Test header access"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer token123",
            "X-Custom-Header": "value"
        }

        raw_request = MockWorkerRequest("POST", "http://localhost/", headers)
        request = Request(raw_request, mock_env)

        # Test case-insensitive access
        assert request.header("content-type") == "application/json"
        assert request.header("Content-Type") == "application/json"
        assert request.header("CONTENT-TYPE") == "application/json"

        assert request.header("authorization") == "Bearer token123"
        assert request.header("x-custom-header") == "value"

        # Test default values
        assert request.header("nonexistent") is None
        assert request.header("nonexistent", "default") == "default"

    @pytest.mark.asyncio
    async def test_request_body(self, mock_env):
        """Test request body access"""
        body_content = "test body content"
        raw_request = MockWorkerRequest("POST", "http://localhost/", body=body_content)
        request = Request(raw_request, mock_env)

        body = await request.body()
        assert body == body_content

        # Test caching - second call should return cached value
        body2 = await request.body()
        assert body2 == body_content

    @pytest.mark.asyncio
    async def test_json_parsing(self, mock_env):
        """Test JSON body parsing"""
        json_data = {"name": "test", "value": 123}
        json_body = json.dumps(json_data)

        headers = {"Content-Type": "application/json"}
        raw_request = MockWorkerRequest("POST", "http://localhost/", headers, json_body)
        request = Request(raw_request, mock_env)

        parsed_json = await request.json()
        assert parsed_json == json_data

        # JSON parsing works

    @pytest.mark.asyncio
    async def test_invalid_json_parsing(self, mock_env):
        """Test invalid JSON handling"""
        invalid_json = "{ invalid json"
        headers = {"Content-Type": "application/json"}
        raw_request = MockWorkerRequest("POST", "http://localhost/", headers, invalid_json)
        request = Request(raw_request, mock_env)

        parsed_json = await request.json()
        assert parsed_json is None

    @pytest.mark.asyncio
    async def test_empty_json_parsing(self, mock_env):
        """Test empty body JSON parsing"""
        raw_request = MockWorkerRequest("POST", "http://localhost/")
        request = Request(raw_request, mock_env)

        parsed_json = await request.json()
        assert parsed_json is None

    def test_path_parameters(self, mock_env):
        """Test path parameter access"""
        raw_request = MockWorkerRequest("GET", "http://localhost/users/123")
        request = Request(raw_request, mock_env)

        # Path params are set by the router
        request.path_params = {"id": "123", "slug": "test-slug"}

        assert request.path_param("id") == "123"
        assert request.path_param("slug") == "test-slug"
        assert request.path_param("nonexistent") is None
        assert request.path_param("nonexistent", "default") == "default"


class TestJsProxyConversion:
    """Test JsProxy to Python dict conversion in request.json()"""

    @pytest.fixture
    def mock_env(self):
        return Mock()

    class MockJsProxy:
        """Mock JsProxy object for testing"""

        def __init__(self, data):
            self._data = data

        def to_py(self):
            """Mock to_py() method that converts to Python dict"""
            return self._data

        def __getitem__(self, key):
            return self._data[key]

        def __iter__(self):
            return iter(self._data)

    class MockJsProxyWithoutToPy:
        """Mock JsProxy object without to_py() method"""

        def __init__(self, data):
            self._data = data
            # Mock Object.keys functionality
            self.Object = type('Object', (), {
                'keys': lambda obj: list(data.keys())
            })()

        def __getitem__(self, key):
            return self._data[key]

        def __iter__(self):
            return iter(self._data)

    class MockWorkerRequestWithJsProxy:
        """Mock Workers request with JsProxy response"""

        def __init__(self, method="POST", url="http://localhost/", headers=None, js_proxy=None):
            self.method = method
            self.url = url
            self.headers = MockHeaders(headers or {})
            self._js_proxy = js_proxy

        async def json(self):
            """Return the mock JsProxy object"""
            return self._js_proxy

        async def text(self):
            return ""

    @pytest.mark.asyncio
    async def test_jsproxy_conversion_with_to_py(self, mock_env):
        """Test JsProxy conversion using to_py() method"""
        test_data = {"name": "test", "value": 123, "nested": {"key": "value"}}
        js_proxy = self.MockJsProxy(test_data)

        raw_request = self.MockWorkerRequestWithJsProxy(js_proxy=js_proxy)
        request = Request(raw_request, mock_env)

        # Test default behavior (convert=True)
        result = await request.json()
        assert result == test_data
        assert isinstance(result, dict)

        # Test that we can access dict methods
        assert result.get("name") == "test"
        assert result["value"] == 123

    @pytest.mark.asyncio
    async def test_jsproxy_conversion_disabled(self, mock_env):
        """Test JsProxy conversion can be disabled"""
        test_data = {"name": "test", "value": 123}
        js_proxy = self.MockJsProxy(test_data)

        raw_request = self.MockWorkerRequestWithJsProxy(js_proxy=js_proxy)
        request = Request(raw_request, mock_env)

        # Test with convert=False
        result = await request.json(convert=False)
        assert result is js_proxy  # Should return the original JsProxy
        assert not isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_jsproxy_without_to_py_fallback(self, mock_env):
        """Test fallback for JsProxy objects without to_py() method"""
        test_data = {"name": "test", "value": 123}
        js_proxy = self.MockJsProxyWithoutToPy(test_data)

        raw_request = self.MockWorkerRequestWithJsProxy(js_proxy=js_proxy)
        request = Request(raw_request, mock_env)

        # Should handle JsProxy without to_py() method
        result = await request.json()
        # This should extract the data manually or return the original object
        assert result is not None

    @pytest.mark.asyncio
    async def test_regular_dict_passthrough(self, mock_env):
        """Test that regular Python dicts pass through unchanged"""
        test_data = {"name": "test", "value": 123}

        # Mock request that returns a regular dict (not JsProxy)
        class MockRegularRequest:
            def __init__(self):
                self.method = "POST"
                self.url = "http://localhost/"
                self.headers = MockHeaders({})

            async def json(self):
                return test_data

            async def text(self):
                return ""

        raw_request = MockRegularRequest()
        request = Request(raw_request, mock_env)

        result = await request.json()
        assert result == test_data
        assert isinstance(result, dict)
        assert result.get("name") == "test"

    @pytest.mark.asyncio
    async def test_json_caching_with_convert_parameter(self, mock_env):
        """Test that caching works correctly with convert parameter"""
        test_data = {"name": "test", "cached": True}
        js_proxy = self.MockJsProxy(test_data)

        raw_request = self.MockWorkerRequestWithJsProxy(js_proxy=js_proxy)
        request = Request(raw_request, mock_env)

        # First call with convert=True
        result1 = await request.json(convert=True)
        result2 = await request.json(convert=True)
        assert result1 is result2  # Should return cached value

        # Call with convert=False should return different cached value
        result3 = await request.json(convert=False)
        assert result3 is not result1  # Different cache
        assert result3 is js_proxy  # Should be the original JsProxy

    @pytest.mark.asyncio
    async def test_none_json_handling(self, mock_env):
        """Test handling of None/empty JSON responses"""
        class MockNoneRequest:
            def __init__(self):
                self.method = "POST"
                self.url = "http://localhost/"
                self.headers = MockHeaders({})

            async def json(self):
                return None

            async def text(self):
                return ""

        raw_request = MockNoneRequest()
        request = Request(raw_request, mock_env)

        result = await request.json()
        assert result is None

        # Test with convert=False
        result2 = await request.json(convert=False)
        assert result2 is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
