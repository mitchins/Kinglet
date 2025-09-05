"""
Tests for kinglet.validation module
Tests validators, schemas, decorators, and validation utilities
"""

import re
from datetime import datetime

import pytest

from kinglet.services import ValidationException
from kinglet.validation import (
    LISTING_CREATION_SCHEMA,
    USER_LOGIN_SCHEMA,
    USER_REGISTRATION_SCHEMA,
    VALIDATION_FAILED_MESSAGE,
    ChoicesValidator,
    DateValidator,
    EmailValidator,
    LengthValidator,
    PasswordValidator,
    RangeValidator,
    RegexValidator,
    RequiredValidator,
    ValidationResult,
    ValidationRule,
    ValidationSchema,
    Validator,
    validate_email,
    validate_json,
    validate_password,
    validate_required_fields,
    validate_schema,
)


class TestValidationResult:
    """Test ValidationResult class"""

    def test_success_creation(self):
        """Test creating successful validation result"""
        result = ValidationResult.success()

        assert result.is_valid is True
        assert result.errors == {}

    def test_failure_creation(self):
        """Test creating failed validation result"""
        errors = {"email": ["Invalid email"], "name": ["Required"]}
        result = ValidationResult.failure(errors)

        assert result.is_valid is False
        assert result.errors == errors

    def test_add_error(self):
        """Test adding errors to validation result"""
        result = ValidationResult.success()
        result.add_error("email", "Invalid format")
        result.add_error("email", "Too short")
        result.add_error("name", "Required field")

        assert result.errors["email"] == ["Invalid format", "Too short"]
        assert result.errors["name"] == ["Required field"]


class TestValidationRule:
    """Test ValidationRule dataclass"""

    def test_validation_rule_creation(self):
        """Test creating validation rule"""

        def validator_func(x):
            return x is not None

        rule = ValidationRule(
            validator=validator_func,
            error_message="Field is required",
            field_name="email",
        )

        assert rule.validator is validator_func
        assert rule.error_message == "Field is required"
        assert rule.field_name == "email"


class TestValidator:
    """Test base Validator class"""

    def test_validator_with_custom_message(self):
        """Test validator with custom error message"""

        class CustomValidator(Validator):
            def validate(self, value, field_name=None):
                return value == "valid"

        validator = CustomValidator(error_message="Custom error message")

        assert validator.error_message == "Custom error message"

    def test_validator_with_default_message(self):
        """Test validator with default error message"""

        class CustomValidator(Validator):
            def validate(self, value, field_name=None):
                return True

        validator = CustomValidator()

        assert validator.error_message == VALIDATION_FAILED_MESSAGE

    def test_validator_call_method(self):
        """Test validator __call__ method"""

        class CustomValidator(Validator):
            def validate(self, value, field_name=None):
                return value == "valid"

        validator = CustomValidator()

        assert validator("valid") is True
        assert validator("invalid") is False

    def test_validator_not_implemented(self):
        """Test that base Validator raises NotImplementedError"""
        validator = Validator()

        with pytest.raises(NotImplementedError):
            validator.validate("test")


class TestRequiredValidator:
    """Test RequiredValidator"""

    def test_required_validator_valid_values(self):
        """Test required validator with valid values"""
        validator = RequiredValidator()

        assert validator.validate("test") is True
        assert validator.validate(123) is True
        assert validator.validate([1, 2, 3]) is True
        assert validator.validate({"key": "value"}) is True

    def test_required_validator_invalid_values(self):
        """Test required validator with invalid values"""
        validator = RequiredValidator()

        assert validator.validate(None) is False
        assert validator.validate("") is False
        assert validator.validate([]) is False
        assert validator.validate({}) is False

    def test_required_validator_error_message(self):
        """Test required validator error message"""
        validator = RequiredValidator()
        assert "required" in validator.error_message.lower()


