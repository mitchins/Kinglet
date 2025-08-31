"""
Tests for exception chaining improvements (from e) in various modules
"""

from unittest.mock import MagicMock

import pytest

from kinglet.http import HTTPError, Request
from kinglet.storage import d1_unwrap
from kinglet.totp import generate_totp_code


class TestHTTPExceptionChaining:
    """Test exception chaining in http.py"""

    def test_query_int_with_invalid_value_chains_exception(self):
        """Test query_int chains ValueError properly"""
        mock_request = MagicMock()
        mock_request.url = "http://example.com?page=not_a_number"
        mock_request.method = "GET"
        mock_request.headers = {}
        request = Request(mock_request)

        with pytest.raises(HTTPError) as exc_info:
            request.query_int("page")

        # Check exception chaining
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, ValueError)
        assert exc_info.value.status_code == 400
        assert "page" in str(exc_info.value.message)

    def test_path_param_int_with_invalid_value_chains_exception(self):
        """Test path_param_int chains ValueError properly"""
        mock_request = MagicMock()
        mock_request.url = "http://example.com/users/abc"
        mock_request.method = "GET"
        mock_request.headers = {}
        request = Request(mock_request, path_params={"id": "abc"})

        with pytest.raises(HTTPError) as exc_info:
            request.path_param_int("id")

        # Check exception chaining
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, ValueError)
        assert exc_info.value.status_code == 400
        assert "id" in str(exc_info.value.message)


class TestStorageExceptionChaining:
    """Test exception chaining in storage.py"""

    def test_d1_unwrap_with_bad_proxy_chains_exception(self):
        """Test d1_unwrap chains exception when to_py() fails"""
        mock_obj = MagicMock()
        mock_obj.to_py.side_effect = RuntimeError("Proxy error")

        with pytest.raises(ValueError) as exc_info:
            d1_unwrap(mock_obj)

        # Check exception chaining
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, RuntimeError)
        assert "Failed to unwrap D1 object" in str(exc_info.value)
        assert "Proxy error" in str(exc_info.value)

    def test_d1_unwrap_with_bad_dict_access_chains_exception(self):
        """Test d1_unwrap chains exception when dict access fails"""
        mock_obj = MagicMock()
        del mock_obj.to_py  # Remove to_py to trigger dict access path
        mock_obj.keys.side_effect = AttributeError("No keys method")

        with pytest.raises(ValueError) as exc_info:
            d1_unwrap(mock_obj)

        # Check exception chaining
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, AttributeError)
        assert "Failed to unwrap dict-like object" in str(exc_info.value)

    def test_bytes_to_arraybuffer_fallback(self):
        """Test bytes_to_arraybuffer fallback behavior in non-JS environment"""
        from kinglet.storage import bytes_to_arraybuffer

        # In Python environment (no js module), should return data as-is
        test_bytes = b"test data"
        result = bytes_to_arraybuffer(test_bytes)
        assert result == test_bytes  # Fallback returns original data

    def test_bytes_to_arraybuffer_non_bytes_passthrough(self):
        """Test bytes_to_arraybuffer passes through non-bytes objects"""
        from kinglet.storage import bytes_to_arraybuffer

        # Non-bytes object should pass through unchanged
        test_obj = "not bytes"
        result = bytes_to_arraybuffer(test_obj)
        assert result == test_obj

    def test_arraybuffer_to_bytes_fallback(self):
        """Test arraybuffer_to_bytes fallback behavior in non-JS environment"""
        from kinglet.storage import arraybuffer_to_bytes

        # In Python environment, should handle bytes-like objects
        test_bytes = b"test data"
        result = arraybuffer_to_bytes(test_bytes)
        assert result == test_bytes


class TestTOTPExceptionChaining:
    """Test exception chaining in totp.py"""

    def test_generate_totp_invalid_secret_chains_exception(self):
        """Test generate_totp_code chains exception for invalid secret"""
        with pytest.raises(ValueError) as exc_info:
            generate_totp_code("not-a-valid-base32-secret!")

        # Check exception chaining
        assert exc_info.value.__cause__ is not None
        assert "Invalid TOTP secret format" in str(exc_info.value)

    def test_decrypt_totp_secret_failure_chains_exception(self):
        """Test decrypt_totp_secret chains exception on decryption failure"""
        from kinglet.totp import decrypt_totp_secret

        # Invalid encrypted data that can't be decrypted properly
        with pytest.raises(ValueError) as exc_info:
            decrypt_totp_secret(b"\x00\x01\x02", "wrong_key")

        # Check exception chaining
        assert exc_info.value.__cause__ is not None
        assert "Failed to decrypt TOTP secret" in str(exc_info.value)


class TestORMExceptionChaining:
    """Test exception chaining in orm.py"""

    def test_float_field_invalid_value_chains_exception(self):
        """Test FloatField chains exception for invalid values"""
        from kinglet.orm import FloatField

        field = FloatField()
        field.name = "price"

        with pytest.raises(ValueError) as exc_info:
            field.validate("not_a_number")

        # Check exception chaining
        assert exc_info.value.__cause__ is not None
        assert "Invalid float value" in str(exc_info.value)
        assert "not_a_number" in str(exc_info.value)
