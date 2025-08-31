"""
Tests for the main kinglet module imports and version info.
This ensures the main module can be imported and all exports are accessible.
"""


class TestKingletModuleImports:
    """Test that the main kinglet module imports work correctly"""

    def test_core_imports(self):
        """Test core components can be imported"""
        from kinglet import Kinglet, Route, Router

        assert Kinglet is not None
        assert Route is not None
        assert Router is not None

        # Should be classes
        assert isinstance(Kinglet, type)
        assert isinstance(Route, type)
        assert isinstance(Router, type)

    def test_http_imports(self):
        """Test HTTP components can be imported"""
        from kinglet import Request, Response, error_response, generate_request_id

        assert Request is not None
        assert Response is not None
        assert error_response is not None
        assert generate_request_id is not None

        # Should be callable
        assert callable(error_response)
        assert callable(generate_request_id)

    def test_exception_imports(self):
        """Test exception classes can be imported"""
        from kinglet import DevOnlyError, GeoRestrictedError, HTTPError

        assert HTTPError is not None
        assert GeoRestrictedError is not None
        assert DevOnlyError is not None

        # Should be exception classes
        assert issubclass(HTTPError, Exception)
        assert issubclass(GeoRestrictedError, Exception)
        assert issubclass(DevOnlyError, Exception)

    def test_storage_imports(self):
        """Test storage utility imports"""
        from kinglet import (
            d1_unwrap,
            d1_unwrap_results,
            r2_delete,
            r2_get_content_info,
            r2_get_metadata,
            r2_list,
            r2_put,
        )

        storage_functions = [
            d1_unwrap,
            d1_unwrap_results,
            r2_get_metadata,
            r2_get_content_info,
            r2_put,
            r2_delete,
            r2_list,
        ]

        for func in storage_functions:
            assert func is not None
            assert callable(func)

    def test_testing_imports(self):
        """Test testing utility imports"""
        from kinglet import TestClient

        assert TestClient is not None
        assert isinstance(TestClient, type)

    def test_middleware_imports(self):
        """Test middleware imports"""
        from kinglet import CorsMiddleware, Middleware, TimingMiddleware

        assert Middleware is not None
        assert CorsMiddleware is not None
        assert TimingMiddleware is not None

        # Should be classes
        assert isinstance(Middleware, type)
        assert isinstance(CorsMiddleware, type)
        assert isinstance(TimingMiddleware, type)

    def test_decorator_imports(self):
        """Test decorator imports"""
        from kinglet import (
            geo_restrict,
            require_dev,
            require_field,
            validate_json_body,
            wrap_exceptions,
        )

        decorators = [
            wrap_exceptions,
            require_dev,
            geo_restrict,
            validate_json_body,
            require_field,
        ]

        for decorator in decorators:
            assert decorator is not None
            assert callable(decorator)

    def test_version_info(self):
        """Test version and author information"""
        import kinglet

        assert hasattr(kinglet, "__version__")
        assert hasattr(kinglet, "__author__")

        assert isinstance(kinglet.__version__, str)
        assert isinstance(kinglet.__author__, str)

        assert len(kinglet.__version__) > 0
        assert len(kinglet.__author__) > 0

        # Version should be in semver-like format
        version_parts = kinglet.__version__.split(".")
        assert len(version_parts) >= 2  # At least major.minor

    def test_all_exports_defined(self):
        """Test that __all__ is properly defined"""
        import kinglet

        assert hasattr(kinglet, "__all__")
        assert isinstance(kinglet.__all__, list)
        assert len(kinglet.__all__) > 0

        # All items in __all__ should be strings
        for item in kinglet.__all__:
            assert isinstance(item, str)
            assert len(item) > 0

    def test_all_exports_exist(self):
        """Test that all items in __all__ actually exist in the module"""
        import kinglet

        for item_name in kinglet.__all__:
            assert hasattr(
                kinglet, item_name
            ), f"'{item_name}' is in __all__ but not found in module"

            item = getattr(kinglet, item_name)
            assert item is not None, f"'{item_name}' exists but is None"


class TestKingletModuleUsage:
    """Test basic usage patterns of imported components"""

    def test_basic_app_creation(self):
        """Test basic Kinglet app can be created"""
        from kinglet import Kinglet

        app = Kinglet()
        assert app is not None

        # Should have basic attributes
        assert hasattr(app, "route")
        assert hasattr(app, "get")
        assert hasattr(app, "post")

    def test_response_creation(self):
        """Test Response can be created"""
        from kinglet import Response

        response = Response("Hello")
        assert response is not None

        # Should have basic properties
        assert response.content == "Hello"
        assert response.status == 200

    def test_error_response_function(self):
        """Test error_response utility function"""
        from kinglet import error_response

        response = error_response("Test error", 400)
        assert response is not None
        assert response.status == 400

    def test_router_creation(self):
        """Test Router can be created"""
        from kinglet import Router

        router = Router()
        assert router is not None

        # Should have routing methods
        assert hasattr(router, "route")
        assert hasattr(router, "get")
        assert hasattr(router, "post")

    def test_test_client_creation(self):
        """Test TestClient can be created"""
        from kinglet import Kinglet, TestClient

        app = Kinglet()
        client = TestClient(app)
        assert client is not None

        # Should have request method
        assert hasattr(client, "request")
        assert callable(client.request)


class TestKingletBackwardsCompatibility:
    """Test that the kinglet module maintains backwards compatibility"""

    def test_old_import_patterns_work(self):
        """Test that common import patterns from older versions work"""
        # These should all work without errors
        from kinglet import (
            Kinglet,
            Response,
            Router,
        )

        # Create instances to ensure they work
        app = Kinglet()
        router = Router()
        response = Response("test")

        assert app is not None
        assert router is not None
        assert response is not None

    def test_star_import_works(self):
        """Test that star imports work (though not recommended)"""
        # This should not raise an error
        namespace = {}
        exec("from kinglet import *", namespace)

        # Should have imported the main components
        assert "Kinglet" in namespace
        assert "Response" in namespace
        assert "Router" in namespace
