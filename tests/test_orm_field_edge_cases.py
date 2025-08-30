"""
Tests for ORM field edge cases and uncovered branches
"""

from datetime import datetime

import pytest

from kinglet.orm import DateTimeField, Field, FloatField, IntegerField


class TestFieldEdgeCases:
    """Test edge cases in Field base class"""

    def test_field_get_sql_type(self):
        """Test Field.get_sql_type returns TEXT by default"""
        field = Field()
        assert field.get_sql_type() == "TEXT"

    def test_field_validate_passthrough(self):
        """Test Field.validate passes through values unchanged"""
        field = Field()
        assert field.validate("test") == "test"
        assert field.validate(123) == 123
        assert field.validate(None) is None


class TestDateTimeFieldEdgeCases:
    """Test edge cases in DateTimeField conversion methods"""

    def test_to_python_string_iso_format(self):
        """Test to_python with ISO format datetime string"""
        field = DateTimeField()

        # ISO format with T separator
        result = field.to_python("2023-12-01T15:30:45")
        assert isinstance(result, datetime)
        assert result.year == 2023
        assert result.month == 12
        assert result.day == 1
        assert result.hour == 15
        assert result.minute == 30
        assert result.second == 45

        # ISO format with space separator
        result = field.to_python("2023-12-01 15:30:45")
        assert isinstance(result, datetime)
        assert result.year == 2023
        assert result.month == 12
        assert result.day == 1

    def test_to_python_string_timestamp(self):
        """Test to_python with Unix timestamp string"""
        field = DateTimeField()

        # When ISO parsing fails, try timestamp
        result = field.to_python("1609459200")  # 2021-01-01 00:00:00 UTC
        assert isinstance(result, datetime)
        assert result.year == 2021
        assert result.month == 1
        assert result.day == 1

    def test_to_python_string_invalid_returns_none(self):
        """Test to_python with invalid string returns None"""
        field = DateTimeField()

        # Invalid datetime string
        result = field.to_python("not-a-date")
        assert result is None

        # Invalid timestamp string
        result = field.to_python("not-a-number")
        assert result is None

    def test_to_python_numeric_timestamp(self):
        """Test to_python with numeric Unix timestamp"""
        field = DateTimeField()

        # Integer timestamp
        result = field.to_python(1609459200)  # 2021-01-01 00:00:00 UTC
        assert isinstance(result, datetime)
        assert result.year == 2021

        # Float timestamp
        result = field.to_python(1609459200.5)
        assert isinstance(result, datetime)
        assert result.year == 2021

    def test_to_python_invalid_numeric_returns_none(self):
        """Test to_python with invalid numeric value returns None"""
        field = DateTimeField()

        # Invalid type (causes TypeError) - this will be caught and return None
        result = field.to_python(complex(1, 2))  # Complex number
        assert result is None

    def test_to_db_datetime_object(self):
        """Test to_db with datetime object"""
        field = DateTimeField()
        dt = datetime(2023, 12, 1, 15, 30, 45)

        result = field.to_db(dt)
        assert isinstance(result, int)
        # Should be Unix timestamp
        assert result == int(dt.timestamp())

    def test_to_db_none(self):
        """Test to_db with None value"""
        field = DateTimeField()
        result = field.to_db(None)
        assert result is None

    def test_get_sql_type(self):
        """Test DateTimeField.get_sql_type returns INTEGER"""
        field = DateTimeField()
        assert field.get_sql_type() == "INTEGER"


class TestFloatFieldEdgeCases:
    """Test edge cases in FloatField"""

    def test_get_sql_type(self):
        """Test FloatField.get_sql_type returns REAL"""
        field = FloatField()
        assert field.get_sql_type() == "REAL"

    def test_validate_valid_float(self):
        """Test FloatField.validate with valid float values"""
        field = FloatField()
        field.name = "test_field"

        assert field.validate(3.14) == 3.14
        assert field.validate(0.0) == 0.0
        assert field.validate(-2.5) == -2.5

        # String that can be converted
        assert field.validate("3.14") == 3.14
        assert field.validate("0") == 0.0

    def test_validate_none(self):
        """Test FloatField.validate with None"""
        field = FloatField()
        field.name = "test_field"

        assert field.validate(None) is None


class TestIntegerFieldEdgeCases:
    """Test edge cases in IntegerField"""

    def test_get_sql_type(self):
        """Test IntegerField.get_sql_type returns INTEGER"""
        field = IntegerField()
        assert field.get_sql_type() == "INTEGER"

    def test_validate_valid_integer(self):
        """Test IntegerField.validate with valid integer values"""
        field = IntegerField()
        field.name = "test_field"

        assert field.validate(42) == 42
        assert field.validate(0) == 0
        assert field.validate(-10) == -10

        # String that can be converted
        assert field.validate("42") == 42
        assert field.validate("0") == 0

    def test_validate_none(self):
        """Test IntegerField.validate with None"""
        field = IntegerField()
        field.name = "test_field"

        assert field.validate(None) is None

    def test_to_python_invalid_value_raises_error(self):
        """Test IntegerField.to_python raises error for invalid values"""
        field = IntegerField()

        with pytest.raises(ValueError):
            field.to_python("not_an_integer")


class TestFieldIndexConfiguration:
    """Test field index configuration"""

    def test_integer_field_index_configuration(self):
        """Test IntegerField index configuration"""
        # Default no index
        field = IntegerField()
        assert field.index is False

        # Explicit index
        field = IntegerField(index=True)
        assert field.index is True

        # Index with other options
        field = IntegerField(index=True, primary_key=True)
        assert field.index is True
        assert field.primary_key is True

    def test_datetime_field_index_configuration(self):
        """Test DateTimeField index configuration"""
        # Default no index
        field = DateTimeField()
        assert field.index is False

        # Explicit index
        field = DateTimeField(index=True)
        assert field.index is True

        # Index with auto_now options
        field = DateTimeField(index=True, auto_now=True)
        assert field.index is True
        assert field.auto_now is True


class TestFieldDatabaseOperations:
    """Test field database operation edge cases"""

    def test_datetime_field_to_db_edge_cases(self):
        """Test DateTimeField.to_db with numeric input"""
        field = DateTimeField()

        # Non-datetime, non-None numeric values should be converted directly
        result = field.to_db(1609459200)  # Unix timestamp
        assert result == 1609459200  # Should return the int directly (line 193)

        # Float input
        result = field.to_db(1609459200.5)
        assert result == 1609459200  # Should convert to int