class TestEmailValidator:
    """Test EmailValidator"""

    def test_email_validator_valid_emails(self):
        """Test email validator with valid emails"""
        validator = EmailValidator()

        assert validator.validate("test@example.com") is True
        assert validator.validate("user.name+tag@domain.co.uk") is True
        assert validator.validate("test123@test-domain.org") is True

    def test_email_validator_invalid_emails(self):
        """Test email validator with invalid emails"""
        validator = EmailValidator()

        assert validator.validate("invalid") is False
        assert validator.validate("@example.com") is False
        assert validator.validate("test@") is False
        assert validator.validate("test.example.com") is False
        assert validator.validate("") is False

    def test_email_validator_none_value(self):
        """Test email validator with None value"""
        validator = EmailValidator()
        assert validator.validate(None) is True  # None is allowed

    def test_email_validator_whitespace_handling(self):
        """Test email validator strips whitespace"""
        validator = EmailValidator()
        assert validator.validate("  test@example.com  ") is True


class TestLengthValidator:
    """Test LengthValidator"""

    def test_length_validator_min_length(self):
        """Test length validator with minimum length"""
        validator = LengthValidator(min_length=3)

        assert validator.validate("abc") is True
        assert validator.validate("abcd") is True
        assert validator.validate("ab") is False
        assert validator.validate("") is False

    def test_length_validator_max_length(self):
        """Test length validator with maximum length"""
        validator = LengthValidator(max_length=5)

        assert validator.validate("abc") is True
        assert validator.validate("abcde") is True
        assert validator.validate("abcdef") is False

    def test_length_validator_range(self):
        """Test length validator with min and max"""
        validator = LengthValidator(min_length=3, max_length=5)

        assert validator.validate("abc") is True
        assert validator.validate("abcd") is True
        assert validator.validate("abcde") is True
        assert validator.validate("ab") is False
        assert validator.validate("abcdef") is False

    def test_length_validator_list(self):
        """Test length validator with lists"""
        validator = LengthValidator(min_length=2, max_length=3)

        assert validator.validate([1, 2]) is True
        assert validator.validate([1, 2, 3]) is True
        assert validator.validate([1]) is False
        assert validator.validate([1, 2, 3, 4]) is False

    def test_length_validator_none_value(self):
        """Test length validator with None"""
        validator = LengthValidator(min_length=1)
        assert validator.validate(None) is True

    def test_length_validator_error_messages(self):
        """Test length validator error messages"""
        validator_min = LengthValidator(min_length=3)
        validator_max = LengthValidator(max_length=5)
        validator_range = LengthValidator(min_length=3, max_length=5)

        assert "at least 3" in validator_min.error_message
        assert "at most 5" in validator_max.error_message
        assert "between 3 and 5" in validator_range.error_message


class TestRangeValidator:
    """Test RangeValidator"""

    def test_range_validator_min_value(self):
        """Test range validator with minimum value"""
        validator = RangeValidator(min_value=10)

        assert validator.validate(10) is True
        assert validator.validate(15) is True
        assert validator.validate(9) is False

    def test_range_validator_max_value(self):
        """Test range validator with maximum value"""
        validator = RangeValidator(max_value=100)

        assert validator.validate(50) is True
        assert validator.validate(100) is True
        assert validator.validate(101) is False

    def test_range_validator_range(self):
        """Test range validator with min and max"""
        validator = RangeValidator(min_value=10, max_value=100)

        assert validator.validate(50) is True
        assert validator.validate(10) is True
        assert validator.validate(100) is True
        assert validator.validate(9) is False
        assert validator.validate(101) is False

    def test_range_validator_floats(self):
        """Test range validator with float values"""
        validator = RangeValidator(min_value=1.5, max_value=10.5)

        assert validator.validate(5.5) is True
        assert validator.validate(1.5) is True
        assert validator.validate(10.5) is True
        assert validator.validate(1.4) is False
        assert validator.validate(10.6) is False

    def test_range_validator_none_value(self):
        """Test range validator with None"""
        validator = RangeValidator(min_value=1)
        assert validator.validate(None) is True

    def test_range_validator_non_numeric(self):
        """Test range validator with non-numeric values"""
        validator = RangeValidator(min_value=1, max_value=10)

        assert validator.validate("not_a_number") is False
        assert validator.validate([1, 2, 3]) is False


