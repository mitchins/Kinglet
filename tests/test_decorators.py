"""
Tests for Kinglet decorators: exception wrapping, dev-only, and geo-restriction
"""
from kinglet import (
    HTTPError,
    Kinglet,
    TestClient,
    geo_restrict,
    require_dev,
    wrap_exceptions,
)


class TestExceptionWrapping:
    """Test exception wrapping decorator"""

    def test_manual_wrap_exceptions_catches_generic_exceptions(self):
        """Test that wrap_exceptions catches and wraps generic exceptions"""
        app = Kinglet(auto_wrap_exceptions=False)  # Disable global wrapping

        @app.get("/error")
        @wrap_exceptions(step="test_error", expose_details=True)
        async def error_endpoint(request):
            raise ValueError("Something went wrong")

        client = TestClient(app)
        status, headers, body = client.request("GET", "/error")

        assert status == 500
        assert "Something went wrong" in body
        assert "test_error" in body

    def test_manual_wrap_exceptions_preserves_http_errors(self):
        """Test that wrap_exceptions preserves HTTPError exceptions"""
        app = Kinglet(auto_wrap_exceptions=False)

        @app.get("/http-error")
        @wrap_exceptions(step="test_http")
        async def http_error_endpoint(request):
            raise HTTPError(400, "Bad request")

        client = TestClient(app)
        status, headers, body = client.request("GET", "/http-error")

        assert status == 400
        assert "Bad request" in body

    def test_wrap_exceptions_environment_detection(self):
        """Test that wrap_exceptions auto-detects environment"""
        app = Kinglet(auto_wrap_exceptions=False)

        @app.get("/error")
        @wrap_exceptions(step="env_test")  # No expose_details specified
        async def error_endpoint(request):
            raise ValueError("Sensitive error")

        # Test with development environment
        client = TestClient(app, env={'ENVIRONMENT': 'development'})
        status, headers, body = client.request("GET", "/error")

        assert status == 500
        assert "Sensitive error" in body  # Details exposed in dev

        # Test with production environment
        client = TestClient(app, env={'ENVIRONMENT': 'production'})
        status, headers, body = client.request("GET", "/error")

        assert status == 500
        assert "Sensitive error" not in body  # Details hidden in prod
        assert "Internal server error" in body

    def test_global_exception_wrapping_enabled_by_default(self):
        """Test that global exception wrapping is enabled by default"""
        app = Kinglet(debug=True)  # Should auto-wrap with debug details

        @app.get("/error")
        async def error_endpoint(request):
            raise RuntimeError("Auto-wrapped error")

        client = TestClient(app, env={'ENVIRONMENT': 'development'})
        status, headers, body = client.request("GET", "/error")

        assert status == 500
        assert "Auto-wrapped error" in body

    def test_global_exception_wrapping_can_be_disabled(self):
        """Test that global exception wrapping can be disabled"""
        app = Kinglet(auto_wrap_exceptions=False, debug=True)  # Enable debug to see raw errors

        @app.get("/error")
        async def error_endpoint(request):
            raise RuntimeError("Unwrapped error")

        client = TestClient(app)

        # Should get raw exception since wrapping is disabled but debug shows details
        status, headers, body = client.request("GET", "/error")

        assert status == 500
        assert "Unwrapped error" in body


class TestDevOnlyDecorator:
    """Test require_dev decorator"""

    def test_require_dev_allows_development(self):
        """Test that require_dev allows development environment"""
        app = Kinglet()

        @app.get("/admin/debug")
        @require_dev()
        async def debug_endpoint(request):
            return {"debug": "allowed"}

        client = TestClient(app, env={'ENVIRONMENT': 'development'})
        status, headers, body = client.request("GET", "/admin/debug")

        assert status == 200
        assert "allowed" in body

    def test_require_dev_allows_test(self):
        """Test that require_dev allows test environment"""
        app = Kinglet()

        @app.get("/admin/debug")
        @require_dev()
        async def debug_endpoint(request):
            return {"debug": "allowed"}

        client = TestClient(app, env={'ENVIRONMENT': 'test'})
        status, headers, body = client.request("GET", "/admin/debug")

        assert status == 200
        assert "allowed" in body

    def test_require_dev_blocks_production(self):
        """Test that require_dev blocks production environment"""
        app = Kinglet()

        @app.get("/admin/debug")
        @require_dev()
        async def debug_endpoint(request):
            return {"debug": "should not see this"}

        client = TestClient(app, env={'ENVIRONMENT': 'production'})
        status, headers, body = client.request("GET", "/admin/debug")

        # Security: In production, dev endpoints should be a blackhole (404 Not Found)
        assert status == 404
        assert "Not Found" in body

    def test_require_dev_blocks_unknown_environment(self):
        """Test that require_dev blocks unknown environments"""
        app = Kinglet()

        @app.get("/admin/debug")
        @require_dev()
        async def debug_endpoint(request):
            return {"debug": "should not see this"}

        client = TestClient(app, env={'ENVIRONMENT': 'staging'})
        status, headers, body = client.request("GET", "/admin/debug")

        # Security: Unknown environments should also get blackhole treatment (404 Not Found)
        assert status == 404
        assert "Not Found" in body


