"""
Tests for ORM Error Taxonomy Integration

Verifies that database errors are properly classified into semantic ORM exceptions.
"""

import sqlite3

import pytest

from kinglet.orm import IntegerField, Model, StringField
from kinglet.orm_errors import (
    CheckViolationError,
    ConstraintRegistry,
    D1ErrorClassifier,
    DeadlockError,
    DoesNotExistError,
    ForeignKeyViolationError,
    MultipleObjectsReturnedError,
    NotNullViolationError,
    TimeoutError,
    UniqueViolationError,
    ValidationError,
)

from .mock_d1 import MockD1Database


class SampleUser(Model):
    email = StringField(max_length=100, null=False, unique=True)
    name = StringField(max_length=50, null=False)
    age = IntegerField(null=True)

    class Meta:
        table_name = "test_users"


class TestFieldValidation:
    """Test field validation raises ValidationError"""

    def test_string_field_null_validation(self):
        """Test NOT NULL validation raises ValidationError"""
        field = StringField(null=False)
        field.name = "test_field"

        with pytest.raises(ValidationError) as exc_info:
            field.validate(None)

        assert exc_info.value.field_name == "test_field"
        assert "cannot be null" in str(exc_info.value)

    def test_string_field_max_length_validation(self):
        """Test max_length validation raises ValidationError"""
        field = StringField(max_length=10)
        field.name = "test_field"

        with pytest.raises(ValidationError) as exc_info:
            field.validate("This string is too long")

        assert exc_info.value.field_name == "test_field"
        assert "too long" in str(exc_info.value)
        assert exc_info.value.value == "This string is too long"


class TestD1ErrorClassifier:
    """Test D1ErrorClassifier mapping database errors to ORM errors"""

    def test_unique_constraint_classification(self):
        """Test UNIQUE constraint violations are classified correctly"""
        # Test typical SQLite unique constraint error
        db_error = sqlite3.IntegrityError("UNIQUE constraint failed: test_users.email")

        orm_error = D1ErrorClassifier.classify_error(db_error)

        assert isinstance(orm_error, UniqueViolationError)
        assert orm_error.field_name == "email"
        assert orm_error.original_error is db_error

    def test_not_null_constraint_classification(self):
        """Test NOT NULL constraint violations are classified correctly"""
        db_error = sqlite3.IntegrityError("NOT NULL constraint failed: test_users.name")

        orm_error = D1ErrorClassifier.classify_error(db_error)

        assert isinstance(orm_error, NotNullViolationError)
        assert orm_error.field_name == "name"
        assert orm_error.original_error is db_error

    def test_generic_error_classification(self):
        """Test generic errors are classified as QueryError"""
        db_error = sqlite3.OperationalError("syntax error in SQL")

        orm_error = D1ErrorClassifier.classify_error(db_error)

        # Should be generic QueryError
        from kinglet.orm_errors import QueryError

        assert isinstance(orm_error, QueryError)
        assert orm_error.original_error is db_error

    def test_foreign_key_classification(self):
        """Test foreign key constraint violations"""
        db_error = sqlite3.IntegrityError("FOREIGN KEY constraint failed")

        orm_error = D1ErrorClassifier.classify_error(db_error)

        from kinglet.orm_errors import ForeignKeyViolationError

        assert isinstance(orm_error, ForeignKeyViolationError)
        assert orm_error.original_error is db_error


class TestQuerySetErrorIntegration:
    """Test QuerySet methods raise proper ORM errors"""

    @pytest.mark.asyncio
    async def test_get_does_not_exist(self):
        """Test QuerySet.get() raises DoesNotExistError when no records found"""
        db = MockD1Database()
        await SampleUser.create_table(db)

        with pytest.raises(DoesNotExistError) as exc_info:
            await (
                SampleUser.objects.get_queryset(db)
                .filter(email="nonexistent@example.com")
                .get()
            )

        assert exc_info.value.model_name == "SampleUser"

    @pytest.mark.asyncio
    async def test_get_multiple_objects_returned(self):
        """Test QuerySet.get() raises MultipleObjectsReturnedError when multiple records found"""
        db = MockD1Database()
        await SampleUser.create_table(db)

        # Create two users with same name
        await SampleUser.objects.create(
            db, email="user1@example.com", name="John", age=25
        )
        await SampleUser.objects.create(
            db, email="user2@example.com", name="John", age=30
        )

        with pytest.raises(MultipleObjectsReturnedError) as exc_info:
            await SampleUser.objects.get_queryset(db).filter(name="John").get()

        assert exc_info.value.model_name == "SampleUser"
        assert exc_info.value.count == 2


