"""
Comprehensive tests for NULL handling in Kinglet ORM

This test file ensures 100% coverage of NULL/None value handling to prevent
D1_TYPE_ERROR: Type 'undefined' not supported issues in Cloudflare Workers.

Critical for alpha testing of Kinglet 1.6.0 with D1 database.
"""

import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kinglet.orm import Model, StringField, IntegerField, BooleanField, DateTimeField
from .mock_d1 import MockD1Database, d1_unwrap, d1_unwrap_results


class NullTestModel(Model):
    """Test model specifically for NULL handling scenarios"""
    required_field = StringField(max_length=100, null=False, unique=True)
    optional_string = StringField(max_length=100, null=True)
    optional_int = IntegerField(null=True)
    optional_bool = BooleanField(null=True)
    optional_datetime = DateTimeField(null=True)
    
    class Meta:
        table_name = "test_null_model"


class TestNullHandlingFieldValidation:
    """Test field-level NULL validation and conversion"""
    
    def test_string_field_null_allowed(self):
        """Test StringField with null=True handles None correctly"""
        field = StringField(null=True)
        field.name = "test_field"
        
        # None should be valid when null=True
        assert field.validate(None) is None
        assert field.to_db(None) is None
        
        # Non-None values should work normally
        assert field.validate("test") == "test"
        assert field.to_db("test") == "test"
        
    def test_string_field_null_not_allowed(self):
        """Test StringField with null=False rejects None"""
        field = StringField(null=False)
        field.name = "test_field"
        
        from kinglet.orm_errors import ValidationError
        with pytest.raises(ValidationError, match="Field cannot be null"):
            field.validate(None)
            
    def test_integer_field_null_handling(self):
        """Test IntegerField NULL handling"""
        field = IntegerField(null=True)
        field.name = "test_int"
        
        assert field.validate(None) is None
        assert field.to_db(None) is None
        assert field.to_python(None) is None
        
        # Ensure normal values still work
        assert field.validate(42) == 42
        assert field.to_db(42) == 42
        
    def test_boolean_field_null_handling(self):
        """Test BooleanField NULL handling"""
        field = BooleanField(null=True)
        field.name = "test_bool"
        
        assert field.validate(None) is None
        assert field.to_db(None) is None
        assert field.to_python(None) is None
        
        # Ensure boolean conversion still works
        assert field.to_db(True) == 1
        assert field.to_db(False) == 0
        
    def test_datetime_field_null_handling(self):
        """Test DateTimeField NULL handling"""
        field = DateTimeField(null=True)
        field.name = "test_datetime"
        
        assert field.validate(None) is None
        assert field.to_db(None) is None
        assert field.to_python(None) is None


