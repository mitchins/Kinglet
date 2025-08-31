"""
Tests for kinglet.middleware module
"""

from unittest.mock import Mock

import pytest

from kinglet.http import Response
from kinglet.middleware import (
    CorsMiddleware,
    Middleware,
    ORMErrorMiddleware,
    TimingMiddleware,
    create_global_error_boundary,
)
from kinglet.orm_errors import ValidationError


class TestCorsMiddleware:
    """Test CORS middleware functionality"""

    @pytest.mark.asyncio
    async def test_options_preflight_request(self):
        """Test OPTIONS preflight request handling"""
        middleware = CorsMiddleware()

        # Mock request
        request = Mock()
        request.method = "OPTIONS"

        result = await middleware.process_request(request)

        assert isinstance(result, Response)
        assert result.status == 200
        assert result.headers["Access-Control-Allow-Origin"] == "*"

    @pytest.mark.asyncio
    async def test_non_options_request(self):
        """Test non-OPTIONS request passes through"""
        middleware = CorsMiddleware()

        request = Mock()
        request.method = "POST"

        result = await middleware.process_request(request)
        assert result is None

    @pytest.mark.asyncio
    async def test_process_response_dict(self):
        """Test response processing with dict response"""
        middleware = CorsMiddleware()

        request = Mock()
        response = {"data": "test"}

        result = await middleware.process_response(request, response)

        assert isinstance(result, Response)
        assert result.headers["Access-Control-Allow-Origin"] == "*"

    @pytest.mark.asyncio
    async def test_process_response_non_response_object(self):
        """Test response processing with non-Response object"""
        middleware = CorsMiddleware()

        request = Mock()
        response = "string response"

        result = await middleware.process_response(request, response)

        # Should return original response if can't convert
        assert result == "string response"


class TestTimingMiddleware:
    """Test timing middleware functionality"""

    @pytest.mark.asyncio
    async def test_process_request_sets_start_time(self):
        """Test that process_request sets start time"""
        middleware = TimingMiddleware()

        request = Mock()
        result = await middleware.process_request(request)

        assert result is None
        assert hasattr(request, "_start_time")

    @pytest.mark.asyncio
    async def test_process_response_adds_timing_header(self):
        """Test that process_response adds timing header"""
        middleware = TimingMiddleware()

        request = Mock()
        request._start_time = 0.0  # Mock start time

        response = Mock()
        response.header = Mock()

        result = await middleware.process_response(request, response)

        assert result == response
        response.header.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_response_no_start_time(self):
        """Test response processing when no start time"""
        middleware = TimingMiddleware()

        request = Mock(spec=[])  # No _start_time attribute

        response = Mock()
        result = await middleware.process_response(request, response)

        assert result == response

    @pytest.mark.asyncio
    async def test_process_response_no_header_method(self):
        """Test response processing when response has no header method"""
        middleware = TimingMiddleware()

        request = Mock()
        request._start_time = 0.0

        response = Mock(spec=[])  # No header method

        result = await middleware.process_response(request, response)

        assert result == response


class TestORMErrorMiddleware:
    """Test ORM error middleware functionality"""

    def test_middleware_initialization(self):
        """Test middleware initialization with defaults"""
        middleware = ORMErrorMiddleware()

        assert not middleware.is_prod
        assert middleware.correlation_header == "X-Request-Id"
        assert not middleware.include_trace

    def test_middleware_initialization_with_params(self):
        """Test middleware initialization with custom parameters"""
        middleware = ORMErrorMiddleware(
            is_prod=True, correlation_header="X-Trace-Id", include_trace=True
        )

        assert middleware.is_prod
        assert middleware.correlation_header == "X-Trace-Id"
        assert middleware.include_trace

    @pytest.mark.asyncio
    async def test_process_request_passthrough(self):
        """Test that process_request returns None"""
        middleware = ORMErrorMiddleware()
        request = Mock()

        result = await middleware.process_request(request)
        assert result is None

    @pytest.mark.asyncio
    async def test_process_response_passthrough(self):
        """Test that process_response returns response unchanged"""
        middleware = ORMErrorMiddleware()
        request = Mock()
        response = Mock()

        result = await middleware.process_response(request, response)
        assert result == response

    @pytest.mark.asyncio
    async def test_error_boundary_orm_error(self):
        """Test error boundary with ORM error"""
        middleware = ORMErrorMiddleware()

        # Create mock handler that raises ORM error
        async def mock_handler(request, env):
            raise ValidationError("email", "Invalid email format")

        wrapped_handler = middleware.create_error_boundary(mock_handler)

        request = Mock()
        request.headers = {}
        env = Mock()

        result = await wrapped_handler(request, env)

        assert isinstance(result, Response)
        assert result.status == 422
        assert result.headers["Content-Type"] == "application/problem+json"

    @pytest.mark.asyncio
    async def test_error_boundary_generic_error(self):
        """Test error boundary with generic error"""
        middleware = ORMErrorMiddleware()

        async def mock_handler(request, env):
            raise ValueError("Something went wrong")

        wrapped_handler = middleware.create_error_boundary(mock_handler)

        request = Mock()
        request.headers = {}
        env = Mock()

        result = await wrapped_handler(request, env)

        assert isinstance(result, Response)
        assert result.status == 500
        assert result.headers["Content-Type"] == "application/problem+json"

    @pytest.mark.asyncio
    async def test_error_boundary_with_correlation_id(self):
        """Test error boundary with correlation ID in headers"""
        middleware = ORMErrorMiddleware(correlation_header="X-Request-Id")

        async def mock_handler(request, env):
            raise ValidationError("email", "Invalid email")

        wrapped_handler = middleware.create_error_boundary(mock_handler)

        request = Mock()
        request.headers = {"X-Request-Id": "test-123"}
        env = Mock()

        result = await wrapped_handler(request, env)

        assert isinstance(result, Response)
        assert "instance" in result.content

    @pytest.mark.asyncio
    async def test_error_boundary_with_trace(self):
        """Test error boundary with stack trace in dev mode"""
        middleware = ORMErrorMiddleware(is_prod=False, include_trace=True)

        async def mock_handler(request, env):
            raise ValidationError("email", "Invalid email")

        wrapped_handler = middleware.create_error_boundary(mock_handler)

        request = Mock()
        request.headers = {}
        env = Mock()

        result = await wrapped_handler(request, env)

        assert isinstance(result, Response)
        assert "trace" in result.content


def test_create_global_error_boundary():
    """Test global error boundary factory function"""
    boundary = create_global_error_boundary(
        is_prod=True, correlation_header="X-Custom-Id"
    )

    assert callable(boundary)


class TestBaseMiddleware:
    """Test abstract Middleware base class"""

    @pytest.mark.asyncio
    async def test_abstract_middleware_methods(self):
        """Test abstract middleware methods can be implemented"""

        class TestMiddleware(Middleware):
            async def process_request(self, request):
                # This covers line 18 (pass statement)
                return None

            async def process_response(self, request, response):
                # This covers line 23 (pass statement)
                return response

        middleware = TestMiddleware()
        request = Mock()
        response = Mock()

        # Test both methods
        result_req = await middleware.process_request(request)
        assert result_req is None

        result_resp = await middleware.process_response(request, response)
        assert result_resp == response
