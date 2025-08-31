"""
Tests for kinglet.storage module
"""

from unittest.mock import Mock

from kinglet.storage import (
    _access_attribute,
    _access_bracket_notation,
    _access_dict_key,
    _is_js_undefined,
    _safe_js_object_access,
    _traverse_path_part,
    arraybuffer_to_bytes,
    bytes_to_arraybuffer,
    d1_unwrap,
    d1_unwrap_results,
    r2_get_content_info,
    r2_get_metadata,
    r2_list,
)


class TestD1Utilities:
    """Test D1 database utilities"""

    def test_d1_unwrap_dict(self):
        """Test unwrapping dict objects"""
        obj = {"key": "value"}
        result = d1_unwrap(obj)
        assert result == {"key": "value"}

    def test_d1_unwrap_none(self):
        """Test unwrapping None returns empty dict"""
        result = d1_unwrap(None)
        assert result == {}

    def test_d1_unwrap_results_with_results_attr(self):
        """Test unwrapping results with .results attribute"""
        results_obj = Mock()
        results_obj.results = [{"id": 1}, {"id": 2}]

        result = d1_unwrap_results(results_obj)
        assert result == [{"id": 1}, {"id": 2}]

    def test_d1_unwrap_results_list(self):
        """Test unwrapping direct list of results"""
        results_list = [{"id": 1}, {"id": 2}]

        result = d1_unwrap_results(results_list)
        assert result == [{"id": 1}, {"id": 2}]


class TestR2MetadataHelpers:
    """Test R2 metadata helper functions"""

    def test_is_js_undefined_string_check(self):
        """Test undefined detection via string representation"""
        result = _is_js_undefined("undefined", "default_val")
        assert result == "default_val"

    def test_is_js_undefined_normal_value(self):
        """Test undefined detection with normal value"""
        result = _is_js_undefined("normal", "default_val")
        assert result == "normal"

    def test_access_attribute_success(self):
        """Test successful attribute access"""
        obj = Mock()
        obj.test_attr = "value"

        result = _access_attribute(obj, "test_attr", "default")
        assert result == "value"

    def test_access_attribute_missing(self):
        """Test attribute access when attribute doesn't exist"""
        obj = Mock(spec=[])  # No attributes

        result = _access_attribute(obj, "missing", "default")
        assert result is None

    def test_access_dict_key_success(self):
        """Test successful dict key access"""
        result = _access_dict_key({"key": "value"}, "key")
        assert result == "value"

    def test_access_dict_key_not_dict(self):
        """Test dict key access on non-dict object"""
        result = _access_dict_key("not a dict", "key")
        assert result is None

    def test_access_bracket_notation_success(self):
        """Test successful bracket notation access"""
        obj = {"key": "value"}

        result = _access_bracket_notation(obj, "key", "default")
        assert result == "value"

    def test_access_bracket_notation_error(self):
        """Test bracket notation access failure"""
        obj = Mock()
        obj.__getitem__ = Mock(side_effect=KeyError())

        result = _access_bracket_notation(obj, "key", "default")
        assert result == "default"

    def test_traverse_path_part_none_current(self):
        """Test path traversal with None current value"""
        result = _traverse_path_part(None, "part", "default")
        assert result == "default"


class TestR2MetadataIntegration:
    """Test full R2 metadata extraction"""

    def test_r2_get_metadata_simple_attribute(self):
        """Test getting simple attribute from R2 object"""
        obj = Mock()
        obj.size = 1024

        result = r2_get_metadata(obj, "size", 0)
        assert result == 1024

    def test_r2_get_metadata_nested_path(self):
        """Test getting nested attribute via dot notation"""
        obj = Mock()
        obj.httpMetadata = Mock()
        obj.httpMetadata.contentType = "image/jpeg"

        result = r2_get_metadata(
            obj, "httpMetadata.contentType", "application/octet-stream"
        )
        assert result == "image/jpeg"

    def test_r2_get_metadata_missing_returns_default(self):
        """Test that missing metadata returns default value"""
        obj = Mock(spec=[])  # No attributes

        result = r2_get_metadata(obj, "missing.path", "default")
        assert result == "default"

    def test_d1_unwrap_error_case(self):
        """Test d1_unwrap with unsupported type"""
        # Test error case for unsupported type
        import pytest

        with pytest.raises(ValueError, match="Cannot unwrap D1 object"):
            d1_unwrap(set())  # Unsupported type

        # Test dict case (should work)
        result = d1_unwrap({"key": "value"})
        assert result == {"key": "value"}

    def test_r2_content_info_fallback(self):
        """Test r2_get_content_info with missing attributes"""
        # Mock object with missing attributes
        mock_obj = type("MockR2", (), {})()

        result = r2_get_content_info(mock_obj)

        # Should have fallback values
        assert result["content_type"] == "application/octet-stream"
        assert result["custom_metadata"] == {}
        assert result["size"] is None
        assert result["etag"] is None

    def test_bytes_arraybuffer_non_js(self):
        """Test bytes/arraybuffer conversion in non-JS environment"""
        test_data = b"test data"

        # In non-JS environment, should return data as-is
        result = bytes_to_arraybuffer(test_data)
        assert result == test_data

        # Reverse conversion
        converted_back = arraybuffer_to_bytes(result)
        assert converted_back == test_data

    def test_r2_list_function(self):
        """Test r2_list function with mock data"""
        # Mock list result with objects array
        mock_result = type(
            "MockListResult",
            (),
            {
                "objects": [
                    type("MockObject", (), {"key": "file1.txt"})(),
                    type("MockObject", (), {"key": "file2.txt"})(),
                ]
            },
        )()

        # Should extract objects array and convert to dicts
        result = r2_list(mock_result)
        assert len(result) == 2
        assert result[0]["key"] == "file1.txt"
        assert "size" in result[0]  # Should have default values

    def test_safe_js_object_access(self):
        """Test _safe_js_object_access function"""
        # Test with None
        result = _safe_js_object_access(None)
        assert result is None

        # Test with object
        obj = type("MockObj", (), {"attr": "value"})()
        result = _safe_js_object_access(obj, default="fallback")
        assert result == obj  # Should return the object itself
