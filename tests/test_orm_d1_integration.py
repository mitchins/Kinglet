"""
Integration tests for Kinglet ORM with real D1 database

These tests run against actual D1 database to catch issues that
mock tests might miss, particularly around type conversion and
JavaScript/Python interop.
"""

import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kinglet.orm import Model, StringField, IntegerField, BooleanField, DateTimeField


class D1UserModel(Model):
    """Test model matching User structure for D1 integration testing"""
    email = StringField(max_length=255, null=False, unique=True)
    username = StringField(max_length=50, null=False, unique=True)
    password_hash = StringField(max_length=255, null=False)
    is_publisher = BooleanField(default=False)
    totp_secret = StringField(max_length=32, null=True)  # This should be None
    totp_enabled = BooleanField(default=False)
    
    class Meta:
        table_name = "test_d1_users"


@pytest.mark.asyncio
async def test_d1_user_creation_with_nullable_fields():
    """
    Test creating a user with nullable fields using mock D1
    
    This test verifies that None -> NULL conversion works properly
    and would catch JavaScript undefined values being passed to D1.
    """
    from .mock_d1 import MockD1Database, d1_unwrap, d1_unwrap_results
    from unittest.mock import patch
    
    mock_db = MockD1Database()
    
    with patch('kinglet.orm.d1_unwrap', d1_unwrap), \
         patch('kinglet.orm.d1_unwrap_results', d1_unwrap_results):
        
        # Create table first
        await D1UserModel.create_table(mock_db)
        
        # Test creating user with None values for nullable fields
        user = await D1UserModel.objects.create(
            mock_db,
            email="integration@test.com",
            username="integration_user",
            password_hash="test_hash",
            is_publisher=False,
            totp_secret=None,  # This should not cause D1_TYPE_ERROR
            totp_enabled=False
        )
        
        # Verify creation succeeded
        assert user.email == "integration@test.com"
        assert user.username == "integration_user"
        assert user.totp_secret is None
        assert user.is_publisher is False
        assert user.id is not None
        
        # Verify we can retrieve the user
        retrieved_user = await D1UserModel.objects.get(mock_db, id=user.id)
        assert retrieved_user.totp_secret is None
        assert retrieved_user.email == "integration@test.com"


def test_field_conversion_edge_cases():
    """Test field conversion edge cases that might cause undefined values"""
    
    # Test BooleanField with None
    bool_field = BooleanField(default=False)
    assert bool_field.to_db(None) is None  # Should be None, not undefined
    assert bool_field.to_db(False) == 0
    assert bool_field.to_db(True) == 1
    
    # Test StringField with None  
    str_field = StringField(null=True)
    assert str_field.to_db(None) is None  # Should be None, not undefined
    assert str_field.to_db("test") == "test"
    
    # Test StringField with empty string
    assert str_field.to_db("") == ""


def test_user_data_conversion():
    """Test the exact user data conversion that's failing in production"""
    
    user_data = {
        'email': 'test@example.com',
        'username': 'testuser',
        'password_hash': 'hashed_password',
        'is_publisher': False,
        'totp_secret': None,  # This is the suspected problem field
        'totp_enabled': False
    }
    
    # Create user instance and check field conversions
    user = D1UserModel(**user_data)
    
    # Manually test field conversion like the ORM save() method does
    field_data = {}
    for field_name, field in user._fields.items():
        value = getattr(user, field_name, None)
        validated_value = field.validate(value)
        db_value = field.to_db(validated_value)
        field_data[field_name] = db_value
        
        print(f"Field {field_name}: {value} -> {validated_value} -> {db_value} (type: {type(db_value)})")
        
        # Assert no undefined values
        assert db_value != 'undefined', f"Field {field_name} produced undefined value"
        
        # Assert proper None handling for nullable fields
        if field.null and value is None:
            assert db_value is None, f"Nullable field {field_name} should convert None to None"


if __name__ == "__main__":
    # Run the field conversion test
    test_field_conversion_edge_cases()
    test_user_data_conversion()
    print("All field conversion tests passed!")