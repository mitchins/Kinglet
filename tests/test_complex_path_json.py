"""
Test case for JSON parsing bug with complex path patterns
Bug: JSON parsing fails for paths like /prefix/{param}/suffix
"""
import json
import pytest
from kinglet import Kinglet, Response
from kinglet.testing import TestClient


@pytest.fixture
def app():
    """Create test app with both simple and complex path patterns"""
    app = Kinglet()
    
    @app.post("/simple/{slug}")
    async def simple_path(request):
        """Simple path pattern - should work"""
        slug = request.path_param("slug")
        data = await request.json()
        return {"slug": slug, "data": data}
    
    @app.post("/complex/{slug}/test")
    async def complex_path(request):
        """Complex path pattern - currently broken"""
        slug = request.path_param("slug")
        data = await request.json()
        return {"slug": slug, "data": data}
        
    @app.post("/very/complex/{slug}/path/test")
    async def very_complex_path(request):
        """Very complex path pattern - currently broken"""
        slug = request.path_param("slug")
        data = await request.json()
        return {"slug": slug, "data": data}
    
    return app


def test_simple_path_json_parsing(app):
    """Test that JSON parsing works for simple paths"""
    client = TestClient(app)
    
    test_data = {"rating": 5, "title": "Great!"}
    status, headers, body = client.request(
        "POST", "/simple/alien-blaster",
        json=test_data
    )
    
    assert status == 200
    response_data = json.loads(body) if isinstance(body, str) else body
    assert response_data["slug"] == "alien-blaster"
    assert response_data["data"] == test_data


def test_complex_path_json_parsing(app):
    """Test that JSON parsing works for complex paths - THIS CURRENTLY FAILS"""
    client = TestClient(app)
    
    test_data = {"rating": 5, "title": "Great!"}
    status, headers, body = client.request(
        "POST", "/complex/alien-blaster/test",
        json=test_data
    )
    
    assert status == 200
    response_data = json.loads(body) if isinstance(body, str) else body
    assert response_data["slug"] == "alien-blaster"
    # This assertion will fail because data comes back as None
    assert response_data["data"] == test_data


def test_very_complex_path_json_parsing(app):
    """Test that JSON parsing works for very complex paths"""
    client = TestClient(app)
    
    test_data = {"rating": 5, "title": "Great!"}
    status, headers, body = client.request(
        "POST", "/very/complex/alien-blaster/path/test",
        json=test_data
    )
    
    assert status == 200
    response_data = json.loads(body) if isinstance(body, str) else body
    assert response_data["slug"] == "alien-blaster"
    assert response_data["data"] == test_data


def create_test_app():
    """Create test app for manual testing"""
    app = Kinglet()
    
    @app.post("/simple/{slug}")
    async def simple_path(request):
        """Simple path pattern - should work"""
        slug = request.path_param("slug")
        data = await request.json()
        return {"slug": slug, "data": data}
    
    @app.post("/complex/{slug}/test")
    async def complex_path(request):
        """Complex path pattern - currently broken"""
        slug = request.path_param("slug")
        data = await request.json()
        return {"slug": slug, "data": data}
        
    return app


if __name__ == "__main__":
    # Run the test to demonstrate the bug
    app = create_test_app()
    
    print("Testing simple path...")
    try:
        test_simple_path_json_parsing(app)
        print("✅ Simple path works")
    except Exception as e:
        print(f"❌ Simple path fails: {e}")
    
    print("Testing complex path...")
    try:
        test_complex_path_json_parsing(app) 
        print("✅ Complex path works")
    except Exception as e:
        print(f"❌ Complex path fails: {e}")