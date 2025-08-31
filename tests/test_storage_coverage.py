"""
Focused storage coverage tests - DRY approach
Tests for storage functions that need coverage
"""

import pytest


class TestStorageCoverage:
    """Test storage functions that need coverage"""

    def test_d1_unwrap_error_case(self):
        """Test d1_unwrap with unsupported type"""
        from kinglet.storage import d1_unwrap

        # Test error case for unsupported type
        with pytest.raises(ValueError, match="Cannot unwrap D1 object"):
            d1_unwrap(set())  # Unsupported type

        # Test dict case (should work)
        result = d1_unwrap({"key": "value"})
        assert result == {"key": "value"}

    def test_r2_content_info_fallback(self):
        """Test r2_get_content_info with missing attributes"""
        from kinglet.storage import r2_get_content_info

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
        from kinglet.storage import arraybuffer_to_bytes, bytes_to_arraybuffer

        test_data = b"test data"

        # In non-JS environment, should return data as-is
        result = bytes_to_arraybuffer(test_data)
        assert result == test_data

        # Reverse conversion
        converted_back = arraybuffer_to_bytes(result)
        assert converted_back == test_data

    def test_r2_list_function(self):
        """Test r2_list function with mock data"""
        from kinglet.storage import r2_list

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
        from kinglet.storage import _safe_js_object_access

        # Test with None
        result = _safe_js_object_access(None)
        assert result is None

        # Test with object
        obj = type("MockObj", (), {"attr": "value"})()
        result = _safe_js_object_access(obj, default="fallback")
        assert result == obj  # Should return the object itself

    def test_r2_metadata_complex_path(self):
        """Test r2_get_metadata with nested path"""
        from kinglet.storage import r2_get_metadata

        # Mock nested object
        inner = type("Inner", (), {"contentType": "text/plain"})()
        mock_obj = type("MockR2", (), {"httpMetadata": inner})()

        # Test nested access
        content_type = r2_get_metadata(mock_obj, "httpMetadata.contentType")
        assert content_type == "text/plain"

        # Test non-existent path
        result = r2_get_metadata(mock_obj, "nonexistent.path", "default")
        assert result == "default"