class TestRegexValidator:
    """Test RegexValidator"""

    def test_regex_validator_string_pattern(self):
        """Test regex validator with string pattern"""
        validator = RegexValidator(r"^\d{3}-\d{3}-\d{4}$")

        assert validator.validate("123-456-7890") is True
        assert validator.validate("invalid") is False

    def test_regex_validator_compiled_pattern(self):
        """Test regex validator with compiled pattern"""
        pattern = re.compile(r"^[A-Z][a-z]+$")
        validator = RegexValidator(pattern)

        assert validator.validate("Hello") is True
        assert validator.validate("hello") is False
        assert validator.validate("HELLO") is False

    def test_regex_validator_none_value(self):
        """Test regex validator with None"""
        validator = RegexValidator(r"\d+")
        assert validator.validate(None) is True

    def test_regex_validator_non_string(self):
        """Test regex validator with non-string values"""
        validator = RegexValidator(r"\d+")

        assert validator.validate(123) is False
        assert validator.validate([1, 2, 3]) is False


class TestPasswordValidator:
    """Test PasswordValidator"""

    def test_password_validator_valid_passwords(self):
        """Test password validator with valid passwords"""
        validator = PasswordValidator(min_length=8)

        # Valid passwords must have uppercase, lowercase, digit, and special char
        assert validator.validate("Password123!") is True
        assert validator.validate("MyP@ssw0rd") is True

    def test_password_validator_too_short(self):
        """Test password validator with short passwords"""
        validator = PasswordValidator(min_length=8)

        assert validator.validate("short") is False
        assert validator.validate("") is False

    def test_password_validator_none_value(self):
        """Test password validator with None"""
        validator = PasswordValidator()
        assert validator.validate(None) is False  # Passwords are required

    def test_password_validator_custom_requirements(self):
        """Test password validator with custom requirements"""
        # Disable some requirements for a less strict validator
        validator = PasswordValidator(
            min_length=12,
            require_uppercase=False,
            require_lowercase=True,
            require_digits=False,
            require_special=False,
        )

        # This password is long and has lowercase, so it passes
        assert validator.validate("passwordlong") is True
        assert validator.validate("short") is False


class TestChoicesValidator:
    """Test ChoicesValidator"""

    def test_choices_validator_valid_choices(self):
        """Test choices validator with valid values"""
        validator = ChoicesValidator(["red", "green", "blue"])

        assert validator.validate("red") is True
        assert validator.validate("green") is True
        assert validator.validate("blue") is True

    def test_choices_validator_invalid_choices(self):
        """Test choices validator with invalid values"""
        validator = ChoicesValidator(["red", "green", "blue"])

        assert validator.validate("yellow") is False
        assert validator.validate("purple") is False

    def test_choices_validator_none_value(self):
        """Test choices validator with None"""
        validator = ChoicesValidator(["option1", "option2"])
        assert validator.validate(None) is True

    def test_choices_validator_error_message(self):
        """Test choices validator error message format"""
        choices = ["red", "green", "blue"]
        validator = ChoicesValidator(choices)

        error_msg = validator._default_error_message()
        assert "red" in error_msg
        assert "green" in error_msg
        assert "blue" in error_msg


class TestDateValidator:
    """Test DateValidator"""

    def test_date_validator_valid_dates(self):
        """Test date validator with valid date strings"""
        validator = DateValidator()

        assert validator.validate("2023-12-25") is True
        assert validator.validate("2023-01-01") is True

    def test_date_validator_invalid_dates(self):
        """Test date validator with invalid date strings"""
        validator = DateValidator()

        assert validator.validate("invalid-date") is False
        assert validator.validate("2023-13-01") is False  # Invalid month
        assert validator.validate("2023-02-30") is False  # Invalid day

    def test_date_validator_custom_format(self):
        """Test date validator with custom format"""
        validator = DateValidator(date_format="%d/%m/%Y")

        assert validator.validate("25/12/2023") is True
        assert validator.validate("2023-12-25") is False  # Wrong format

    def test_date_validator_none_value(self):
        """Test date validator with None"""
        validator = DateValidator()
        assert validator.validate(None) is True

    def test_date_validator_datetime_object(self):
        """Test date validator with datetime object"""
        validator = DateValidator()
        date_obj = datetime(2023, 12, 25)

        assert validator.validate(date_obj) is True


