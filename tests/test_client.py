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
        birth_year = data.get("birth_year")

        if not birth_year:
            return Response({"error": "Birth year required"}, status=400)

        age = 2025 - birth_year
        is_adult = age >= 18

        return {"success": True, "is_adult": is_adult, "age": age}

    client = TestClient(app)

    # Test valid request
    status, headers, body = client.request(
        "POST", "/api/auth/verify-age", json={"birth_year": 1990}
    )
    assert status == 200

    # Test invalid request
    status, headers, body = client.request("POST", "/api/auth/verify-age", json={})
    assert status == 400


def test_testclient_with_mock_database():
    """Test TestClient with mock database integration

    This test demonstrates how to use MockD1Database with TestClient.
    Since MockD1Database uses real SQL execution, we need to set up
    the schema and test data before running the test.
    """
    import asyncio

    from kinglet import MockD1Database

    app = Kinglet()

    @app.get("/users/{id}")
    async def get_user(request):
        user_id = request.path_param("id")

        # Query the mock database
        query = "SELECT * FROM users WHERE id = ?"
        result = await request.env.DB.prepare(query).bind(user_id).first()

        if result is None:
            return {"user": None, "id": user_id}

        return {"user": result, "id": user_id}

    # Set up mock database with test data (sync setup using new event loop)
    db = MockD1Database()

    async def setup():
        await db.exec("CREATE TABLE users (id TEXT PRIMARY KEY, name TEXT)")
        await (
            db.prepare("INSERT INTO users (id, name) VALUES (?, ?)")
            .bind("123", "Test User")
            .run()
        )

    asyncio.new_event_loop().run_until_complete(setup())

    client = TestClient(app, env={"DB": db})
    status, headers, body = client.request("GET", "/users/123")

    assert status == 200
    # Body is JSON string, parse it
    import json

    data = json.loads(body)
    assert data["user"]["name"] == "Test User"
    assert data["id"] == "123"


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
            "custom": getattr(request.env, "CUSTOM_VAR", "not_set"),
        }

    client = TestClient(app, env={"CUSTOM_VAR": "test_value"})
    status, headers, body = client.request("GET", "/env")

    assert status == 200
    # Should include both default and custom env vars


if __name__ == "__main__":
    pytest.main([__file__])
