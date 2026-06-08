"""
Kinglet Validation System
Eliminates boilerplate for input validation with decorators and validators
"""

from __future__ import annotations

import functools
import inspect
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .services import ValidationException

# Constants
VALIDATION_FAILED_MESSAGE = "Validation failed"


@dataclass
class ValidationRule:
    """Represents a validation rule"""

    validator: Callable[[Any], bool]
    error_message: str
    field_name: str | None = None


@dataclass
class ValidationResult:
    """Result of validation operation"""

    is_valid: bool
    errors: dict[str, list[str]]

    @classmethod
    def success(cls) -> ValidationResult:
        """Create successful validation result"""
        return cls(is_valid=True, errors={})

    @classmethod
    def failure(cls, errors: dict[str, list[str]]) -> ValidationResult:
        """Create failed validation result"""
        return cls(is_valid=False, errors=errors)

    def add_error(self, field: str, message: str):
        """Add an error to the result"""
        if field not in self.errors:
            self.errors[field] = []
        self.errors[field].append(message)
        self.is_valid = False


class Validator:
    """Base validator class"""

    def __init__(self, error_message: str = None):
        self.error_message = error_message or self._default_error_message()

    def _default_error_message(self) -> str:
        """Default error message for this validator"""
        return VALIDATION_FAILED_MESSAGE

    def validate(self, value: Any, field_name: str = None) -> bool:
        """Validate a value. Should be overridden by subclasses"""
        raise NotImplementedError

    def __call__(self, value: Any, field_name: str = None) -> bool:
        """Make validator callable"""
        return self.validate(value, field_name)


class RequiredValidator(Validator):
    """Validates that a field is not None/empty"""

    def _default_error_message(self) -> str:
        return "{field} is required"

    def validate(self, value: Any, field_name: str = None) -> bool:
        if value is None:
            return False
        if isinstance(value, str) and value.strip() == "":
            return False
        if hasattr(value, "__len__") and len(value) == 0:
            return False
        return True


class EmailValidator(Validator):
    """Validates email format"""

    EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

    def _default_error_message(self) -> str:
        return "{field} must be a valid email address"

    def validate(self, value: Any, field_name: str = None) -> bool:
        if value is None:
            return True  # None means field not provided - that's ok
        if not isinstance(value, str):
            return False
        if not value:  # Empty string is not a valid email
            return False
        return bool(self.EMAIL_REGEX.match(value.strip()))


class LengthValidator(Validator):
    """Validates string/list length"""

    def __init__(
        self,
        min_length: int | None = None,
        max_length: int | None = None,
        **kwargs,
    ):
        self.min_length = min_length
        self.max_length = max_length
        super().__init__(**kwargs)

    def _default_error_message(self) -> str:
        if self.min_length is not None and self.max_length is not None:
            return f"{{field}} must be between {self.min_length} and {self.max_length} characters"
        elif self.min_length is not None:
            return f"{{field}} must be at least {self.min_length} characters"
        elif self.max_length is not None:
            return f"{{field}} must be at most {self.max_length} characters"
        return "{field} length is invalid"

    def validate(self, value: Any, field_name: str = None) -> bool:
        if value is None:
            return True  # None means field not provided

        # Empty string/list has length 0, which may not meet min_length
        length = len(value)

        if self.min_length is not None and length < self.min_length:
            return False
        if self.max_length is not None and length > self.max_length:
            return False

        return True


class RangeValidator(Validator):
    """Validates numeric ranges"""

    def __init__(
        self,
        min_value: int | float | None = None,
        max_value: int | float | None = None,
        **kwargs,
    ):
        self.min_value = min_value
        self.max_value = max_value
        super().__init__(**kwargs)

    def _default_error_message(self) -> str:
        if self.min_value is not None and self.max_value is not None:
            return "{field} must be between {min_value} and {max_value}"
        elif self.min_value is not None:
            return "{field} must be at least {min_value}"
        elif self.max_value is not None:
            return "{field} must be at most {max_value}"
        return "{field} value is out of range"

    def validate(self, value: Any, field_name: str = None) -> bool:
        if value is None:
            return True

        try:
            num_value = float(value)
        except (ValueError, TypeError):
            return False

        if self.min_value is not None and num_value < self.min_value:
            return False
        if self.max_value is not None and num_value > self.max_value:
            return False

        return True