class TestGeoRestriction:
    """Test geo_restrict decorator"""

    def test_geo_restrict_allows_permitted_country(self):
        """Test that geo_restrict allows permitted countries"""
        app = Kinglet()

        @app.get("/games")
        @geo_restrict(allowed=["US", "CA", "UK"])
        async def games_endpoint(request):
            return {"games": "available"}

        client = TestClient(app)
        status, headers, body = client.request(
            "GET", "/games",
            headers={"cf-ipcountry": "US"}
        )

        assert status == 200
        assert "available" in body

    def test_geo_restrict_blocks_non_permitted_country(self):
        """Test that geo_restrict blocks non-permitted countries"""
        app = Kinglet()

        @app.get("/games")
        @geo_restrict(allowed=["US", "CA", "UK"])
        async def games_endpoint(request):
            return {"games": "should not see this"}

        client = TestClient(app)
        status, headers, body = client.request(
            "GET", "/games",
            headers={"cf-ipcountry": "CN"}
        )

        assert status == 451  # HTTP 451 Unavailable For Legal Reasons
        assert "Access denied from CN" in body
        assert "US, CA, UK" in body

    def test_geo_restrict_blocked_takes_precedence(self):
        """Test that blocked countries take precedence over allowed"""
        app = Kinglet()

        @app.get("/games")
        @geo_restrict(allowed=["US", "CN"], blocked=["CN"])
        async def games_endpoint(request):
            return {"games": "should not see this"}

        client = TestClient(app)
        status, headers, body = client.request(
            "GET", "/games",
            headers={"cf-ipcountry": "CN"}
        )

        assert status == 451
        assert "Access denied from CN" in body

    def test_geo_restrict_handles_missing_header(self):
        """Test that geo_restrict handles missing CF-IPCountry header"""
        app = Kinglet()

        @app.get("/games")
        @geo_restrict(allowed=["US"])
        async def games_endpoint(request):
            return {"games": "should not see this"}

        client = TestClient(app)
        status, headers, body = client.request("GET", "/games")

        # Should block XX (default when header missing)
        assert status == 451
        assert "Access denied from XX" in body

    def test_geo_restrict_case_insensitive(self):
        """Test that geo_restrict is case insensitive"""
        app = Kinglet()

        @app.get("/games")
        @geo_restrict(allowed=["US"])
        async def games_endpoint(request):
            return {"games": "available"}

        client = TestClient(app)
        status, headers, body = client.request(
            "GET", "/games",
            headers={"cf-ipcountry": "us"}  # lowercase
        )

        assert status == 200
        assert "available" in body


class TestDecoratorCombinations:
    """Test combining multiple decorators"""

    def test_combined_decorators_order_matters(self):
        """Test that decorator order matters for proper error handling"""
        app = Kinglet()

        @app.get("/admin/geo-debug")
        @require_dev()
        @geo_restrict(allowed=["US"])
        async def debug_endpoint(request):
            return {"debug": "super restricted"}

        # Test blocked by geo first (should get 451, not 403)
        client = TestClient(app, env={'ENVIRONMENT': 'development'})
        status, headers, body = client.request(
            "GET", "/admin/geo-debug",
            headers={"cf-ipcountry": "CN"}
        )

        assert status == 451  # Geo restriction error

    def test_exception_wrapping_with_restrictions(self):
        """Test exception wrapping combined with restrictions"""
        app = Kinglet()

        @app.get("/restricted-error")
        @require_dev()
        @wrap_exceptions(step="restricted_test")
        async def restricted_error(request):
            raise ValueError("Error in restricted endpoint")

        # Should work in dev environment
        client = TestClient(app, env={'ENVIRONMENT': 'development'})
        status, headers, body = client.request("GET", "/restricted-error")

        assert status == 500
        assert "Error in restricted endpoint" in body
        assert "restricted_test" in body

        # Should be blocked in production before getting to error
        client = TestClient(app, env={'ENVIRONMENT': 'production'})
        status, headers, body = client.request("GET", "/restricted-error")

        assert status == 404  # Dev restriction blackhole, not the ValueError
