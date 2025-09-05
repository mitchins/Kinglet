"""
Tests for kinglet.services module
Tests ServiceResult, exceptions, decorators, and BaseService functionality
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from kinglet.services import (
    BaseService,
    ServiceException,
    ServiceResult,
    ServiceResultType,
    ValidationException,
    _convert_function_result_to_service_result,
    handle_service_exceptions,
)


class TestServiceResult:
    """Test ServiceResult class functionality"""

    def test_success_result_creation(self):
        """Test creating success results"""
        result = ServiceResult.success_result({"id": 1, "name": "test"})

        assert result.success is True
        assert result.data == {"id": 1, "name": "test"}
        assert result.message == "Operation successful"
        assert result.result_type == ServiceResultType.SUCCESS

    def test_success_result_with_non_dict_data(self):
        """Test success result with non-dict data gets wrapped"""
        result = ServiceResult.success_result("test_string")

        assert result.success is True
        assert result.data == {"result": "test_string"}

    def test_success_result_with_none_data(self):
        """Test success result with None data"""
        result = ServiceResult.success_result(None)

        assert result.success is True
        assert result.data == {}

    def test_error_result_creation(self):
        """Test creating error results"""
        result = ServiceResult.error_result(
            "Something went wrong",
            error_code="CUSTOM_ERROR",
            error_details="Additional details",
        )

        assert result.success is False
        assert result.message == "Something went wrong"
        assert result.error_code == "CUSTOM_ERROR"
        assert result.error_details == "Additional details"
        assert result.result_type == ServiceResultType.ERROR

    def test_validation_error_result(self):
        """Test creating validation error results"""
        field_errors = {"email": "Invalid email format", "name": "Required field"}
        result = ServiceResult.validation_error("Validation failed", field_errors)

        assert result.success is False
        assert result.message == "Validation failed"
        assert result.error_code == "VALIDATION_ERROR"
        assert result.result_type == ServiceResultType.VALIDATION_ERROR
        assert result.data["field_errors"] == field_errors

    def test_not_found_result(self):
        """Test creating not found results"""
        result = ServiceResult.not_found("Resource not found")

        assert result.success is False
        assert result.message == "Resource not found"
        assert result.error_code == "NOT_FOUND"
        assert result.result_type == ServiceResultType.NOT_FOUND

    def test_permission_denied_result(self):
        """Test creating permission denied results"""
        result = ServiceResult.permission_denied("Access denied")

        assert result.success is False
        assert result.message == "Access denied"
        assert result.error_code == "PERMISSION_DENIED"
        assert result.result_type == ServiceResultType.PERMISSION_DENIED

    def test_to_dict_success(self):
        """Test converting success result to dictionary"""
        result = ServiceResult.success_result({"id": 1, "name": "test"})
        result_dict = result.to_dict()

        assert result_dict["success"] is True
        assert result_dict["message"] == "Operation successful"
        assert result_dict["id"] == 1
        assert result_dict["name"] == "test"

    def test_to_dict_error(self):
        """Test converting error result to dictionary"""
        result = ServiceResult.error_result(
            "Something went wrong",
            error_code="CUSTOM_ERROR",
            error_details="Additional details",
        )
        result_dict = result.to_dict()

        assert result_dict["success"] is False
        assert result_dict["message"] == "Something went wrong"
        assert result_dict["error"]["code"] == "CUSTOM_ERROR"
        assert result_dict["error"]["message"] == "Something went wrong"
        assert result_dict["error"]["details"] == "Additional details"

    def test_to_dict_validation_error(self):
        """Test converting validation error to dictionary"""
        field_errors = {"email": "Invalid email"}
        result = ServiceResult.validation_error("Validation failed", field_errors)
        result_dict = result.to_dict()

        assert result_dict["success"] is False
        assert result_dict["error"]["field_errors"] == field_errors

    def test_to_tuple_success(self):
        """Test converting success result to tuple"""
        result = ServiceResult.success_result({"id": 1})
        success, data = result.to_tuple()

        assert success is True
        assert data == {"id": 1}

    def test_to_tuple_error(self):
        """Test converting error result to tuple"""
        result = ServiceResult.error_result("Failed", "ERROR_CODE", "Details")
        success, data = result.to_tuple()

        assert success is False
        assert data["error"] == "Failed"
        assert data["code"] == "ERROR_CODE"
        assert data["details"] == "Details"

    def test_format_success_data_dict(self):
        """Test _format_success_data with dict input"""
        data = {"key": "value"}
        result = ServiceResult._format_success_data(data)
        assert result == data

    def test_format_success_data_non_dict(self):
        """Test _format_success_data with non-dict input"""
        data = "test_string"
        result = ServiceResult._format_success_data(data)
        assert result == {"result": "test_string"}

    def test_format_success_data_none(self):
        """Test _format_success_data with None input"""
        result = ServiceResult._format_success_data(None)
        assert result == {}


class TestServiceExceptions:
    """Test ServiceException and ValidationException"""

    def test_service_exception_creation(self):
        """Test creating ServiceException"""
        exc = ServiceException("Test error", "TEST_CODE", "Test details")

        assert str(exc) == "Test error"
        assert exc.message == "Test error"
        assert exc.error_code == "TEST_CODE"
        assert exc.details == "Test details"

    def test_service_exception_defaults(self):
        """Test ServiceException with default values"""
        exc = ServiceException("Test error")

        assert exc.message == "Test error"
        assert exc.error_code == "SERVICE_ERROR"
        assert exc.details is None

    def test_validation_exception_creation(self):
        """Test creating ValidationException"""
        field_errors = {"email": "Invalid"}
        exc = ValidationException("Validation failed", field_errors)

        assert str(exc) == "Validation failed"
        assert exc.message == "Validation failed"
        assert exc.error_code == "VALIDATION_ERROR"
        assert exc.field_errors == field_errors

    def test_validation_exception_defaults(self):
        """Test ValidationException with default field_errors"""
        exc = ValidationException("Validation failed")

        assert exc.field_errors == {}


class TestConvertFunctionResult:
    """Test _convert_function_result_to_service_result function"""

    def test_service_result_passthrough(self):
        """Test that ServiceResult is passed through unchanged"""
        original = ServiceResult.success_result({"test": "data"})
        result = _convert_function_result_to_service_result(original)

        assert result is original

    def test_tuple_success_conversion(self):
        """Test converting (True, data) tuple to ServiceResult"""
        result = _convert_function_result_to_service_result((True, {"id": 1}))

        assert isinstance(result, ServiceResult)
        assert result.success is True
        assert result.data == {"id": 1}

    def test_tuple_error_conversion(self):
        """Test converting (False, error_dict) tuple to ServiceResult"""
        error_data = {
            "error": "Something failed",
            "code": "FAILURE",
            "details": "Extra info",
        }
        result = _convert_function_result_to_service_result((False, error_data))

        assert isinstance(result, ServiceResult)
        assert result.success is False
        assert result.message == "Something failed"
        assert result.error_code == "FAILURE"
        assert result.error_details == "Extra info"

    def test_tuple_error_conversion_defaults(self):
        """Test converting error tuple with missing fields"""
        result = _convert_function_result_to_service_result(
            (False, {"error": "Failed"})
        )

        assert result.success is False
        assert result.message == "Failed"
        assert result.error_code == "OPERATION_FAILED"
        assert result.error_details is None

    def test_tuple_error_conversion_missing_error(self):
        """Test converting error tuple with no error field"""
        result = _convert_function_result_to_service_result((False, {"code": "ERROR"}))

        assert result.success is False
        assert result.message == "Operation failed"
        assert result.error_code == "ERROR"

    def test_raw_data_conversion(self):
        """Test converting raw data to success result"""
        result = _convert_function_result_to_service_result({"user": "data"})

        assert isinstance(result, ServiceResult)
        assert result.success is True
        assert result.data == {"user": "data"}


class TestHandleServiceExceptionsDecorator:
    """Test handle_service_exceptions decorator"""

    @pytest.mark.asyncio
    async def test_async_function_success(self):
        """Test decorator with successful async function"""

        @handle_service_exceptions
        async def test_func(data):
            return {"processed": data}

        result = await test_func("test_data")

        assert isinstance(result, ServiceResult)
        assert result.success is True
        assert result.data == {"processed": "test_data"}

    def test_sync_function_success(self):
        """Test decorator with successful sync function"""

        @handle_service_exceptions
        def test_func(data):
            return {"processed": data}

        result = test_func("test_data")

        assert isinstance(result, ServiceResult)
        assert result.success is True
        assert result.data == {"processed": "test_data"}

    @pytest.mark.asyncio
    async def test_async_service_exception(self):
        """Test decorator catching ServiceException in async function"""

        @handle_service_exceptions
        async def test_func():
            raise ServiceException("Service error", "SERVICE_CODE", "Details")

        result = await test_func()

        assert isinstance(result, ServiceResult)
        assert result.success is False
        assert result.message == "Service error"
        assert result.error_code == "SERVICE_CODE"
        assert result.error_details == "Details"

    def test_sync_validation_exception(self):
        """Test decorator catching ValidationException in sync function"""

        @handle_service_exceptions
        def test_func():
            raise ValidationException("Validation error", {"field": "error"})

        result = test_func()

        assert isinstance(result, ServiceResult)
        assert result.success is False
        assert result.message == "Validation error"
        assert result.error_code == "VALIDATION_ERROR"
        assert result.data["field_errors"] == {"field": "error"}

    @pytest.mark.asyncio
    async def test_async_generic_exception(self):
        """Test decorator catching generic Exception in async function"""

        @handle_service_exceptions
        async def test_func():
            raise ValueError("Something went wrong")

        result = await test_func()

        assert isinstance(result, ServiceResult)
        assert result.success is False
        assert result.message == "An unexpected error occurred"
        assert result.error_code == "INTERNAL_ERROR"
        assert "Something went wrong" in result.error_details

    def test_sync_generic_exception(self):
        """Test decorator catching generic Exception in sync function"""

        @handle_service_exceptions
        def test_func():
            raise RuntimeError("Runtime error")

        result = test_func()

        assert isinstance(result, ServiceResult)
        assert result.success is False
        assert result.message == "An unexpected error occurred"
        assert result.error_code == "INTERNAL_ERROR"

    @pytest.mark.asyncio
    async def test_async_function_returns_service_result(self):
        """Test decorator with function that already returns ServiceResult"""

        @handle_service_exceptions
        async def test_func():
            return ServiceResult.success_result({"already": "wrapped"})

        result = await test_func()

        assert isinstance(result, ServiceResult)
        assert result.success is True
        assert result.data == {"already": "wrapped"}

    def test_function_returns_tuple(self):
        """Test decorator with function returning legacy tuple format"""

        @handle_service_exceptions
        def test_func():
            return True, {"legacy": "format"}

        result = test_func()

        assert isinstance(result, ServiceResult)
        assert result.success is True
        assert result.data == {"legacy": "format"}


class TestBaseService:
    """Test BaseService class functionality"""

    def test_init_with_explicit_model(self):
        """Test BaseService initialization with explicit model class"""
        mock_model = MagicMock()
        mock_db = MagicMock()

        service = BaseService(mock_db, mock_model)

        assert service.db is mock_db
        assert service.model_class is mock_model

    def test_get_model_class_explicit(self):
        """Test _get_model_class with explicit model_class"""
        mock_model = MagicMock()
        mock_db = MagicMock()

        service = BaseService(mock_db, mock_model)
        result = service._get_model_class()

        assert result is mock_model

    def test_get_model_class_no_model_raises_error(self):
        """Test _get_model_class raises error when no model specified"""
        mock_db = MagicMock()

        service = BaseService(mock_db)
        service.__class__.__orig_bases__ = []  # No generic bases

        with pytest.raises(ValueError, match="Model class not specified"):
            service._get_model_class()

    @pytest.mark.asyncio
    async def test_create_success(self):
        """Test BaseService create method success"""
        mock_model = MagicMock()
        mock_instance = MagicMock()
        mock_instance.to_dict.return_value = {"id": 1, "name": "test"}
        mock_model.objects.create = AsyncMock(return_value=mock_instance)
        mock_model.__name__ = "TestModel"

        mock_db = MagicMock()
        service = BaseService(mock_db, mock_model)

        result = await service.create({"name": "test"})

        assert isinstance(result, ServiceResult)
        assert result.success is True
        assert result.data == {"id": 1, "name": "test"}
        mock_model.objects.create.assert_called_once_with(mock_db, name="test")

    @pytest.mark.asyncio
    async def test_create_with_custom_message(self):
        """Test BaseService create with custom success message"""
        mock_model = MagicMock()
        mock_instance = MagicMock()
        mock_instance.to_dict.return_value = {"id": 1}
        mock_model.objects.create = AsyncMock(return_value=mock_instance)
        mock_model.__name__ = "TestModel"

        service = BaseService(MagicMock(), mock_model)

        result = await service.create({"name": "test"}, "Custom message")

        assert result.success is True
        assert result.message == "Custom message"

    @pytest.mark.asyncio
    async def test_get_by_id_success(self):
        """Test BaseService get_by_id success"""
        mock_model = MagicMock()
        mock_instance = MagicMock()
        mock_instance.to_dict.return_value = {"id": 1, "name": "test"}
        mock_model.objects.get = AsyncMock(return_value=mock_instance)

        service = BaseService(MagicMock(), mock_model)

        result = await service.get_by_id(1)

        assert isinstance(result, ServiceResult)
        assert result.success is True
        assert result.data == {"id": 1, "name": "test"}

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self):
        """Test BaseService get_by_id when record not found"""
        mock_model = MagicMock()
        mock_model.objects.get = AsyncMock(return_value=None)
        mock_model.__name__ = "TestModel"

        service = BaseService(MagicMock(), mock_model)

        result = await service.get_by_id(1)

        assert isinstance(result, ServiceResult)
        assert result.success is False
        assert result.result_type == ServiceResultType.NOT_FOUND
        assert "TestModel not found" in result.message

    @pytest.mark.asyncio
    async def test_update_success(self):
        """Test BaseService update success"""
        mock_model = MagicMock()
        mock_instance = MagicMock()
        mock_instance.to_dict.return_value = {"id": 1, "name": "updated"}

        # Setup proper async mocks for update flow
        mock_filter = MagicMock()
        mock_filter.update = AsyncMock(return_value=None)
        mock_objects = MagicMock()
        mock_objects.get = AsyncMock(
            side_effect=[mock_instance, mock_instance]
        )  # First get, then updated get
        mock_objects.filter = MagicMock(return_value=mock_filter)
        mock_model.objects = mock_objects
        mock_model.__name__ = "TestModel"

        service = BaseService(MagicMock(), mock_model)

        result = await service.update(1, {"name": "updated"})

        assert isinstance(result, ServiceResult)
        assert result.success is True
        assert result.data == {"id": 1, "name": "updated"}

    @pytest.mark.asyncio
    async def test_update_not_found(self):
        """Test BaseService update when record not found"""
        mock_model = MagicMock()
        mock_model.objects.get = AsyncMock(return_value=None)
        mock_model.__name__ = "TestModel"

        service = BaseService(MagicMock(), mock_model)

        result = await service.update(1, {"name": "updated"})

        assert isinstance(result, ServiceResult)
        assert result.success is False
        assert result.result_type == ServiceResultType.NOT_FOUND

    @pytest.mark.asyncio
    async def test_delete_success(self):
        """Test BaseService delete success"""
        mock_model = MagicMock()
        mock_instance = MagicMock()
        mock_model.__name__ = "TestModel"

        # Setup proper async mocks for delete flow (need to support both update and delete paths)
        mock_filter = MagicMock()
        mock_filter.update = AsyncMock(return_value=None)  # For soft delete
        mock_filter.delete = AsyncMock(return_value=True)  # For hard delete
        mock_objects = MagicMock()
        mock_objects.get = AsyncMock(return_value=mock_instance)
        mock_objects.filter = MagicMock(return_value=mock_filter)
        mock_model.objects = mock_objects

        # Mock instance to not have status attribute (forces hard delete)
        mock_instance.configure_mock(**{"status": None})
        del mock_instance.status

        service = BaseService(MagicMock(), mock_model)

        result = await service.delete(1)

        assert isinstance(result, ServiceResult)
        assert result.success is True
        assert result.data == {"id": 1}
        assert "TestModel deleted successfully" in result.message

    @pytest.mark.asyncio
    async def test_delete_not_found(self):
        """Test BaseService delete when record not found"""
        mock_model = MagicMock()
        mock_model.objects.get = AsyncMock(return_value=None)
        mock_model.__name__ = "TestModel"

        service = BaseService(MagicMock(), mock_model)

        result = await service.delete(1)

        assert isinstance(result, ServiceResult)
        assert result.success is False
        assert result.result_type == ServiceResultType.NOT_FOUND

    @pytest.mark.asyncio
    async def test_list_items_success(self):
        """Test BaseService list_items success"""
        mock_model = MagicMock()
        mock_instances = [MagicMock(), MagicMock()]
        for i, instance in enumerate(mock_instances):
            instance.to_dict.return_value = {"id": i + 1, "name": f"item{i + 1}"}

        # Setup proper async mock chain with order_by
        mock_all = AsyncMock(return_value=mock_instances)
        mock_offset = MagicMock()
        mock_offset.all = mock_all
        mock_limit = MagicMock()
        mock_limit.offset = MagicMock(return_value=mock_offset)
        mock_order_by = MagicMock()
        mock_order_by.limit = MagicMock(return_value=mock_limit)
        mock_filter = MagicMock()
        mock_filter.order_by = MagicMock(return_value=mock_order_by)
        mock_objects = MagicMock()
        mock_objects.filter = MagicMock(return_value=mock_filter)
        mock_model.objects = mock_objects

        service = BaseService(MagicMock(), mock_model)

        result = await service.list_items({"status": "active"}, limit=10, offset=0)

        assert isinstance(result, ServiceResult)
        assert result.success is True
        assert len(result.data["items"]) == 2
        assert result.data["items"][0] == {"id": 1, "name": "item1"}
        assert result.data["pagination"]["count"] == 2

    @pytest.mark.asyncio
    async def test_list_items_with_defaults(self):
        """Test BaseService list_items with default parameters"""
        mock_model = MagicMock()

        # Setup proper async mock chain with empty results and order_by
        mock_all = AsyncMock(return_value=[])
        mock_offset = MagicMock()
        mock_offset.all = mock_all
        mock_limit = MagicMock()
        mock_limit.offset = MagicMock(return_value=mock_offset)
        mock_order_by = MagicMock()
        mock_order_by.limit = MagicMock(return_value=mock_limit)
        mock_filter = MagicMock()
        mock_filter.order_by = MagicMock(return_value=mock_order_by)
        mock_objects = MagicMock()
        mock_objects.filter = MagicMock(return_value=mock_filter)
        mock_model.objects = mock_objects

        service = BaseService(MagicMock(), mock_model)

        result = await service.list_items()

        assert isinstance(result, ServiceResult)
        assert result.success is True
        assert result.data["items"] == []
        assert result.data["pagination"]["count"] == 0

        # Verify default parameters were used (filter called with the db mock)
        mock_model.objects.filter.assert_called_once()
        mock_filter.order_by.assert_called_with("-created_at")
        mock_order_by.limit.assert_called_with(20)
        mock_limit.offset.assert_called_with(0)