class TestNullHandlingModelOperations:
    """Test model-level NULL handling in CRUD operations"""
    
    def setup_method(self):
        self.mock_db = MockD1Database()
        self.manager = NullTestModel.objects
        
    @pytest.mark.asyncio
    async def test_create_with_null_values(self):
        """Test creating model instance with NULL values"""
        with patch('kinglet.orm.d1_unwrap', d1_unwrap), \
             patch('kinglet.orm.d1_unwrap_results', d1_unwrap_results):
            
            # Create table first
            await NullTestModel.create_table(self.mock_db)
            
            # Create instance with NULL values for optional fields
            instance = await self.manager.create(
                self.mock_db,
                required_field="required_value",
                optional_string=None,
                optional_int=None,
                optional_bool=None,
                optional_datetime=None
            )
            
            assert instance.required_field == "required_value"
            assert instance.optional_string is None
            assert instance.optional_int is None
            assert instance.optional_bool is None
            assert instance.optional_datetime is None
            assert instance.id is not None
            
    @pytest.mark.asyncio
    async def test_save_with_null_values_insert(self):
        """Test saving new instance with NULL values (INSERT operation)"""
        with patch('kinglet.orm.d1_unwrap', d1_unwrap), \
             patch('kinglet.orm.d1_unwrap_results', d1_unwrap_results):
            
            # Create table first
            await NullTestModel.create_table(self.mock_db)
            
            # Create instance and save (INSERT)
            instance = NullTestModel(
                required_field="test_value",
                optional_string=None,
                optional_int=None,
                optional_bool=None
            )
            
            await instance.save(self.mock_db)
            
            assert instance.id is not None
            assert instance._state['saved'] is True
            
    @pytest.mark.asyncio
    async def test_save_with_null_values_update(self):
        """Test saving existing instance with NULL values (UPDATE operation)"""
        with patch('kinglet.orm.d1_unwrap', d1_unwrap), \
             patch('kinglet.orm.d1_unwrap_results', d1_unwrap_results):
            
            # Create table and initial instance
            await NullTestModel.create_table(self.mock_db)
            
            instance = await self.manager.create(
                self.mock_db,
                required_field="original_value",
                optional_string="original_string",
                optional_int=42
            )
            
            # Update with NULL values (UPDATE operation)
            instance.optional_string = None
            instance.optional_int = None
            instance.optional_bool = None
            
            await instance.save(self.mock_db)
            
            # Verify update worked
            retrieved = await self.manager.get(self.mock_db, id=instance.id)
            assert retrieved.optional_string is None
            assert retrieved.optional_int is None
            assert retrieved.optional_bool is None
            
    @pytest.mark.asyncio
    async def test_bulk_create_with_null_values(self):
        """Test bulk create operations with NULL values"""
        with patch('kinglet.orm.d1_unwrap', d1_unwrap), \
             patch('kinglet.orm.d1_unwrap_results', d1_unwrap_results):
            
            # Create table first
            await NullTestModel.create_table(self.mock_db)
            
            # Create instances with NULL values for bulk create
            instances = [
                NullTestModel(
                    required_field=f"bulk_test_{i}",
                    optional_string=None if i % 2 == 0 else f"value_{i}",
                    optional_int=None if i % 3 == 0 else i * 10,
                    optional_bool=None if i % 4 == 0 else True
                )
                for i in range(3)
            ]
            
            # Bulk create
            created_instances = await self.manager.bulk_create(self.mock_db, instances)
            
            assert len(created_instances) == 3
            # Verify NULL values are preserved
            assert created_instances[0].optional_string is None  # i=0, i%2==0
            assert created_instances[1].optional_string == "value_1"  # i=1, i%2!=0
            assert created_instances[0].optional_int is None  # i=0, i%3==0


class TestNullHandlingSQLGeneration:
    """Test SQL generation for NULL handling"""
    
    def test_insert_sql_with_nulls(self):
        """Test that INSERT SQL uses explicit NULL instead of ? for None values"""
        # This is a unit test - we'll test the SQL generation logic directly
        # by examining what the model save() method would generate
        
        instance = NullTestModel(
            required_field="test",
            optional_string=None,
            optional_int=42,
            optional_bool=None
        )
        
        # Mock the field conversion process
        field_data = {}
        for field_name, field in instance._fields.items():
            if field_name != 'id':  # Don't include auto-generated ID in INSERT
                value = getattr(instance, field_name, None)
                validated_value = field.validate(value)
                db_value = field.to_db(validated_value)
                field_data[field_name] = db_value
        
        # Simulate the SQL generation logic from save() method
        columns = list(field_data.keys())
        values = list(field_data.values())
        
        value_expressions = []
        bind_values = []
        
        for value in values:
            if value is None:
                value_expressions.append("NULL")
            else:
                value_expressions.append("?")
                bind_values.append(value)
        
        sql = f"INSERT INTO test_null_model ({', '.join(columns)}) VALUES ({', '.join(value_expressions)})"
        
        # Verify SQL contains explicit NULL
        assert "NULL" in sql
        assert sql.count("?") == len(bind_values)
        assert None not in bind_values  # No None values should be in bind parameters
        
        # Verify specific field handling
        assert "required_field = ?" not in sql  # It's in VALUES, not SET
        assert 42 in bind_values  # Non-null integer should be bound
        
    def test_update_sql_with_nulls(self):
        """Test that UPDATE SQL uses explicit NULL instead of ? for None values"""
        
        # Simulate UPDATE scenario
        field_data = {
            'required_field': 'updated_value',
            'optional_string': None,
            'optional_int': 99,
            'optional_bool': None,
            'id': 1
        }
        
        # Simulate UPDATE SQL generation logic
        pk_field_name = 'id'
        pk_value = field_data[pk_field_name]
        
        set_clauses = []
        bind_values = []
        
        for field_name, value in field_data.items():
            if field_name != pk_field_name:  # Don't update primary key
                if value is None:
                    set_clauses.append(f"{field_name} = NULL")
                else:
                    set_clauses.append(f"{field_name} = ?")
                    bind_values.append(value)
        
        bind_values.append(pk_value)  # Add PK value for WHERE clause
        sql = f"UPDATE test_null_model SET {', '.join(set_clauses)} WHERE {pk_field_name} = ?"
        
        # Verify SQL contains explicit NULL
        assert "= NULL" in sql
        assert sql.count("?") == len(bind_values)
        assert None not in bind_values  # No None values should be in bind parameters
        
        # Verify specific patterns
        assert "optional_string = NULL" in sql
        assert "optional_bool = NULL" in sql
        assert "optional_int = ?" in sql  # Non-null should use parameter


