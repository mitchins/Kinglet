"""
Tests for the constants module to ensure string constants are accessible
and maintain expected values for compatibility.
"""

from kinglet.constants import (
    AUTH_REQUIRED,
    CHECK_CONSTRAINT_VIOLATION,
    ERROR_TYPES,
    HTTP_STATUS,
    MIGRATIONS_FILE,
    NOT_FOUND,
    PYTHON_MODULE_HELP,
    SCHEMA_LOCK_FILE,
    TOTP_STEP_UP_PATH,
)


class TestStringConstants:
    """Test that string constants have expected values"""

    def test_auth_required_constant(self):
        """Test authentication required constant"""
        assert AUTH_REQUIRED == "authentication required"
        assert isinstance(AUTH_REQUIRED, str)
        assert len(AUTH_REQUIRED) > 0

    def test_not_found_constant(self):
        """Test not found constant"""
        assert NOT_FOUND == "not found"
        assert isinstance(NOT_FOUND, str)
        assert len(NOT_FOUND) > 0

    def test_check_constraint_violation_constant(self):
        """Test check constraint violation constant"""
        assert CHECK_CONSTRAINT_VIOLATION == "Check constraint violation"
        assert isinstance(CHECK_CONSTRAINT_VIOLATION, str)
        assert len(CHECK_CONSTRAINT_VIOLATION) > 0

    def test_totp_step_up_path_constant(self):
        """Test TOTP step-up path constant"""
        assert TOTP_STEP_UP_PATH == "/auth/totp/step-up"
        assert isinstance(TOTP_STEP_UP_PATH, str)
        assert TOTP_STEP_UP_PATH.startswith("/")

    def test_file_name_constants(self):
        """Test file name constants"""
        assert SCHEMA_LOCK_FILE == "schema.lock.json"
        assert MIGRATIONS_FILE == "migrations.json"
        assert isinstance(SCHEMA_LOCK_FILE, str)
        assert isinstance(MIGRATIONS_FILE, str)
        assert SCHEMA_LOCK_FILE.endswith(".json")
        assert MIGRATIONS_FILE.endswith(".json")

    def test_help_text_constant(self):
        """Test help text constant"""
        assert PYTHON_MODULE_HELP == "Python module containing models"
        assert isinstance(PYTHON_MODULE_HELP, str)
        assert len(PYTHON_MODULE_HELP) > 0


class TestErrorTypes:
    """Test error type constants"""

    def test_error_types_dict(self):
        """Test error types dictionary structure"""
        assert isinstance(ERROR_TYPES, dict)
        assert len(ERROR_TYPES) > 0

        # Check expected keys exist
        expected_keys = ["NOT_FOUND", "AUTHENTICATION_REQUIRED", "CONSTRAINT_VIOLATION"]
        for key in expected_keys:
            assert key in ERROR_TYPES
            assert isinstance(ERROR_TYPES[key], str)

    def test_error_type_values(self):
        """Test specific error type values"""
        assert ERROR_TYPES["NOT_FOUND"] == "not_found"
        assert ERROR_TYPES["AUTHENTICATION_REQUIRED"] == "authentication_required"
        assert ERROR_TYPES["CONSTRAINT_VIOLATION"] == "constraint_violation"


class TestHttpStatus:
    """Test HTTP status code constants"""

    def test_http_status_dict(self):
        """Test HTTP status dictionary structure"""
        assert isinstance(HTTP_STATUS, dict)
        assert len(HTTP_STATUS) > 0

        # All values should be integers
        for status_name, status_code in HTTP_STATUS.items():
            assert isinstance(status_name, str)
            assert isinstance(status_code, int)
            assert 100 <= status_code < 600  # Valid HTTP status range

    def test_common_http_status_codes(self):
        """Test common HTTP status codes are present"""
        expected_statuses = {
            "OK": 200,
            "UNAUTHORIZED": 401,
            "FORBIDDEN": 403,
            "NOT_FOUND": 404,
            "INTERNAL_SERVER_ERROR": 500,
        }

        for status_name, expected_code in expected_statuses.items():
            assert status_name in HTTP_STATUS
            assert HTTP_STATUS[status_name] == expected_code


class TestConstantsIntegration:
    """Test that constants work with the rest of the system"""

    def test_constants_importable_from_authz(self):
        """Test that authz module can import and use constants"""
        from kinglet.authz import get_user

        # The function should be importable and callable
        assert callable(get_user)

    def test_constants_importable_from_orm_modules(self):
        """Test that ORM modules can import constants"""
        # Test that imports work without errors
        from kinglet import orm_deploy, orm_errors, orm_migrations

        # These should not raise import errors
        assert hasattr(orm_deploy, "generate_lock")
        assert hasattr(orm_migrations, "Migration")
        assert hasattr(orm_errors, "ConstraintRegistry")

    def test_file_extensions_valid(self):
        """Test that file name constants have valid extensions"""
        assert SCHEMA_LOCK_FILE.endswith(".json")
        assert MIGRATIONS_FILE.endswith(".json")

        # Should not contain invalid characters for filenames
        invalid_chars = ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]
        for char in invalid_chars:
            assert char not in SCHEMA_LOCK_FILE
            assert char not in MIGRATIONS_FILE


class TestConstantsBackwardsCompatibility:
    """Test that using constants doesn't break existing functionality"""

    def test_string_constants_behave_like_strings(self):
        """Test that constants can be used anywhere strings are expected"""
        # Test string formatting
        error_msg = f"Error: {NOT_FOUND}"
        assert "not found" in error_msg

        # Test string concatenation
        full_path = "/api" + TOTP_STEP_UP_PATH
        assert full_path == "/api/auth/totp/step-up"

        # Test string comparison
        assert NOT_FOUND == "not found"
        assert NOT_FOUND != "something else"

        # Test string methods
        assert NOT_FOUND.upper() == "NOT FOUND"
        assert AUTH_REQUIRED.replace("required", "needed") == "authentication needed"
