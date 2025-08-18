"""
Tests for Kinglet Response class
"""

import pytest

from kinglet import Response, error_response


class TestResponse:
    """Test Response class"""

    def test_basic_response_creation(self):
        """Test basic response creation"""
        response = Response("Hello, World!")

        assert response.content == "Hello, World!"
        assert response.status == 200
        assert response.headers["Content-Type"] == "text/plain; charset=utf-8"

    def test_json_response_auto_detection(self):
        """Test automatic JSON content type detection"""
        data = {"key": "value"}
        response = Response(data)

        assert response.content == data
        assert response.headers["Content-Type"] == "application/json"

    def test_custom_status_and_headers(self):
        """Test custom status code and headers"""
        headers = {"X-Custom": "value"}
        response = Response("Not Found", status=404, headers=headers)

        assert response.status == 404
        assert response.headers["X-Custom"] == "value"
        assert "Content-Type" in response.headers

    def test_explicit_content_type(self):
        """Test explicit content type override"""
        response = Response("Hello", content_type="text/html")

        assert response.headers["Content-Type"] == "text/html"

    def test_header_chaining(self):
        """Test chainable header method"""
        response = Response("test")
        result = response.header("X-Test", "value")

        assert result is response  # Should return self for chaining
        assert response.headers["X-Test"] == "value"

    def test_cors_chaining(self):
        """Test chainable CORS method"""
        response = Response("test")
        result = response.cors(origin="https://example.com")

        assert result is response  # Should return self for chaining
        assert response.headers["Access-Control-Allow-Origin"] == "https://example.com"
        assert "Access-Control-Allow-Methods" in response.headers
        assert "Access-Control-Allow-Headers" in response.headers


    def test_to_workers_response_import_error(self):
        """Test that to_workers_response handles ImportError gracefully"""
        data = {"message": "test"}
        response = Response(data)

        # Since workers module is not available in test environment,
        # this should raise ImportError which is expected behavior
        with pytest.raises(ImportError):
            response.to_workers_response()

    def test_response_without_workers_conversion(self):
        """Test that Response objects work fine without Workers conversion"""
        response = Response("Hello, World!")

        # Test that the response object itself is valid
        assert response.content == "Hello, World!"
        assert response.status == 200
        assert response.headers["Content-Type"] == "text/plain; charset=utf-8"

        # Test chainable methods work
        chained = response.header("X-Test", "value").cors(origin="https://example.com")
        assert chained is response
        assert response.headers["X-Test"] == "value"
        assert response.headers["Access-Control-Allow-Origin"] == "https://example.com"


class TestConvenienceFunctions:
    """Test convenience response functions"""

    def test_error_response(self):
        """Test error_response function"""
        message = "Something went wrong"
        response = error_response(message, status=500)

        expected_content = {
            "error": message,
            "status_code": 500
        }

        assert response.content == expected_content
        assert response.status == 500
        assert response.headers["Content-Type"] == "application/json"

    def test_default_error_status(self):
        """Test default error status code"""
        response = error_response("Bad request")
        assert response.status == 400
