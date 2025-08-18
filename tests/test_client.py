"""
Test the TestClient for unit testing Kinglet apps
"""
import os
import sys

import pytest

# Add parent directory to path for importing kinglet package
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from kinglet import Kinglet, Response, TestClient


def test_testclient_basic():
    """Test basic TestClient functionality"""
    app = Kinglet()

    @app.get("/hello")
    async def hello(request):
        return {"message": "Hello, World!"}

    client = TestClient(app)
    status, headers, body = client.request("GET", "/hello")

    assert status == 200
    # Note: body parsing depends on Response.to_workers_response implementation


def test_testclient_with_json_request():
    """Test TestClient with JSON request body"""
    app = Kinglet()

    @app.post("/api/auth/verify-age")
    async def verify_age(request):
        data = await request.json()
        birth_year = data.get('birth_year')

        if not birth_year:
            return Response({"error": "Birth year required"}, status=400)

        age = 2025 - birth_year
        is_adult = age >= 18

        return {
            "success": True,
            "is_adult": is_adult,
            "age": age
        }

    client = TestClient(app)

    # Test valid request
    status, headers, body = client.request("POST", "/api/auth/verify-age", json={"birth_year": 1990})
    assert status == 200

    # Test invalid request
    status, headers, body = client.request("POST", "/api/auth/verify-age", json={})
    assert status == 400


def test_testclient_with_mock_database():
    """Test TestClient with mock database integration"""
    app = Kinglet()

    @app.get("/users/{id}")
    async def get_user(request):
        user_id = request.path_param("id")

        # Simulate database query
        query = "SELECT * FROM users WHERE id = ?1"
        result = await request.env.DB.prepare(query).bind(user_id).first()
        user_data = result.to_py()

        return {"user": user_data, "id": user_id}

    client = TestClient(app)
    status, headers, body = client.request("GET", "/users/123")

    assert status == 200
    # Mock database should return test data


def test_testclient_error_handling():
    """Test TestClient error handling"""
    app = Kinglet()

    @app.get("/error")
    async def error_handler(request):
        raise ValueError("Test error")

    client = TestClient(app)
    status, headers, body = client.request("GET", "/error")

    assert status == 500
    assert "error" in body


def test_testclient_environment_injection():
    """Test TestClient with custom environment variables"""
    app = Kinglet()

    @app.get("/env")
    async def env_handler(request):
        return {
            "environment": request.env.ENVIRONMENT,
            "custom": getattr(request.env, 'CUSTOM_VAR', 'not_set')
        }

    client = TestClient(app, env={"CUSTOM_VAR": "test_value"})
    status, headers, body = client.request("GET", "/env")

    assert status == 200
    # Should include both default and custom env vars


if __name__ == "__main__":
    pytest.main([__file__])