class TestModelErrorIntegration:
    """Test Model methods raise proper ORM errors"""

    @pytest.mark.asyncio
    async def test_save_unique_violation(self):
        """Test Model.save() converts database unique errors to UniqueViolationError"""
        db = MockD1Database()
        await SampleUser.create_table(db)

        # Create first user
        user1 = SampleUser(email="test@example.com", name="Test User")
        await user1.save(db)

        # Try to create another with same email - should raise UniqueViolationError
        user2 = SampleUser(email="test@example.com", name="Another User")

        with pytest.raises(UniqueViolationError) as exc_info:
            await user2.save(db)

        assert exc_info.value.field_name == "email"

    @pytest.mark.asyncio
    async def test_bulk_create_integrity_error(self):
        """Test Manager.bulk_create() converts database errors properly"""
        db = MockD1Database()
        await SampleUser.create_table(db)

        # Create users where one violates unique constraint
        users = [
            SampleUser(email="user1@example.com", name="User 1"),
            SampleUser(email="user1@example.com", name="User 2"),  # Duplicate email
        ]

        with pytest.raises(UniqueViolationError):
            await SampleUser.objects.bulk_create(db, users)


class TestRFC7807Responses:
    """Test RFC7807 problem+json response helpers"""

    def test_problem_json_validation_error(self):
        """Test RFC7807 response for ValidationError"""
        from kinglet.orm_errors import orm_problem_response

        error = ValidationError("email", "Invalid email format", "invalid-email")
        problem, status, headers = orm_problem_response(error, is_prod=False)

        assert status == 422
        assert headers["Content-Type"] == "application/problem+json"
        assert problem["type"] == "https://errors.kinglet.dev/validation"
        assert problem["title"] == "Validation failed"
        assert problem["field"] == "email"
        assert problem["value"] == "invalid-email"

    def test_problem_json_not_found_error(self):
        """Test RFC7807 response for DoesNotExistError"""
        from kinglet.orm_errors import orm_problem_response

        error = DoesNotExistError("SampleUser", email="test@example.com")
        problem, status, headers = orm_problem_response(error, is_prod=False)

        assert status == 404
        assert problem["type"] == "https://errors.kinglet.dev/not-found"
        assert problem["title"] == "Resource not found"
        assert problem["model"] == "SampleUser"
        assert problem["lookup"] == {"email": "test@example.com"}

    def test_problem_json_production_redaction(self):
        """Test field redaction in production mode"""
        from kinglet.orm_errors import orm_problem_response

        error = ValidationError("email", "Invalid email", "sensitive-data")

        # Development mode - shows all fields
        dev_problem, _, _ = orm_problem_response(error, is_prod=False)
        assert "field" in dev_problem
        assert "value" in dev_problem

        # Production mode - redacts sensitive fields
        prod_problem, _, _ = orm_problem_response(error, is_prod=True)
        assert "field" not in prod_problem
        assert "value" not in prod_problem
        assert prod_problem["code"] == "ValidationError"


class TestConstraintRegistry:
    """Test ConstraintRegistry functionality"""

    def test_register_constraint_with_none_type(self):
        """Test register_constraint when constraint_type is None - covers lines 82-88"""
        registry = ConstraintRegistry()

        # Register constraint without specifying type (should infer)
        registry.register_constraint(
            "users", "uq_users_email", ["email"], constraint_type=None
        )

        info = registry.get_constraint_info("users", "uq_users_email")
        assert info is not None
        assert info["fields"] == ["email"]
        assert info["type"] == "unique"  # Should be inferred from name

    def test_infer_constraint_type_coverage(self):
        """Test all branches of _infer_constraint_type - covers lines 141-147, 150"""
        registry = ConstraintRegistry()

        # Foreign key patterns - lines 141-142
        assert registry._infer_constraint_type("fk_users_tenant") == "foreign_key"
        assert registry._infer_constraint_type("users_tenant_fkey") == "foreign_key"
        assert registry._infer_constraint_type("users_foreign_key") == "foreign_key"

        # Check constraint patterns - lines 143-144
        assert registry._infer_constraint_type("ck_users_age") == "check"
        assert registry._infer_constraint_type("users_age_check") == "check"

        # Not null patterns - lines 145-146
        assert registry._infer_constraint_type("nn_users_name") == "not_null"
        assert registry._infer_constraint_type("users_name_not_null") == "not_null"

        # Primary key patterns - lines 147-148
        assert registry._infer_constraint_type("pk_users") == "primary_key"
        assert registry._infer_constraint_type("users_pkey") == "primary_key"
        assert registry._infer_constraint_type("users_primary_key") == "primary_key"

        # Unknown pattern - line 150
        assert registry._infer_constraint_type("weird_constraint_name") == "unknown"


