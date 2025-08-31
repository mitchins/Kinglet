"""
Tests for Kinglet exception classes
"""

from kinglet.exceptions import DevOnlyError, GeoRestrictedError, HTTPError


class TestHTTPError:
    """Test HTTPError exception class"""

    def test_http_error_basic(self):
        """Test HTTPError with basic parameters"""
        error = HTTPError(500, "Server Error", "req-123")

        assert error.status_code == 500
        assert error.message == "Server Error"
        assert error.request_id == "req-123"
        assert str(error) == "Server Error"

    def test_http_error_no_request_id(self):
        """Test HTTPError without request ID"""
        error = HTTPError(404, "Not Found")

        assert error.status_code == 404
        assert error.message == "Not Found"
        assert error.request_id is None


class TestGeoRestrictedError:
    """Test GeoRestrictedError exception class"""

    def test_geo_restricted_with_allowed_countries(self):
        """Test GeoRestrictedError with allowed countries list"""
        error = GeoRestrictedError("CN", ["US", "CA"], "req-456")

        assert error.status_code == 451
        assert error.country_code == "CN"
        assert error.allowed_countries == ["US", "CA"]
        assert "Access denied from CN" in error.message
        assert "US, CA" in error.message
        assert error.request_id == "req-456"

    def test_geo_restricted_no_allowed_countries(self):
        """Test GeoRestrictedError without allowed countries (covers line 19)"""
        error = GeoRestrictedError("RU", None, "req-789")

        assert error.status_code == 451
        assert error.country_code == "RU"
        assert error.allowed_countries == []
        assert error.message == "Access denied from RU"
        assert error.request_id == "req-789"

    def test_geo_restricted_empty_allowed_countries(self):
        """Test GeoRestrictedError with empty allowed countries list"""
        error = GeoRestrictedError("FR", [])

        assert error.status_code == 451
        assert error.country_code == "FR"
        assert error.allowed_countries == []
        assert error.message == "Access denied from FR"


class TestDevOnlyError:
    """Test DevOnlyError exception class"""

    def test_dev_only_error_with_request_id(self):
        """Test DevOnlyError with request ID"""
        error = DevOnlyError("req-dev-123")

        assert error.status_code == 403
        assert error.message == "This endpoint is only available in development mode"
        assert error.request_id == "req-dev-123"

    def test_dev_only_error_no_request_id(self):
        """Test DevOnlyError without request ID (covers lines 27-28)"""
        error = DevOnlyError()

        assert error.status_code == 403
        assert error.message == "This endpoint is only available in development mode"
        assert error.request_id is None
