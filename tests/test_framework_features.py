"""
Tests for framework features: field indexing, SQL security, and error handling
"""

from unittest.mock import MagicMock

import pytest

from kinglet.http import HTTPError
from kinglet.orm import IntegerField, _qi


class TestFieldIndexing:
    """Test explicit field indexing feature"""

    def test_integer_field_with_index(self):
        """Test IntegerField can be created with index=True"""
        field = IntegerField(index=True)
        assert field.index is True

    def test_integer_field_without_index(self):
        """Test IntegerField defaults to index=False"""
        field = IntegerField()
        assert field.index is False

    def test_integer_field_with_other_params(self):
        """Test IntegerField with other Field parameters"""
        field = IntegerField(index=True, primary_key=True)
        assert field.index is True
        assert field.primary_key is True


class TestSQLSecurity:
    """Test SQL injection protection via identifier validation"""

    def test_qi_quotes_identifiers(self):
        """Test _qi adds quotes to identifiers"""
        assert _qi("users") == '"users"'
        assert _qi("user_posts") == '"user_posts"'
        assert _qi("_private_table") == '"_private_table"'

    def test_qi_validates_identifiers(self):
        """Test _qi rejects unsafe identifiers"""
        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            _qi("users; DROP TABLE")

        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            _qi("123invalid")  # Can't start with number

        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            _qi("user-name")  # Hyphen not allowed

        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            _qi("")  # Empty string


class TestErrorHandling:
    """Test proper exception chaining for debugging"""

    def test_http_error_from_query_int(self):
        """Test HTTPError raised from query_int preserves cause"""
        from kinglet.http import Request

        # Create a mock request with query string
        mock_raw = MagicMock()
        mock_raw.url = "http://example.com?page=abc"
        mock_raw.method = "GET"
        mock_raw.headers = {}

        request = Request(mock_raw)

        # Should raise HTTPError with ValueError as cause
        with pytest.raises(HTTPError) as exc_info:
            request.query_int("page")

        assert exc_info.value.status_code == 400
        assert "page" in str(exc_info.value.message)
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, ValueError)

    def test_http_error_from_path_param_int(self):
        """Test HTTPError raised from path_param_int preserves cause"""
        from kinglet.http import Request

        # Create a mock request with path params
        mock_raw = MagicMock()
        mock_raw.url = "http://example.com/users/xyz"
        mock_raw.method = "GET"
        mock_raw.headers = {}

        request = Request(mock_raw, path_params={"id": "xyz"})

        # Should raise HTTPError with ValueError as cause
        with pytest.raises(HTTPError) as exc_info:
            request.path_param_int("id")

        assert exc_info.value.status_code == 400
        assert "id" in str(exc_info.value.message)
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, ValueError)


class TestStorageErrorHandling:
    """Test storage utility error handling"""

    def test_d1_unwrap_with_error(self):
        """Test d1_unwrap chains exceptions properly"""
        from kinglet.storage import d1_unwrap

        # Mock object that fails to_py()
        mock_obj = MagicMock()
        mock_obj.to_py.side_effect = RuntimeError("Proxy error")

        with pytest.raises(ValueError) as exc_info:
            d1_unwrap(mock_obj)

        assert "Failed to unwrap D1 object" in str(exc_info.value)
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, RuntimeError)

    def test_d1_unwrap_dict_access_error(self):
        """Test d1_unwrap chains dict access exceptions"""
        from kinglet.storage import d1_unwrap

        # Mock object without to_py but with failing keys()
        mock_obj = MagicMock()
        del mock_obj.to_py
        mock_obj.keys.side_effect = AttributeError("No keys")

        with pytest.raises(ValueError) as exc_info:
            d1_unwrap(mock_obj)

        assert "Failed to unwrap dict-like object" in str(exc_info.value)
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, AttributeError)


class TestTOTPErrorHandling:
    """Test TOTP utility error handling"""

    def test_invalid_totp_secret_format(self):
        """Test generate_totp_code with invalid secret"""
        from kinglet.totp import generate_totp_code

        with pytest.raises(ValueError) as exc_info:
            generate_totp_code("not!valid@base32")

        assert "Invalid TOTP secret format" in str(exc_info.value)
        assert exc_info.value.__cause__ is not None

    def test_decrypt_totp_failure(self):
        """Test decrypt_totp_secret error handling"""
        from kinglet.totp import decrypt_totp_secret

        # Invalid encrypted data
        with pytest.raises(ValueError) as exc_info:
            decrypt_totp_secret(b"\x00\x01", "key")

        assert "Failed to decrypt TOTP secret" in str(exc_info.value)
        assert exc_info.value.__cause__ is not None


class TestFieldValidation:
    """Test field validation error handling"""

    def test_float_field_invalid_value(self):
        """Test FloatField.validate with invalid value"""
        from kinglet.orm import FloatField

        field = FloatField()
        field.name = "price"

        with pytest.raises(ValueError) as exc_info:
            field.validate("not_a_float")

        assert "Invalid float value" in str(exc_info.value)
        assert "not_a_float" in str(exc_info.value)
        assert exc_info.value.__cause__ is not None


class TestSchemaGeneration:
    """Test schema generation utilities"""

    def test_collect_tables(self):
        """Test _collect_tables function"""
        from kinglet.orm import IntegerField, Model
        from kinglet.orm_deploy import _collect_tables

        class TestModel1(Model):
            class Meta:
                table_name = "test1"

            id = IntegerField(primary_key=True)

        class TestModel2(Model):
            class Meta:
                table_name = "test2"

            id = IntegerField(primary_key=True)

        tables = _collect_tables([TestModel1, TestModel2])
        # Should use explicit Meta.table_name values
        assert "test1" in tables
        assert "test2" in tables

    def test_append_cleanslate(self):
        """Test _append_cleanslate function"""
        from kinglet.orm import IntegerField, Model
        from kinglet.orm_deploy import _append_cleanslate

        class TestModel(Model):
            class Meta:
                table_name = "test_table"

            id = IntegerField(primary_key=True)

        parts = []
        _append_cleanslate(parts, [TestModel])

        # Should add DROP TABLE statements
        assert any("DROP TABLE" in part for part in parts)
        # Check that the table is referenced (may be quoted)
        assert any("test_table" in part for part in parts)
