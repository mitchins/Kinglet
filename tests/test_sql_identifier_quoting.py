"""
Tests for SQL identifier validation and quoting functionality
"""

import pytest

from kinglet.orm import _qi


def test_qi_valid_identifiers():
    """Test _qi function with valid SQL identifiers"""
    assert _qi("table_name") == '"table_name"'
    assert _qi("TableName") == '"TableName"'
    assert _qi("_private") == '"_private"'
    assert _qi("field123") == '"field123"'
    assert _qi("a") == '"a"'
    assert _qi("A") == '"A"'


def test_qi_invalid_identifiers():
    """Test _qi function rejects invalid SQL identifiers"""
    with pytest.raises(ValueError, match="Unsafe SQL identifier"):
        _qi("123invalid")  # Cannot start with number

    with pytest.raises(ValueError, match="Unsafe SQL identifier"):
        _qi("table-name")  # Hyphen not allowed

    with pytest.raises(ValueError, match="Unsafe SQL identifier"):
        _qi("table name")  # Space not allowed

    with pytest.raises(ValueError, match="Unsafe SQL identifier"):
        _qi("table.name")  # Dot not allowed

    with pytest.raises(ValueError, match="Unsafe SQL identifier"):
        _qi("")  # Empty string not allowed

    with pytest.raises(ValueError, match="Unsafe SQL identifier"):
        _qi("user@domain")  # Special characters not allowed


def test_qi_edge_cases():
    """Test _qi function edge cases"""
    # Test longest common identifier patterns
    assert (
        _qi("very_long_table_name_with_many_underscores")
        == '"very_long_table_name_with_many_underscores"'
    )

    # Test mixed case
    assert _qi("CamelCase_field") == '"CamelCase_field"'

    # Test numbers in valid positions
    assert _qi("table_2023_data") == '"table_2023_data"'


def test_stringfield_index_parameter():
    """Test StringField with index parameter"""
    from kinglet.orm import StringField

    # Default behavior - no index
    field1 = StringField()
    assert hasattr(field1, "index")
    assert field1.index is False

    # Explicit index=True
    field2 = StringField(index=True)
    assert field2.index is True

    # Explicit index=False
    field3 = StringField(index=False)
    assert field3.index is False

    # Test with other parameters
    field4 = StringField(max_length=255, index=True)
    assert field4.index is True
    assert field4.max_length == 255