class TestValidationSchema:
    """Test ValidationSchema class"""

    def test_validation_schema_creation(self):
        """Test creating validation schema"""
        rules = {
            "email": [RequiredValidator(), EmailValidator()],
            "age": [RequiredValidator(), RangeValidator(min_value=18)],
        }
        schema = ValidationSchema(rules)

        assert schema.rules == rules

    def test_validation_schema_success(self):
        """Test validation schema with valid data"""
        schema = ValidationSchema(
            {
                "email": [RequiredValidator(), EmailValidator()],
                "name": [RequiredValidator(), LengthValidator(min_length=2)],
            }
        )

        data = {"email": "test@example.com", "name": "John"}
        result = schema.validate(data)

        assert result.is_valid is True
        assert result.errors == {}

    def test_validation_schema_failures(self):
        """Test validation schema with invalid data"""
        schema = ValidationSchema(
            {
                "email": [RequiredValidator(), EmailValidator()],
                "age": [RequiredValidator(), RangeValidator(min_value=18)],
            }
        )

        data = {"email": "invalid-email", "age": 15}
        result = schema.validate(data)

        assert result.is_valid is False
        assert "email" in result.errors
        assert "age" in result.errors

    def test_validation_schema_missing_fields(self):
        """Test validation schema with missing required fields"""
        schema = ValidationSchema(
            {"email": [RequiredValidator()], "name": [RequiredValidator()]}
        )

        data = {"email": "test@example.com"}  # Missing name
        result = schema.validate(data)

        assert result.is_valid is False
        assert "name" in result.errors

    def test_validation_schema_extra_fields(self):
        """Test validation schema ignores extra fields"""
        schema = ValidationSchema({"name": [RequiredValidator()]})

        data = {"name": "John", "extra_field": "ignored"}
        result = schema.validate(data)

        assert result.is_valid is True


class TestValidateSchemaDecorator:
    """Test validate_schema decorator"""

    def test_validate_schema_decorator_success(self):
        """Test validate_schema decorator with valid data"""
        schema = ValidationSchema(
            {"name": [RequiredValidator()], "age": [RangeValidator(min_value=18)]}
        )

        @validate_schema(schema)
        def test_func(name, age):
            return {"name": name, "age": age}

        result = test_func(name="John", age=25)
        assert result == {"name": "John", "age": 25}

    def test_validate_schema_decorator_failure(self):
        """Test validate_schema decorator with invalid data"""
        schema = ValidationSchema(
            {"name": [RequiredValidator()], "age": [RangeValidator(min_value=18)]}
        )

        @validate_schema(schema)
        def test_func(name, age):
            return {"name": name, "age": age}

        with pytest.raises(ValidationException) as exc_info:
            test_func(name="", age=15)

        assert exc_info.value.field_errors is not None
        assert "name" in exc_info.value.field_errors
        assert "age" in exc_info.value.field_errors

    @pytest.mark.asyncio
    async def test_validate_schema_decorator_async(self):
        """Test validate_schema decorator with async function"""
        schema = ValidationSchema({"name": [RequiredValidator()]})

        @validate_schema(schema)
        async def test_func(name):
            return {"processed": name}

        result = await test_func(name="John")
        assert result == {"processed": "John"}

    def test_validate_schema_decorator_dict_schema(self):
        """Test validate_schema decorator with dict schema"""

        @validate_schema({"email": [RequiredValidator(), EmailValidator()]})
        def test_func(email):
            return {"email": email}

        result = test_func(email="test@example.com")
        assert result == {"email": "test@example.com"}


class TestValidateJsonDecorator:
    """Test validate_json decorator"""

    def test_validate_json_decorator_success(self):
        """Test validate_json decorator with valid data"""
        schema = ValidationSchema({"name": [RequiredValidator()]})

        @validate_json(schema)
        def test_func(data):
            return {"processed": data["name"]}

        result = test_func(data={"name": "John"})
        assert result == {"processed": "John"}

    def test_validate_json_decorator_failure(self):
        """Test validate_json decorator with invalid data"""
        schema = ValidationSchema({"name": [RequiredValidator()]})

        @validate_json(schema)
        def test_func(data):
            return data

        with pytest.raises(ValidationException):
            test_func(data={"name": ""})

    def test_validate_json_decorator_missing_param(self):
        """Test validate_json decorator with missing data parameter"""
        schema = ValidationSchema({"name": [RequiredValidator()]})

        @validate_json(schema)
        def test_func(data):
            return data

        with pytest.raises(ValidationException, match="Missing required parameter"):
            test_func()

    def test_validate_json_decorator_non_dict_data(self):
        """Test validate_json decorator with non-dict data"""
        schema = ValidationSchema({"name": [RequiredValidator()]})

        @validate_json(schema)
        def test_func(data):
            return data

        with pytest.raises(ValidationException, match="must be a dictionary"):
            test_func(data="not_a_dict")

    @pytest.mark.asyncio
    async def test_validate_json_decorator_async(self):
        """Test validate_json decorator with async function"""
        schema = ValidationSchema({"name": [RequiredValidator()]})

        @validate_json(schema)
        async def test_func(data):
            return {"async_processed": data["name"]}

        result = await test_func(data={"name": "John"})
        assert result == {"async_processed": "John"}

    def test_validate_json_decorator_custom_param_name(self):
        """Test validate_json decorator with custom parameter name"""
        schema = ValidationSchema({"name": [RequiredValidator()]})

        @validate_json(schema, json_param="json_data")
        def test_func(json_data):
            return json_data

        result = test_func(json_data={"name": "John"})
        assert result == {"name": "John"}