class TestErrorConstructorMessages:
    """Test error constructors with None messages"""

    def test_foreign_key_error_none_message_with_field(self):
        """Test ForeignKeyViolationError with None message and field - covers lines 215-217"""
        error = ForeignKeyViolationError(field_name="user_id", message=None)
        assert "Foreign key constraint violation on field 'user_id'" in str(error)

    def test_foreign_key_error_none_message_no_field(self):
        """Test ForeignKeyViolationError with None message and no field"""
        error = ForeignKeyViolationError(field_name=None, message=None)
        assert "Foreign key constraint violation" in str(error)

    def test_deadlock_error_none_message(self):
        """Test DeadlockError with None message - covers lines 270-272"""
        error = DeadlockError(message=None)
        assert "Database deadlock detected - retry recommended" in str(error)
        assert error.retry_after == 0.1

    def test_timeout_error_none_message(self):
        """Test TimeoutError with None message - covers lines 279-281"""
        error = TimeoutError(message=None)
        assert "Database operation timed out - retry recommended" in str(error)
        assert error.retry_after == 1.0


class TestD1ErrorClassifierRegistryPaths:
    """Test D1ErrorClassifier registry-based error classification"""

    def test_classify_with_registry_foreign_key(self):
        """Test registry-based foreign key classification - covers lines 372-374"""
        registry = ConstraintRegistry()
        registry.register_constraint(
            "users", "fk_users_tenant", ["tenant_id"], "foreign_key"
        )

        # Mock error with constraint name
        error = Exception("CONSTRAINT fk_users_tenant failed")

        result = D1ErrorClassifier.classify_error(error, registry)
        assert isinstance(result, ForeignKeyViolationError)
        assert result.field_name == "tenant_id"

    def test_classify_with_registry_check_constraint(self):
        """Test registry-based check constraint classification - covers lines 376-377"""
        registry = ConstraintRegistry()
        registry.register_constraint("users", "ck_users_age", ["age"], "check")

        error = Exception("CHECK constraint `ck_users_age` failed")

        result = D1ErrorClassifier.classify_error(error, registry)
        assert isinstance(result, CheckViolationError)

    def test_classify_fallback_patterns_unique_with_groups(self):
        """Test fallback regex patterns for unique constraint - covers lines 382-391"""
        error = Exception("UNIQUE constraint failed: users.email")

        result = D1ErrorClassifier.classify_error(error)
        assert isinstance(result, UniqueViolationError)
        assert result.field_name == "email"

    def test_classify_fallback_patterns_unique_single_group(self):
        """Test unique constraint with single group - covers lines 389-390"""
        error = Exception("column name is not unique")

        result = D1ErrorClassifier.classify_error(error)
        assert isinstance(result, UniqueViolationError)
        assert result.field_name == "name"

    def test_classify_fallback_patterns_not_null_two_groups(self):
        """Test NOT NULL constraint with two groups - covers lines 395-403"""
        error = Exception("NOT NULL constraint failed: users.email")

        result = D1ErrorClassifier.classify_error(error)
        assert isinstance(result, NotNullViolationError)
        assert result.field_name == "email"

    def test_classify_fallback_patterns_not_null_one_group(self):
        """Test NOT NULL constraint with one group - covers lines 401-402"""
        error = Exception("column email may not be NULL")

        result = D1ErrorClassifier.classify_error(error)
        assert isinstance(result, NotNullViolationError)
        assert result.field_name == "email"

    def test_classify_fallback_foreign_key_patterns(self):
        """Test foreign key pattern matching - covers lines 406-408"""
        error = Exception("FOREIGN KEY constraint failed")

        result = D1ErrorClassifier.classify_error(error)
        assert isinstance(result, ForeignKeyViolationError)

    def test_classify_fallback_check_patterns(self):
        """Test check constraint pattern matching - covers lines 411-413"""
        error = Exception("CHECK constraint failed: age_positive")

        result = D1ErrorClassifier.classify_error(error)
        assert isinstance(result, CheckViolationError)

    def test_classify_fallback_deadlock_patterns(self):
        """Test deadlock pattern matching - covers lines 416-418"""
        error = Exception("database is locked")

        result = D1ErrorClassifier.classify_error(error)
        assert isinstance(result, DeadlockError)

    def test_classify_fallback_timeout_patterns(self):
        """Test timeout pattern matching - covers lines 420-422"""
        error = Exception("operation timed out")

        result = D1ErrorClassifier.classify_error(error)
        assert isinstance(result, TimeoutError)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
