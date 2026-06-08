"""
Kinglet Service Layer Utilities
Eliminates boilerplate in service layer patterns
"""

from __future__ import annotations

import asyncio
import functools
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ServiceResultType(Enum):
    SUCCESS = "success"
    ERROR = "error"
    VALIDATION_ERROR = "validation_error"
    NOT_FOUND = "not_found"
    PERMISSION_DENIED = "permission_denied"


@dataclass
class ServiceResult:
    """
    Standardized service result pattern to eliminate boilerplate
    Replaces the common Tuple[bool, Dict[str, Any]] pattern
    """

    success: bool
    data: dict[str, Any] | None = None
    message: str | None = None
    error_code: str | None = None
    error_details: str | None = None
    result_type: ServiceResultType = ServiceResultType.SUCCESS

    @classmethod
    def success_result(
        cls, data: Any = None, message: str = "Operation successful"
    ) -> ServiceResult:
        """Create a success result"""
        # Extract nested conditional expression
        formatted_data = cls._format_success_data(data)
        return cls(
            success=True,
            data=formatted_data,
            message=message,
            result_type=ServiceResultType.SUCCESS,
        )

    @classmethod
    def error_result(
        cls,
        message: str,
        error_code: str = "OPERATION_FAILED",
        error_details: str | None = None,
        result_type: ServiceResultType = ServiceResultType.ERROR,
    ) -> ServiceResult:
        """Create an error result"""
        return cls(
            success=False,
            data={},
            message=message,
            error_code=error_code,
            error_details=error_details,
            result_type=result_type,
        )

    @classmethod
    def validation_error(
        cls, message: str, field_errors: dict[str, str] | None = None
    ) -> ServiceResult:
        """Create a validation error result"""
        return cls(
            success=False,
            data={"field_errors": field_errors or {}},
            message=message,
            error_code="VALIDATION_ERROR",
            result_type=ServiceResultType.VALIDATION_ERROR,
        )

    @classmethod
    def not_found(cls, message: str = "Resource not found") -> ServiceResult:
        """Create a not found result"""
        return cls(
            success=False,
            data={},
            message=message,
            error_code="NOT_FOUND",
            result_type=ServiceResultType.NOT_FOUND,
        )

    @classmethod
    def permission_denied(cls, message: str = "Permission denied") -> ServiceResult:
        """Create a permission denied result"""
        return cls(
            success=False,
            data={},
            message=message,
            error_code="PERMISSION_DENIED",
            result_type=ServiceResultType.PERMISSION_DENIED,
        )

    @staticmethod
    def _format_success_data(data: Any) -> dict[str, Any]:
        """Format data for success result"""
        if isinstance(data, dict):
            return data
        elif data is not None:
            return {"result": data}
        else:
            return {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses"""
        result = {"success": self.success, "message": self.message}

        if self.success and self.data:
            result.update(self.data)
        elif not self.success:
            result["error"] = {"code": self.error_code, "message": self.message}
            if self.error_details:
                result["error"]["details"] = self.error_details
            if self.data and self.data.get("field_errors"):
                result["error"]["field_errors"] = self.data["field_errors"]

        return result

    def to_tuple(self) -> tuple[bool, dict[str, Any]]:
        """Convert to legacy tuple format for backward compatibility"""
        if self.success:
            return True, self.data or {}
        else:
            error_data = {"error": self.message, "code": self.error_code}
            if self.error_details:
                error_data["details"] = self.error_details
            return False, error_data


class ServiceException(Exception):
    """Base exception for service layer operations"""

    def __init__(
        self,
        message: str,
        error_code: str = "SERVICE_ERROR",
        details: str | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details


class ValidationException(ServiceException):
    """Exception for validation errors"""

    def __init__(self, message: str, field_errors: dict[str, str] | None = None):
        super().__init__(message, "VALIDATION_ERROR")
        self.field_errors = field_errors or {}


def _convert_function_result_to_service_result(result) -> ServiceResult:
    """Convert various function return types to ServiceResult"""
    # If function returns ServiceResult, pass through
    if isinstance(result, ServiceResult):
        return result

    # If function returns tuple (legacy pattern), convert
    if isinstance(result, tuple) and len(result) == 2:
        success, data = result
        if success:
            return ServiceResult.success_result(data)
        else:
            return ServiceResult.error_result(
                data.get("error", "Operation failed"),
                data.get("code", "OPERATION_FAILED"),
                data.get("details"),
            )

    # If function returns data directly, wrap in success
    return ServiceResult.success_result(result)


def handle_service_exceptions(func: Callable) -> Callable:
    """
    Decorator to handle exceptions and convert them to ServiceResult
    Eliminates try/catch boilerplate in service methods
    """

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs) -> ServiceResult:
        try:
            result = await func(*args, **kwargs)
            return _convert_function_result_to_service_result(result)
        except ValidationException as e:
            return ServiceResult.validation_error(e.message, e.field_errors)
        except ServiceException as e:
            return ServiceResult.error_result(e.message, e.error_code, e.details)
        except Exception as e:
            # Log unexpected exceptions (you'd use your logger here)
            traceback.format_exc()
            return ServiceResult.error_result(
                "An unexpected error occurred", "INTERNAL_ERROR", str(e)
            )

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs) -> ServiceResult:
        try:
            result = func(*args, **kwargs)
            return _convert_function_result_to_service_result(result)
        except ValidationException as e:
            return ServiceResult.validation_error(e.message, e.field_errors)
        except ServiceException as e:
            return ServiceResult.error_result(e.message, e.error_code, e.details)
        except Exception as e:
            traceback.format_exc()
            return ServiceResult.error_result(
                "An unexpected error occurred", "INTERNAL_ERROR", str(e)
            )

    # Return appropriate wrapper based on whether function is async
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper


class BaseService[T]:
    """
    Base service class with common patterns
    Provides standard CRUD operations and utilities
    """

    def __init__(self, db, model_class: T | None = None):
        self.db = db
        self.model_class = model_class

    def _get_model_class(self) -> type[T]:
        """Get model class from generic type or explicit assignment"""
        if self.model_class:
            return self.model_class

        # Try to get from generic type annotation
        if hasattr(self.__class__, "__orig_bases__"):
            for base in self.__class__.__orig_bases__:
                if hasattr(base, "__args__") and base.__args__:
                    return base.__args__[0]

        raise ValueError(
            "Model class not specified. Set model_class attribute or use Generic[ModelClass]"
        )

    @handle_service_exceptions
    async def create(self, data: dict[str, Any], message: str = None) -> ServiceResult:
        """Generic create operation"""
        model_class = self._get_model_class()

        # Create instance
        instance = await model_class.objects.create(self.db, **data)

        return ServiceResult.success_result(
            instance.to_dict() if hasattr(instance, "to_dict") else instance.__dict__,
            message or f"{model_class.__name__} created successfully",
        )

    @handle_service_exceptions
    async def get_by_id(self, item_id: Any) -> ServiceResult:
        """Generic get by ID operation"""
        model_class = self._get_model_class()

        instance = await model_class.objects.get(self.db, id=item_id)
        if not instance:
            return ServiceResult.not_found(f"{model_class.__name__} not found")

        return ServiceResult.success_result(
            instance.to_dict() if hasattr(instance, "to_dict") else instance.__dict__
        )

    @handle_service_exceptions
    async def update(
        self, item_id: Any, data: dict[str, Any], message: str = None
    ) -> ServiceResult:
        """Generic update operation"""
        model_class = self._get_model_class()

        # Check if exists
        instance = await model_class.objects.get(self.db, id=item_id)
        if not instance:
            return ServiceResult.not_found(f"{model_class.__name__} not found")

        # Update
        await model_class.objects.filter(self.db, id=item_id).update(**data)
        updated_instance = await model_class.objects.get(self.db, id=item_id)

        return ServiceResult.success_result(
            updated_instance.to_dict()
            if hasattr(updated_instance, "to_dict")
            else updated_instance.__dict__,
            message or f"{model_class.__name__} updated successfully",
        )

    @handle_service_exceptions
    async def delete(
        self, item_id: Any, soft_delete: bool = True, message: str = None
    ) -> ServiceResult:
        """Generic delete operation (soft delete by default)"""
        model_class = self._get_model_class()

        # Check if exists
        instance = await model_class.objects.get(self.db, id=item_id)
        if not instance:
            return ServiceResult.not_found(f"{model_class.__name__} not found")

        if soft_delete and hasattr(instance, "status"):
            # Soft delete by setting status
            await model_class.objects.filter(self.db, id=item_id).update(
                status="deleted"
            )
        else:
            # Hard delete
            await model_class.objects.filter(self.db, id=item_id).delete()

        return ServiceResult.success_result(
            {"id": item_id}, message or f"{model_class.__name__} deleted successfully"
        )

    @handle_service_exceptions
    async def list_items(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str = "-created_at",
    ) -> ServiceResult:
        """Generic list operation with filtering"""
        model_class = self._get_model_class()
        filters = filters or {}

        # Build query
        query = model_class.objects.filter(self.db, **filters)

        # Apply ordering
        if order_by:
            query = query.order_by(order_by)

        # Apply pagination
        items = await query.limit(limit).offset(offset).all()

        # Convert to dicts
        items_data = []
        for item in items:
            if hasattr(item, "to_dict"):
                items_data.append(item.to_dict())
            else:
                items_data.append(item.__dict__)

        return ServiceResult.success_result(
            {
                "items": items_data,
                "pagination": {
                    "limit": limit,
                    "offset": offset,
                    "count": len(items_data),
                },
            }
        )