class TestUtilityFunctions:
    """Test utility validation functions"""

    def test_validate_email_function(self):
        """Test validate_email utility function"""
        assert validate_email("test@example.com") is True
        assert validate_email("invalid-email") is False

    def test_validate_password_function(self):
        """Test validate_password utility function"""
        is_valid, message = validate_password("ValidP@ssw0rd")
        assert is_valid is True
        assert "valid" in message.lower()

        is_valid, message = validate_password("short")
        assert is_valid is False
        assert "password" in message.lower()

    def test_validate_required_fields_function(self):
        """Test validate_required_fields utility function"""
        data = {"name": "John", "email": "test@example.com"}
        result = validate_required_fields(data, ["name", "email"])

        assert result.is_valid is True

    def test_validate_required_fields_missing(self):
        """Test validate_required_fields with missing fields"""
        data = {"name": "John"}
        result = validate_required_fields(data, ["name", "email"])

        assert result.is_valid is False
        assert "email" in result.errors

    def test_validate_required_fields_empty_values(self):
        """Test validate_required_fields with empty values"""
        data = {"name": "", "email": "test@example.com"}
        result = validate_required_fields(data, ["name", "email"])

        assert result.is_valid is False
        assert "name" in result.errors


class TestPredefinedSchemas:
    """Test predefined validation schemas"""

    def test_user_registration_schema_exists(self):
        """Test that USER_REGISTRATION_SCHEMA is defined"""
        assert USER_REGISTRATION_SCHEMA is not None
        assert isinstance(USER_REGISTRATION_SCHEMA, ValidationSchema)

    def test_user_login_schema_exists(self):
        """Test that USER_LOGIN_SCHEMA is defined"""
        assert USER_LOGIN_SCHEMA is not None
        assert isinstance(USER_LOGIN_SCHEMA, ValidationSchema)

    def test_listing_creation_schema_exists(self):
        """Test that LISTING_CREATION_SCHEMA is defined"""
        assert LISTING_CREATION_SCHEMA is not None
        assert isinstance(LISTING_CREATION_SCHEMA, ValidationSchema)

    def test_user_registration_schema_validation(self):
        """Test USER_REGISTRATION_SCHEMA with valid data"""
        valid_data = {
            "email": "test@example.com",
            "name": "Test User",
            "password": "SecureP@ssw0rd123",
        }

        result = USER_REGISTRATION_SCHEMA.validate(valid_data)
        assert result.is_valid is True

    def test_user_login_schema_validation(self):
        """Test USER_LOGIN_SCHEMA with valid data"""
        valid_data = {"email": "test@example.com", "password": "password123"}

        result = USER_LOGIN_SCHEMA.validate(valid_data)
        assert result.is_valid is True

    def test_listing_creation_schema_validation(self):
        """Test LISTING_CREATION_SCHEMA with valid data"""
        valid_data = {
            "title": "Test Listing",
            "description": "A test listing description",
            "price_per_day": 99.99,
            "location": "New York",
            "type": "caravan",
        }

        result = LISTING_CREATION_SCHEMA.validate(valid_data)
        assert result.is_valid is True


class TestConstants:
    """Test validation constants"""

    def test_validation_failed_message_constant(self):
        """Test VALIDATION_FAILED_MESSAGE constant exists and is used"""
        assert VALIDATION_FAILED_MESSAGE == "Validation failed"

        # Test it's used in validators
        validator = Validator()
        assert validator._default_error_message() == VALIDATION_FAILED_MESSAGE