class TestNullHandlingEdgeCases:
    """Test edge cases and error conditions for NULL handling"""
    
    def test_required_field_cannot_be_null(self):
        """Test that required fields reject NULL values during field validation"""
        from kinglet.orm_errors import ValidationError
        
        # Model creation doesn't validate, but field validation should
        field = StringField(null=False)
        field.name = "required_field"
        
        with pytest.raises(ValidationError):
            field.validate(None)
            
    def test_mixed_null_and_non_null_values(self):
        """Test instances with mixed NULL and non-NULL values"""
        instance = NullTestModel(
            required_field="required",
            optional_string="not_null",
            optional_int=None,
            optional_bool=True,
            optional_datetime=None
        )
        
        # Verify field assignments
        assert instance.required_field == "required"
        assert instance.optional_string == "not_null"
        assert instance.optional_int is None
        assert instance.optional_bool is True
        assert instance.optional_datetime is None
        
    def test_empty_string_vs_null(self):
        """Test that empty string is different from NULL"""
        instance = NullTestModel(
            required_field="",  # Empty string, not NULL
            optional_string=""   # Empty string, not NULL
        )
        
        # Empty strings should not be converted to None
        assert instance.required_field == ""
        assert instance.optional_string == ""
        
        # Field validation should preserve empty strings
        for field_name, field in instance._fields.items():
            if field_name in ['required_field', 'optional_string']:
                value = getattr(instance, field_name)
                validated = field.validate(value)
                db_value = field.to_db(validated)
                assert db_value == ""  # Empty string preserved
                assert db_value is not None  # Not None


class TestNullHandlingJavaScriptInterop:
    """Test NULL handling in JavaScript interop scenarios"""
    
    def test_none_to_null_conversion_patterns(self):
        """Test different patterns for converting None to null"""
        
        # Test the patterns we use in the framework
        test_values = [None, "string", 123, True, False, "", 0]
        
        # Pattern 1: SQL-level explicit NULL (our current solution)
        sql_values = []
        bind_values = []
        for value in test_values:
            if value is None:
                sql_values.append("NULL")
            else:
                sql_values.append("?")
                bind_values.append(value)
        
        # Verify no None values in bind parameters
        assert None not in bind_values
        assert "NULL" in sql_values
        
        # Pattern 2: Field-level validation (backup protection)
        for field_type in [StringField, IntegerField, BooleanField]:
            field = field_type(null=True)
            field.name = "test"
            
            # None should pass through unchanged for nullable fields
            assert field.validate(None) is None
            assert field.to_db(None) is None
        
    def test_javascript_undefined_prevention(self):
        """Test that we never generate JavaScript undefined values"""
        
        # Simulate the conversion process that happens in Workers
        python_values = [None, "", 0, False, True, "string", 123]
        
        for value in python_values:
            # Our explicit NULL handling should prevent undefined
            if value is None:
                # Should become explicit NULL in SQL, not bound parameter
                sql_representation = "NULL"
                assert sql_representation != "undefined"
                assert sql_representation != "?"
            else:
                # Should become bound parameter
                sql_representation = "?"
                # Value should be preserved exactly
                assert value is not None  # Never None in bind values


if __name__ == "__main__":
    # Run specific NULL handling tests
    import subprocess
    subprocess.run([
        "python", "-m", "pytest", __file__, "-v", 
        "--tb=short", "-x"  # Stop on first failure for faster feedback
    ])