class RegexValidator(Validator):
    """Validates against regular expression pattern"""

    def __init__(self, pattern: str | re.Pattern, **kwargs):
        if isinstance(pattern, str):
            self.pattern = re.compile(pattern)
        else:
            self.pattern = pattern
        super().__init__(**kwargs)

    def _default_error_message(self) -> str:
        return "{field} format is invalid"

    def validate(self, value: Any, field_name: str = None) -> bool:
        if not value:
            return True
        if not isinstance(value, str):
            return False
        return bool(self.pattern.match(value))


class PasswordValidator(Validator):
    """Validates password strength"""

    def __init__(
        self,
        min_length: int = 8,
        require_uppercase: bool = True,
        require_lowercase: bool = True,
        require_digits: bool = True,
        require_special: bool = True,
        **kwargs,
    ):
        self.min_length = min_length
        self.require_uppercase = require_uppercase
        self.require_lowercase = require_lowercase
        self.require_digits = require_digits
        self.require_special = require_special
        super().__init__(**kwargs)

    def _default_error_message(self) -> str:
        return f"{{field}} must be at least {self.min_length} characters with uppercase, lowercase, digit, and special character"

    def validate(self, value: Any, field_name: str = None) -> bool:
        if not value or not isinstance(value, str):
            return False

        if len(value) < self.min_length:
            return False

        if self.require_uppercase and not any(c.isupper() for c in value):
            return False

        if self.require_lowercase and not any(c.islower() for c in value):
            return False

        if self.require_digits and not any(c.isdigit() for c in value):
            return False

        if self.require_special and not any(c in '!@#$%^&*(),.?":{}|<>' for c in value):
            return False

        return True


class ChoicesValidator(Validator):
    """Validates that value is in allowed choices"""

    def __init__(self, choices: list[Any], **kwargs):
        self.choices = choices
        super().__init__(**kwargs)

    def _default_error_message(self) -> str:
        return f"{{field}} must be one of: {self.choices}"

    def validate(self, value: Any, field_name: str = None) -> bool:
        if value is None:
            return True
        return value in self.choices


class DateValidator(Validator):
    """Validates date format"""

    def __init__(self, date_format: str = "%Y-%m-%d", **kwargs):
        self.date_format = date_format
        super().__init__(**kwargs)

    def _default_error_message(self) -> str:
        return "{field} must be a valid date in format {date_format}"

    def validate(self, value: Any, field_name: str = None) -> bool:
        if not value:
            return True

        if isinstance(value, datetime):
            return True

        if not isinstance(value, str):
            return False

        try:
            datetime.strptime(value, self.date_format)
            return True
        except ValueError:
            return False


class ValidationSchema:
    """Schema for validating dictionaries of data"""

    def __init__(self, rules: dict[str, list[Validator]]):
        """
        Initialize validation schema

        Args:
            rules: Dictionary mapping field names to lists of validators
        """
        self.rules = rules

    def validate(self, data: dict[str, Any]) -> ValidationResult:
        """
        Validate dictionary against schema

        Args:
            data: Dictionary to validate

        Returns:
            ValidationResult with errors if any
        """
        result = ValidationResult.success()

        for field_name, validators in self.rules.items():
            field_value = data.get(field_name)

            for validator in validators:
                if not validator.validate(field_value, field_name):
                    error_message = validator.error_message.format(
                        field=field_name,
                        min_length=getattr(validator, "min_length", None),
                        max_length=getattr(validator, "max_length", None),
                        min_value=getattr(validator, "min_value", None),
                        max_value=getattr(validator, "max_value", None),
                        choices=getattr(validator, "choices", None),
                        date_format=getattr(validator, "date_format", None),
                    )
                    result.add_error(field_name, error_message)
                    break  # Stop at first validation error for this field

        return result


