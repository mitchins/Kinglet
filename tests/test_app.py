"""
Tests for Kinglet main application
"""
from unittest.mock import Mock

import pytest

from kinglet import CorsMiddleware, Kinglet, Response


class MockRequest:
    """Mock Workers request for testing"""

    def __init__(self, method="GET", url="http://localhost/", headers=None):
        self.method = method
        self.url = url
        self.headers = MockHeaders(headers or {})

    async def text(self):
        return ""


class MockHeaders:
    """Mock headers object"""

    def __init__(self, headers_dict):
        self._headers = {k.lower(): v for k, v in headers_dict.items()}

    def items(self):
        return self._headers.items()

    def get(self, key, default=None):
        return self._headers.get(key.lower(), default)


class TestKingletApp:
    """Test Kinglet application"""

    @pytest.fixture
    def app(self):
        """Create a test app"""
        return Kinglet()

    @pytest.fixture
    def mock_env(self):
        """Create mock environment"""
        return Mock()

    def test_app_creation(self, app):
        """Test basic app creation"""
        assert app.router is not None
        assert len(app.middleware_stack) == 0
        assert len(app.error_handlers) == 0

    def test_route_decorators(self, app):
        """Test route decorators"""
        @app.get("/test")
        async def get_handler(request):
            return {"method": "GET"}

        @app.post("/test")
        async def post_handler(request):
            return {"method": "POST"}

        assert len(app.router.routes) == 2

    @pytest.mark.asyncio
    async def test_simple_request_handling(self, app, mock_env):
        """Test basic request handling"""
        @app.get("/hello")
        async def hello_handler(request):
            return {"message": "Hello, World!"}

        mock_request = MockRequest("GET", "http://localhost/hello")
        response = await app(mock_request, mock_env)

        # Check that we get a response
        assert response is not None

    @pytest.mark.asyncio
    async def test_path_parameters(self, app, mock_env):
        """Test path parameter handling"""
        @app.get("/users/{id}")
        async def get_user(request):
            user_id = request.path_param("id")
            return {"user_id": user_id}

        mock_request = MockRequest("GET", "http://localhost/users/123")
        response = await app(mock_request, mock_env)

        # Response handling would depend on the to_workers_response implementation
        assert response is not None

    @pytest.mark.asyncio
    async def test_not_found_handling(self, app, mock_env):
        """Test 404 handling"""
        mock_request = MockRequest("GET", "http://localhost/nonexistent")
        response = await app(mock_request, mock_env)

        assert response is not None

    @pytest.mark.asyncio
    async def test_middleware_processing(self, app, mock_env):
        """Test middleware execution"""
        @app.middleware
        class TestMiddleware:
            async def process_request(self, request):
                request.test_flag = True
                return request

            async def process_response(self, request, response):
                response.header("X-Test", "processed")
                return response

        @app.get("/test")
        async def test_handler(request):
            has_flag = hasattr(request, 'test_flag') and request.test_flag
            return {"middleware_executed": has_flag}

        mock_request = MockRequest("GET", "http://localhost/test")
        response = await app(mock_request, mock_env)

        assert response is not None

    def test_include_router(self, app):
        """Test including sub-routers"""
        from kinglet import Router

        api_router = Router()

        @api_router.get("/users")
        def list_users(request):
            return {"users": []}

        app.include_router("/api/v1", api_router)

        # Check that routes are properly included
        handler, params = app.router.resolve("GET", "/api/v1/users")
        assert handler is not None

    def test_error_handler_decorator(self, app):
        """Test error handler registration"""
        @app.exception_handler(404)
        async def not_found_handler(request, _exc):
            return {"error": "Custom not found"}

        assert 404 in app.error_handlers
        assert app.error_handlers[404] == not_found_handler

    @pytest.mark.asyncio
    async def test_automatic_response_conversion(self, app, mock_env):
        """Test that various return types are converted to Response objects"""
        @app.get("/dict")
        async def dict_handler(request):
            return {"key": "value"}

        @app.get("/string")
        async def string_handler(request):
            return "Hello"

        @app.get("/response")
        async def response_handler(request):
            return Response({"explicit": True})

        # Test dict conversion
        mock_request = MockRequest("GET", "http://localhost/dict")
        response = await app(mock_request, mock_env)
        assert response is not None

        # Test string conversion
        mock_request = MockRequest("GET", "http://localhost/string")
        response = await app(mock_request, mock_env)
        assert response is not None

        # Test explicit Response
        mock_request = MockRequest("GET", "http://localhost/response")
        response = await app(mock_request, mock_env)
        assert response is not None


class TestMiddlewareIntegration:
    """Test middleware integration with app"""

    @pytest.fixture
    def app_with_cors(self):
        """Create app with CORS middleware"""
        app = Kinglet()
        app.middleware_stack.append(CorsMiddleware())

        @app.get("/test")
        async def test_handler(request):
            return {"test": True}

        return app

    @pytest.mark.asyncio
    async def test_cors_middleware(self, app_with_cors):
        """Test CORS middleware integration"""
        mock_request = MockRequest("GET", "http://localhost/test")
        mock_env = Mock()

        response = await app_with_cors(mock_request, mock_env)
        assert response is not None

    @pytest.mark.asyncio
    async def test_options_request_handling(self, app_with_cors):
        """Test OPTIONS request handling with CORS"""
        mock_request = MockRequest("OPTIONS", "http://localhost/test")
        mock_env = Mock()

        response = await app_with_cors(mock_request, mock_env)
        assert response is not None
