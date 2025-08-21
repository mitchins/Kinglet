"""
Tests for custom primary key fields in Kinglet ORM

This tests the specific case where a model defines its own 'id' field
with custom properties, replacing the auto-generated IntegerField id.
"""

import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kinglet.orm import Model, StringField, IntegerField


class CustomIdModel(Model):
    """Test model with custom string primary key"""
    id = StringField(max_length=50, primary_key=True)  # Custom string ID
    name = StringField(max_length=100)
    
    class Meta:
        table_name = "custom_id_test"


class AutoIdModel(Model):
    """Test model with auto-generated integer primary key"""
    name = StringField(max_length=100)
    
    class Meta:
        table_name = "auto_id_test"


def test_custom_string_primary_key_registration():
    """Test that custom string primary key is properly registered in _fields"""
    # The custom id field should be in _fields
    assert 'id' in CustomIdModel._fields
    
    # The id field should be the custom StringField, not auto-generated IntegerField
    id_field = CustomIdModel._fields['id']
    assert isinstance(id_field, StringField)
    assert id_field.primary_key is True
    assert id_field.max_length == 50
    

def test_auto_generated_primary_key_registration():
    """Test that auto-generated primary key works normally"""
    # Should have auto-generated id field
    assert 'id' in AutoIdModel._fields
    
    # Should be auto-generated IntegerField
    id_field = AutoIdModel._fields['id']
    assert isinstance(id_field, IntegerField)
    assert id_field.primary_key is True


def test_custom_primary_key_sql_generation():
    """Test that custom primary key appears in CREATE TABLE SQL"""
    sql = CustomIdModel.get_create_sql()
    
    # Should include the custom id field with correct type and constraint
    assert 'id VARCHAR(50)' in sql
    assert 'CONSTRAINT pk_custom_id_test_id PRIMARY KEY (id)' in sql
    
    # Verify it's not using AUTOINCREMENT (that's for integer IDs only)
    assert 'AUTOINCREMENT' not in sql


def test_auto_primary_key_sql_generation():
    """Test that auto-generated primary key appears in CREATE TABLE SQL"""
    sql = AutoIdModel.get_create_sql()
    
    # Should include auto-generated id field with AUTOINCREMENT
    assert 'id INTEGER PRIMARY KEY AUTOINCREMENT' in sql


def test_primary_key_field_access():
    """Test that primary key fields can be accessed via _get_pk_field"""
    # Custom string primary key
    custom_pk = CustomIdModel._get_pk_field_static()
    assert custom_pk.name == 'id'
    assert isinstance(custom_pk, StringField)
    assert custom_pk.primary_key is True
    
    # Auto-generated integer primary key
    auto_pk = AutoIdModel._get_pk_field_static()
    assert auto_pk.name == 'id'
    assert isinstance(auto_pk, IntegerField)
    assert auto_pk.primary_key is True


def test_model_instantiation_with_custom_pk():
    """Test that models with custom primary keys can be instantiated"""
    # Should be able to create instance with custom id
    instance = CustomIdModel(id="custom-123", name="Test")
    assert instance.id == "custom-123"
    assert instance.name == "Test"
    
    # Should be able to create instance with auto id (None initially)
    auto_instance = AutoIdModel(name="Auto Test")
    assert auto_instance.id is None  # Will be set by database
    assert auto_instance.name == "Auto Test"


if __name__ == "__main__":
    # Run tests directly
    test_custom_string_primary_key_registration()
    test_auto_generated_primary_key_registration()
    test_custom_primary_key_sql_generation()
    test_auto_primary_key_sql_generation()
    test_primary_key_field_access()
    test_model_instantiation_with_custom_pk()
    print("All custom primary key tests passed!")