"""
Tests for Kinglet router functionality
"""
from kinglet import Route, Router


class TestRoute:
    """Test Route class"""

    def test_route_creation(self):
        """Test basic route creation"""
        def handler():
            pass

        route = Route("/api/test", handler, ["GET"])
        assert route.path == "/api/test"
        assert route.handler == handler
        assert route.methods == ["GET"]

    def test_route_methods_normalization(self):
        """Test that methods are normalized to uppercase"""
        def handler():
            pass

        route = Route("/api/test", handler, ["get", "Post", "PUT"])
        assert route.methods == ["GET", "POST", "PUT"]

    def test_simple_path_matching(self):
        """Test matching simple paths"""
        def handler():
            pass

        route = Route("/api/test", handler, ["GET"])

        # Should match
        matches, params = route.matches("GET", "/api/test")
        assert matches is True
        assert params == {}

        # Should not match wrong path
        matches, params = route.matches("GET", "/api/other")
        assert matches is False
        assert params == {}

        # Should not match wrong method
        matches, params = route.matches("POST", "/api/test")
        assert matches is False
        assert params == {}

    def test_path_parameters(self):
        """Test path parameter extraction"""
        def handler():
            pass

        route = Route("/api/users/{id}", handler, ["GET"])

        # Should match and extract parameter
        matches, params = route.matches("GET", "/api/users/123")
        assert matches is True
        assert params == {"id": "123"}

        # Should not match incomplete path
        matches, params = route.matches("GET", "/api/users/")
        assert matches is False

    def test_multiple_path_parameters(self):
        """Test multiple path parameters"""
        def handler():
            pass

        route = Route("/api/users/{user_id}/posts/{post_id}", handler, ["GET"])

        matches, params = route.matches("GET", "/api/users/123/posts/456")
        assert matches is True
        assert params == {"user_id": "123", "post_id": "456"}

    def test_typed_path_parameters(self):
        """Test typed path parameters"""
        def handler():
            pass

        route = Route("/api/users/{id:int}/profile/{slug:str}", handler, ["GET"])

        # Should match integers and strings
        matches, params = route.matches("GET", "/api/users/123/profile/john-doe")
        assert matches is True
        assert params == {"id": "123", "slug": "john-doe"}

        # Should not match non-integers for int type
        matches, params = route.matches("GET", "/api/users/abc/profile/john-doe")
        assert matches is False


class TestRouter:
    """Test Router class"""

    def test_router_creation(self):
        """Test router creation"""
        router = Router()
        assert len(router.routes) == 0
        assert len(router.sub_routers) == 0

    def test_route_decorator(self):
        """Test route decorator functionality"""
        router = Router()

        @router.route("/api/test", ["GET", "POST"])
        def test_handler():
            return {"message": "test"}

        assert len(router.routes) == 1
        route = router.routes[0]
        assert route.path == "/api/test"
        assert route.methods == ["GET", "POST"]
        assert route.handler == test_handler

    def test_method_decorators(self):
        """Test HTTP method decorators"""
        router = Router()

        @router.get("/get-test")
        def get_handler():
            pass

        @router.post("/post-test")
        def post_handler():
            pass

        @router.put("/put-test")
        def put_handler():
            pass

        @router.delete("/delete-test")
        def delete_handler():
            pass

        @router.head("/head-test")
        def head_handler():
            pass

        assert len(router.routes) == 5

        # Check methods
        assert router.routes[0].methods == ["GET"]
        assert router.routes[1].methods == ["POST"]
        assert router.routes[2].methods == ["PUT"]
        assert router.routes[3].methods == ["DELETE"]
        assert router.routes[4].methods == ["HEAD"]

    def test_route_resolution(self):
        """Test route resolution"""
        router = Router()

        @router.get("/api/users")
        def list_users():
            return {"users": []}

        @router.get("/api/users/{id}")
        def get_user():
            return {"user": {}}

        # Test exact match
        handler, params = router.resolve("GET", "/api/users")
        assert handler == list_users
        assert params == {}

        # Test parameter match
        handler, params = router.resolve("GET", "/api/users/123")
        assert handler == get_user
        assert params == {"id": "123"}

        # Test no match
        handler, params = router.resolve("GET", "/api/unknown")
        assert handler is None
        assert params == {}

    def test_sub_routers(self):
        """Test sub-router functionality"""
        main_router = Router()
        api_router = Router()

        @api_router.get("/users")
        def list_users():
            return {"users": []}

        @api_router.get("/users/{id}")
        def get_user():
            return {"user": {}}

        main_router.include_router("/api/v1", api_router)

        # Test sub-router resolution
        handler, params = main_router.resolve("GET", "/api/v1/users")
        assert handler == list_users
        assert params == {}

        handler, params = main_router.resolve("GET", "/api/v1/users/123")
        assert handler == get_user
        assert params == {"id": "123"}

        # Test that direct paths still don't match
        handler, params = main_router.resolve("GET", "/users")
        assert handler is None

    def test_prefix_normalization(self):
        """Test that prefixes are normalized correctly"""
        main_router = Router()
        sub_router = Router()

        @sub_router.get("/test")
        def test_handler():
            return {"test": True}

        # Test various prefix formats
        main_router.include_router("api/v1/", sub_router)

        handler, params = main_router.resolve("GET", "/api/v1/test")
        assert handler == test_handler

    def test_get_routes(self):
        """Test route listing functionality"""
        router = Router()

        @router.get("/api/users")
        def list_users():
            pass

        @router.post("/api/users")
        def create_user():
            pass

        routes = router.get_routes()
        assert len(routes) == 2

        # Check route information
        paths = [route[0] for route in routes]
        assert "/api/users" in paths

        methods_lists = [route[1] for route in routes]
        assert ["GET"] in methods_lists
        assert ["POST"] in methods_lists