def validate_schema(schema: dict[str, list[Validator]] | ValidationSchema):
    """
    Decorator to validate function arguments against a schema

    Args:
        schema: Validation schema or dict of field -> validators

    Usage:
        @validate_schema({
            'email': [RequiredValidator(), EmailValidator()],
            'age': [RequiredValidator(), RangeValidator(min_value=18)]
        })
        async def create_user(email, age):
            # Function will only be called if validation passes
            pass
    """
    if isinstance(schema, dict):
        validation_schema = ValidationSchema(schema)
    else:
        validation_schema = schema

    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Get function signature to map positional args to names
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()

            # Validate the arguments
            result = validation_schema.validate(dict(bound.arguments))

            if not result.is_valid:
                raise ValidationException(VALIDATION_FAILED_MESSAGE, result.errors)

            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Get function signature to map positional args to names
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()

            # Validate the arguments
            result = validation_schema.validate(dict(bound.arguments))

            if not result.is_valid:
                raise ValidationException(VALIDATION_FAILED_MESSAGE, result.errors)

            return func(*args, **kwargs)

        # Return appropriate wrapper based on whether function is async
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# --- helper extracted to keep validate_json tiny ---
def _make_json_validator_decorator(
    validation_schema: ValidationSchema,
    json_param: str,
):
    """Factory that returns a decorator which validates a JSON kwarg."""

    def _ensure_valid_kwargs(kwargs: dict[str, Any]) -> None:
        if json_param not in kwargs:
            raise ValidationException(f"Missing required parameter: {json_param}")

        data = kwargs[json_param]
        if not isinstance(data, dict):
            raise ValidationException(f"Parameter {json_param} must be a dictionary")

        result = validation_schema.validate(data)
        if not result.is_valid:
            raise ValidationException(VALIDATION_FAILED_MESSAGE, result.errors)

    def decorator(func: Callable):
        is_coro = inspect.iscoroutinefunction(func)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            _ensure_valid_kwargs(kwargs)
            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            _ensure_valid_kwargs(kwargs)
            return func(*args, **kwargs)

        return async_wrapper if is_coro else sync_wrapper

    return decorator


def validate_json(
    schema: dict[str, list[Validator]] | ValidationSchema,
    json_param: str = "data",
):
    """
    Decorator to validate JSON data from a keyword argument (default: 'data').
    Usage:
        @validate_json({"email": [RequiredValidator(), EmailValidator()]})
        async def handler(*, data): ...
    """
    validation_schema = (
        schema if isinstance(schema, ValidationSchema) else ValidationSchema(schema)
    )
    return _make_json_validator_decorator(validation_schema, json_param)


# Quick validation functions for common patterns
def validate_email(email: str) -> bool:
    """Quick email validation"""
    validator = EmailValidator()
    return validator.validate(email)


def validate_password(password: str, min_length: int = 8) -> tuple[bool, str]:
    """Quick password validation with detailed message"""
    validator = PasswordValidator(min_length=min_length)
    is_valid = validator.validate(password)
    if not is_valid:
        message = validator.error_message.format(field="password")
    else:
        message = "Password is valid"
    return is_valid, message


def validate_required_fields(
    data: dict[str, Any], fields: list[str]
) -> ValidationResult:
    """Quick validation for required fields"""
    result = ValidationResult.success()

    for field in fields:
        if field not in data or not data[field]:
            result.add_error(field, f"{field} is required")

    return result


# Pre-built validation schemas for common use cases
USER_REGISTRATION_SCHEMA = ValidationSchema(
    {
        "email": [RequiredValidator(), EmailValidator()],
        "password": [RequiredValidator(), PasswordValidator()],
        "name": [RequiredValidator(), LengthValidator(min_length=2, max_length=100)],
        "phone": [LengthValidator(min_length=10, max_length=20)],  # Optional
        "age": [RangeValidator(min_value=13, max_value=120)],  # Optional
    }
)


USER_LOGIN_SCHEMA = ValidationSchema(
    {
        "email": [RequiredValidator(), EmailValidator()],
        "password": [RequiredValidator()],
    }
)


LISTING_CREATION_SCHEMA = ValidationSchema(
    {
        "title": [RequiredValidator(), LengthValidator(min_length=5, max_length=200)],
        "description": [LengthValidator(max_length=5000)],
        "price_per_day": [RequiredValidator(), RangeValidator(min_value=0)],
        "location": [
            RequiredValidator(),
            LengthValidator(min_length=2, max_length=200),
        ],
        "type": [
            RequiredValidator(),
            ChoicesValidator(["caravan", "campervan", "trailer", "motorhome"]),
        ],
        "sleeps": [RangeValidator(min_value=1, max_value=20)],
    }
)
