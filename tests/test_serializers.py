"""
Tests for kinglet.serializers module
Tests ModelSerializer, SerializerConfig, SerializationContext, and related functionality
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from unittest.mock import MagicMock

from kinglet.serializers import (
    FieldTransforms,
    ModelSerializer,
    SerializationContext,
    SerializerConfig,
    SerializerMixin,
    serialize_model,
    serialize_models,
)


class Color(Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"


@dataclass
class SampleModel:
    """Sample model for serialization testing"""

    id: int
    name: str
    email: str
    created_at: datetime
    is_active: bool
    color: Color
    tags: list
    _private_field: str = "private"

    def to_dict(self):
        """Custom to_dict method for testing"""
        return {
            "custom_id": self.id,
            "custom_name": self.name,
            "custom_serialization": True,
        }


class SimpleModel:
    """Simple model without to_dict method"""

    def __init__(self, name, value):
        self.name = name
        self.value = value
        self._internal = "hidden"


class DjangoStyleModel:
    """Mock Django-style model for testing"""

    def __init__(self, name, description):
        self.name = name
        self.description = description

    class _meta:
        fields = {"name": None, "description": None}


class TestSerializationContext:
    """Test SerializationContext class"""

    def test_context_creation_empty(self):
        """Test creating empty serialization context"""
        context = SerializationContext()

        assert context.request is None
        assert context.user is None
        assert context.extra == {}

    def test_context_creation_with_data(self):
        """Test creating serialization context with data"""
        request = MagicMock()
        user = {"id": 1, "name": "John"}
        extra_data = {"custom_key": "custom_value"}

        context = SerializationContext(request=request, user=user, **extra_data)

        assert context.request is request
        assert context.user == user
        assert context.extra == extra_data


class TestSerializerConfig:
    """Test SerializerConfig class"""

    def test_config_defaults(self):
        """Test SerializerConfig with default values"""
        config = SerializerConfig()

        assert config.include is None
        assert config.exclude == []
        assert config.transforms == {}
        assert config.related == {}
        assert config.field_mappings == {}
        assert config.computed_fields == {}
        assert config.read_only_fields == set()
        assert config.write_only_fields == set()

    def test_config_with_values(self):
        """Test SerializerConfig with custom values"""
        transforms = {"price": lambda x: x / 100}
        config = SerializerConfig(
            include=["name", "email"],
            exclude=["password"],
            transforms=transforms,
            field_mappings={"email_address": "email"},
            read_only_fields={"created_at"},
            write_only_fields={"password"},
        )

        assert config.include == ["name", "email"]
        assert config.exclude == ["password"]
        assert config.transforms == transforms
        assert config.field_mappings == {"email_address": "email"}
        assert config.read_only_fields == {"created_at"}
        assert config.write_only_fields == {"password"}


class SampleModelSerializer:
    """Test ModelSerializer class"""

    def test_serializer_creation_default_config(self):
        """Test creating serializer with default config"""
        serializer = ModelSerializer()

        assert isinstance(serializer.config, SerializerConfig)

    def test_serializer_creation_custom_config(self):
        """Test creating serializer with custom config"""
        config = SerializerConfig(include=["name", "email"])
        serializer = ModelSerializer(config)

        assert serializer.config is config

    def test_serialize_none_instance(self):
        """Test serializing None returns None"""
        serializer = ModelSerializer()
        result = serializer.serialize(None)

        assert result is None

    def test_serialize_simple_object(self):
        """Test serializing simple object"""
        obj = SimpleModel("test", 42)
        serializer = ModelSerializer()

        result = serializer.serialize(obj)

        assert result["name"] == "test"
        assert result["value"] == 42
        assert "_internal" not in result  # Private fields should be excluded

    def test_serialize_with_include_fields(self):
        """Test serializing with include fields specified"""
        obj = SimpleModel("test", 42)
        config = SerializerConfig(include=["name"])
        serializer = ModelSerializer(config)

        result = serializer.serialize(obj)

        assert "name" in result
        assert "value" not in result

    def test_serialize_with_exclude_fields(self):
        """Test serializing with exclude fields specified"""
        obj = SimpleModel("test", 42)
        config = SerializerConfig(exclude=["value"])
        serializer = ModelSerializer(config)

        result = serializer.serialize(obj)

        assert "name" in result
        assert "value" not in result

    def test_serialize_with_write_only_fields(self):
        """Test serializing excludes write-only fields"""
        obj = SimpleModel("test", 42)
        config = SerializerConfig(write_only_fields={"value"})
        serializer = ModelSerializer(config)

        result = serializer.serialize(obj)

        assert "name" in result
        assert "value" not in result

    def test_serialize_with_field_transformations(self):
        """Test serializing with field transformations"""
        obj = SimpleModel("test", 100)
        config = SerializerConfig(transforms={"value": lambda x: x * 2})
        serializer = ModelSerializer(config)

        result = serializer.serialize(obj)

        assert result["value"] == 200

    def test_serialize_with_context_transform(self):
        """Test serializing with transformation that uses context"""

        def transform_with_context(value, context=None):
            multiplier = context.extra.get("multiplier", 1) if context else 1
            return value * multiplier

        obj = SimpleModel("test", 10)
        config = SerializerConfig(transforms={"value": transform_with_context})
        serializer = ModelSerializer(config)
        context = SerializationContext(multiplier=5)

        result = serializer.serialize(obj, context)

        assert result["value"] == 50

    def test_serialize_with_field_mappings(self):
        """Test serializing with field name mappings"""
        obj = SimpleModel("test", 42)
        config = SerializerConfig(field_mappings={"name": "display_name"})
        serializer = ModelSerializer(config)

        result = serializer.serialize(obj)

        assert "display_name" in result
        assert result["display_name"] == "test"
        assert "name" not in result

    def test_serialize_with_computed_fields(self):
        """Test serializing with computed fields"""

        def compute_full_info(instance, context=None):
            return f"{instance.name}_{instance.value}"

        obj = SimpleModel("test", 42)
        config = SerializerConfig(computed_fields={"full_info": compute_full_info})
        serializer = ModelSerializer(config)

        result = serializer.serialize(obj)

        assert result["full_info"] == "test_42"

    def test_serialize_with_computed_fields_context(self):
        """Test serializing with computed fields that use context"""

        def compute_with_context(instance, context=None):
            prefix = context.extra.get("prefix", "") if context else ""
            return f"{prefix}{instance.name}"

        obj = SimpleModel("test", 42)
        config = SerializerConfig(
            computed_fields={"prefixed_name": compute_with_context}
        )
        serializer = ModelSerializer(config)
        context = SerializationContext(prefix="Mr. ")

        result = serializer.serialize(obj, context)

        assert result["prefixed_name"] == "Mr. test"

    def test_serialize_with_related_fields(self):
        """Test serializing with related field configuration"""
        related_obj = SimpleModel("related", 99)
        obj = SimpleModel("parent", 42)
        obj.child = related_obj

        related_config = SerializerConfig(include=["name"])
        config = SerializerConfig(related={"child": related_config})
        serializer = ModelSerializer(config)

        result = serializer.serialize(obj)

        assert "child" in result
        assert result["child"]["name"] == "related"
        assert "value" not in result["child"]  # Excluded by related config

    def test_serialize_with_related_list(self):
        """Test serializing with related field that is a list"""
        related_objs = [SimpleModel("item1", 1), SimpleModel("item2", 2)]
        obj = SimpleModel("parent", 42)
        obj.children = related_objs

        related_config = SerializerConfig(include=["name"])
        config = SerializerConfig(related={"children": related_config})
        serializer = ModelSerializer(config)

        result = serializer.serialize(obj)

        assert "children" in result
        assert len(result["children"]) == 2
        assert result["children"][0]["name"] == "item1"
        assert result["children"][1]["name"] == "item2"

    def test_serialize_many_empty_list(self):
        """Test serializing empty list"""
        serializer = ModelSerializer()
        result = serializer.serialize_many([])

        assert result == []

    def test_serialize_many_objects(self):
        """Test serializing multiple objects"""
        objects = [SimpleModel("test1", 1), SimpleModel("test2", 2)]
        serializer = ModelSerializer()

        result = serializer.serialize_many(objects)

        assert len(result) == 2
        assert result[0]["name"] == "test1"
        assert result[1]["name"] == "test2"

    def test_serialize_django_style_model(self):
        """Test serializing Django-style model"""
        obj = DjangoStyleModel("test", "description")
        serializer = ModelSerializer()

        result = serializer.serialize(obj)

        assert result["name"] == "test"
        assert result["description"] == "description"

    def test_serialize_value_datetime(self):
        """Test _serialize_value with datetime"""
        serializer = ModelSerializer()
        dt = datetime(2023, 12, 25, 10, 30, 0)

        result = serializer._serialize_value(dt)

        assert result == dt.isoformat()

    def test_serialize_value_enum(self):
        """Test _serialize_value with enum"""
        serializer = ModelSerializer()
        color = Color.RED

        result = serializer._serialize_value(color)

        assert result == "red"

    def test_serialize_value_object_with_to_dict(self):
        """Test _serialize_value with object that has to_dict"""
        obj = SampleModel(
            1, "test", "test@example.com", datetime.now(), True, Color.RED, []
        )
        serializer = ModelSerializer()

        result = serializer._serialize_value(obj)

        assert result["custom_id"] == 1
        assert result["custom_name"] == "test"
        assert result["custom_serialization"] is True

    def test_serialize_value_simple_object(self):
        """Test _serialize_value with simple object"""
        obj = SimpleModel("test", 42)
        serializer = ModelSerializer()

        result = serializer._serialize_value(obj)

        assert result["name"] == "test"
        assert result["value"] == 42
        assert "_internal" not in result

    def test_serialize_value_none(self):
        """Test _serialize_value with None"""
        serializer = ModelSerializer()
        result = serializer._serialize_value(None)

        assert result is None

    def test_deserialize_basic(self):
        """Test basic deserialization"""
        serializer = ModelSerializer()
        data = {"name": "test", "value": 42}

        result = serializer.deserialize(data)

        assert result == {"name": "test", "value": 42}

    def test_deserialize_with_read_only_fields(self):
        """Test deserialization excludes read-only fields"""
        config = SerializerConfig(read_only_fields={"created_at"})
        serializer = ModelSerializer(config)
        data = {"name": "test", "created_at": "2023-12-25"}

        result = serializer.deserialize(data)

        assert "name" in result
        assert "created_at" not in result

    def test_deserialize_with_reverse_field_mapping(self):
        """Test deserialization with reverse field mapping"""
        config = SerializerConfig(field_mappings={"name": "display_name"})
        serializer = ModelSerializer(config)
        data = {"display_name": "test", "value": 42}

        result = serializer.deserialize(data)

        assert result["name"] == "test"  # Should reverse the mapping
        assert result["value"] == 42

    def test_deserialize_with_reverse_transform(self):
        """Test deserialization with reverse transformation"""

        def transform_func(value):
            return value * 2

        def reverse_transform(value):
            return value / 2

        transform_func.reverse = reverse_transform

        config = SerializerConfig(transforms={"value": transform_func})
        serializer = ModelSerializer(config)
        data = {"name": "test", "value": 100}

        result = serializer.deserialize(data)

        assert result["value"] == 50

    def test_get_field_value_safely_success(self):
        """Test _get_field_value_safely with valid field"""
        obj = SimpleModel("test", 42)
        serializer = ModelSerializer()

        result = serializer._get_field_value_safely(obj, "name")

        assert result == "test"

    def test_get_field_value_safely_missing_field(self):
        """Test _get_field_value_safely with missing field"""
        obj = SimpleModel("test", 42)
        serializer = ModelSerializer()

        result = serializer._get_field_value_safely(obj, "missing_field")

        assert result is None

    def test_get_field_value_safely_attribute_error(self):
        """Test _get_field_value_safely handles AttributeError"""

        class TestObj:
            pass

        obj = TestObj()
        serializer = ModelSerializer()
        result = serializer._get_field_value_safely(obj, "nonexistent_field")

        assert result is None

    def test_apply_field_transformation_no_transform(self):
        """Test _apply_field_transformation with no transformation configured"""
        serializer = ModelSerializer()
        result = serializer._apply_field_transformation("value", "field", None)

        assert result == "value"

    def test_apply_field_transformation_not_callable(self):
        """Test _apply_field_transformation with non-callable transform"""
        config = SerializerConfig(transforms={"field": "not_callable"})
        serializer = ModelSerializer(config)

        result = serializer._apply_field_transformation("value", "field", None)

        assert result == "value"

    def test_serialize_related_field_no_config(self):
        """Test _serialize_related_field with no related configuration"""
        serializer = ModelSerializer()
        result = serializer._serialize_related_field("value", "field", None)

        assert result == "value"

    def test_serialize_related_field_none_value(self):
        """Test _serialize_related_field with None value"""
        config = SerializerConfig(related={"field": SerializerConfig()})
        serializer = ModelSerializer(config)

        result = serializer._serialize_related_field(None, "field", None)

        assert result is None

    def test_compute_field_value_safely_success(self):
        """Test _compute_field_value_safely with valid function"""
        obj = SimpleModel("test", 42)

        def compute_func(instance):
            return f"{instance.name}_computed"

        serializer = ModelSerializer()
        result = serializer._compute_field_value_safely(compute_func, obj, None)

        assert result == "test_computed"

    def test_compute_field_value_safely_not_callable(self):
        """Test _compute_field_value_safely with non-callable"""
        serializer = ModelSerializer()
        result = serializer._compute_field_value_safely("not_callable", None, None)

        assert result is None

    def test_compute_field_value_safely_exception(self):
        """Test _compute_field_value_safely handles exceptions"""

        def failing_func(instance):
            raise ValueError("Computation failed")

        serializer = ModelSerializer()
        result = serializer._compute_field_value_safely(failing_func, None, None)

        assert result is None


class TestFieldTransforms:
    """Test FieldTransforms utility class"""

    def test_cents_to_dollars(self):
        """Test cents to dollars conversion"""
        result = FieldTransforms.cents_to_dollars(1299)
        assert result == 12.99

    def test_cents_to_dollars_none(self):
        """Test cents to dollars with None"""
        result = FieldTransforms.cents_to_dollars(None)
        assert result is None

    def test_dollars_to_cents(self):
        """Test dollars to cents conversion"""
        result = FieldTransforms.dollars_to_cents(12.99)
        assert result == 1299

    def test_dollars_to_cents_none(self):
        """Test dollars to cents with None"""
        result = FieldTransforms.dollars_to_cents(None)
        assert result is None

    def test_cents_to_dollars_reverse(self):
        """Test that cents_to_dollars has reverse function"""
        assert hasattr(FieldTransforms.cents_to_dollars, "reverse")
        assert (
            FieldTransforms.cents_to_dollars.reverse == FieldTransforms.dollars_to_cents
        )

    def test_format_datetime(self):
        """Test datetime formatting"""
        dt = datetime(2023, 12, 25, 10, 30, 0)
        result = FieldTransforms.format_datetime(dt)

        assert result == "2023-12-25 10:30:00"

    def test_format_datetime_custom_format(self):
        """Test datetime formatting with custom format"""
        dt = datetime(2023, 12, 25)
        result = FieldTransforms.format_datetime(dt, "%Y-%m-%d")

        assert result == "2023-12-25"

    def test_format_datetime_none(self):
        """Test datetime formatting with None"""
        result = FieldTransforms.format_datetime(None)
        assert result is None

    def test_format_datetime_string_input(self):
        """Test datetime formatting with string input"""
        result = FieldTransforms.format_datetime("2023-12-25")
        assert result == "2023-12-25"

    def test_boolean_to_int(self):
        """Test boolean to integer conversion"""
        assert FieldTransforms.boolean_to_int(True) == 1
        assert FieldTransforms.boolean_to_int(False) == 0

    def test_boolean_to_int_none(self):
        """Test boolean to integer with None"""
        result = FieldTransforms.boolean_to_int(None)
        assert result is None

    def test_int_to_boolean(self):
        """Test integer to boolean conversion"""
        assert FieldTransforms.int_to_boolean(1) is True
        assert FieldTransforms.int_to_boolean(0) is False
        assert FieldTransforms.int_to_boolean(5) is True

    def test_int_to_boolean_none(self):
        """Test integer to boolean with None"""
        result = FieldTransforms.int_to_boolean(None)
        assert result is None

    def test_boolean_to_int_reverse(self):
        """Test that boolean_to_int has reverse function"""
        assert hasattr(FieldTransforms.boolean_to_int, "reverse")
        assert FieldTransforms.boolean_to_int.reverse == FieldTransforms.int_to_boolean

    def test_json_list_to_string(self):
        """Test JSON list to string conversion"""
        result = FieldTransforms.json_list_to_string([1, 2, 3])
        assert result == "1, 2, 3"

    def test_json_list_to_string_empty(self):
        """Test JSON list to string with empty list"""
        result = FieldTransforms.json_list_to_string([])
        assert result == ""

    def test_json_list_to_string_none(self):
        """Test JSON list to string with None"""
        result = FieldTransforms.json_list_to_string(None)
        assert result == ""

    def test_string_to_json_list(self):
        """Test string to JSON list conversion"""
        result = FieldTransforms.string_to_json_list("item1, item2, item3")
        assert result == ["item1", "item2", "item3"]

    def test_string_to_json_list_empty(self):
        """Test string to JSON list with empty string"""
        result = FieldTransforms.string_to_json_list("")
        assert result == []

    def test_string_to_json_list_none(self):
        """Test string to JSON list with None"""
        result = FieldTransforms.string_to_json_list(None)
        assert result == []

    def test_json_list_to_string_reverse(self):
        """Test that json_list_to_string has reverse function"""
        assert hasattr(FieldTransforms.json_list_to_string, "reverse")
        assert (
            FieldTransforms.json_list_to_string.reverse
            == FieldTransforms.string_to_json_list
        )


class TestSerializerMixin:
    """Test SerializerMixin class"""

    def test_mixin_to_dict(self):
        """Test mixin to_dict method"""

        class SampleModelWithMixin(SerializerMixin):
            def __init__(self, name, value):
                self.name = name
                self.value = value

        obj = SampleModelWithMixin("test", 42)
        result = obj.to_dict()

        assert result["name"] == "test"
        assert result["value"] == 42

    def test_mixin_to_api_dict(self):
        """Test mixin to_api_dict method (alias)"""

        class SampleModelWithMixin(SerializerMixin):
            def __init__(self, name):
                self.name = name

        obj = SampleModelWithMixin("test")
        result = obj.to_api_dict()

        assert result["name"] == "test"

    def test_mixin_with_custom_config(self):
        """Test mixin with custom serializer config"""

        class SampleModelWithMixin(SerializerMixin):
            _serializer_config = SerializerConfig(exclude=["private_field"])

            def __init__(self, name, private_field):
                self.name = name
                self.private_field = private_field

        obj = SampleModelWithMixin("test", "secret")
        result = obj.to_dict()

        assert result["name"] == "test"
        assert "private_field" not in result

    def test_mixin_from_dict(self):
        """Test mixin from_dict class method"""

        class SampleModelWithMixin(SerializerMixin):
            def __init__(self, name=None, value=None):
                self.name = name
                self.value = value

        data = {"name": "test", "value": 42}
        obj = SampleModelWithMixin.from_dict(data)

        assert obj.name == "test"
        assert obj.value == 42

    def test_mixin_serialize_many(self):
        """Test mixin serialize_many class method"""

        class SampleModelWithMixin(SerializerMixin):
            def __init__(self, name):
                self.name = name

        objects = [SampleModelWithMixin("test1"), SampleModelWithMixin("test2")]
        result = SampleModelWithMixin.serialize_many(objects)

        assert len(result) == 2
        assert result[0]["name"] == "test1"
        assert result[1]["name"] == "test2"

    def test_mixin_get_serializer_config_default(self):
        """Test mixin _get_serializer_config with default config"""

        class SampleModelWithMixin(SerializerMixin):
            pass

        config = SampleModelWithMixin._get_serializer_config()

        assert isinstance(config, SerializerConfig)

    def test_mixin_get_serializer_config_custom(self):
        """Test mixin _get_serializer_config with custom config"""
        custom_config = SerializerConfig(include=["name"])

        class SampleModelWithMixin(SerializerMixin):
            _serializer_config = custom_config

        config = SampleModelWithMixin._get_serializer_config()

        assert config is custom_config


class TestUtilityFunctions:
    """Test utility functions"""

    def test_serialize_model_function(self):
        """Test serialize_model utility function"""
        obj = SimpleModel("test", 42)
        result = serialize_model(obj)

        assert result["name"] == "test"
        assert result["value"] == 42

    def test_serialize_model_with_config(self):
        """Test serialize_model with custom config"""
        obj = SimpleModel("test", 42)
        config = SerializerConfig(include=["name"])

        result = serialize_model(obj, config)

        assert "name" in result
        assert "value" not in result

    def test_serialize_model_with_context(self):
        """Test serialize_model with context"""
        obj = SimpleModel("test", 10)
        config = SerializerConfig(
            transforms={
                "value": lambda v, context=None: v * context.extra.get("multiplier", 1)
            }
        )
        context = SerializationContext(multiplier=3)

        result = serialize_model(obj, config, context)

        assert result["value"] == 30

    def test_serialize_models_function(self):
        """Test serialize_models utility function"""
        objects = [SimpleModel("test1", 1), SimpleModel("test2", 2)]
        result = serialize_models(objects)

        assert len(result) == 2
        assert result[0]["name"] == "test1"
        assert result[1]["name"] == "test2"

    def test_serialize_models_with_config(self):
        """Test serialize_models with custom config"""
        objects = [SimpleModel("test1", 1), SimpleModel("test2", 2)]
        config = SerializerConfig(include=["name"])

        result = serialize_models(objects, config)

        assert len(result) == 2
        assert "name" in result[0]
        assert "value" not in result[0]
