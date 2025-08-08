"""
Tests for Kinglet Request wrapper
"""
import pytest
import json
from unittest.mock import Mock, AsyncMock
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
    
    
    
    
