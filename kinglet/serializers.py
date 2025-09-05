"""
Kinglet Model Serialization System
Eliminates boilerplate for model-to-API response formatting
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SerializationContext:
    """Context for serialization operations"""

    def __init__(self, request=None, user=None, **kwargs):
        self.request = request
        self.user = user
        self.extra = kwargs


@dataclass
class SerializerConfig:
    """Configuration for model serialization"""

    # Fields to include (if None, includes all model fields)
    include: list[str] | None = None

    # Fields to exclude
    exclude: list[str] | None = field(default_factory=list)

    # Field transformations: field_name -> function
    transforms: dict[str, Callable] | None = field(default_factory=dict)

    # Related field serialization: field_name -> nested serializer config
    related: dict[str, SerializerConfig] | None = field(default_factory=dict)

    # Custom field mappings: model_field -> api_field
    field_mappings: dict[str, str] | None = field(default_factory=dict)

    # Additional computed fields: field_name -> function
    computed_fields: dict[str, Callable] | None = field(default_factory=dict)

    # Read-only fields (excluded from deserialization)
    read_only_fields: set[str] | None = field(default_factory=set)

    # Write-only fields (excluded from serialization)
    write_only_fields: set[str] | None = field(default_factory=set)


class ModelSerializer:
    """
    Base model serializer with automatic field detection
    Eliminates manual to_dict() method boilerplate
    """

    def __init__(self, config: SerializerConfig | None = None):
        self.config = config or SerializerConfig()

    def serialize(
        self, instance, context: SerializationContext | None = None
    ) -> dict[str, Any]:
        """
        Serialize model instance to dictionary

        Args:
            instance: Model instance to serialize
            context: Serialization context with request info, user, etc.

        Returns:
            Serialized dictionary ready for API response
        """
        if instance is None:
            return None

        context = context or SerializationContext()
        result = {}

        # Get all model fields and determine which to include
        model_fields = self._get_model_fields(instance)
        fields_to_include = self._get_fields_to_include(model_fields)

        # Serialize model fields
        self._serialize_model_fields(instance, fields_to_include, result, context)

        # Add computed fields
        self._serialize_computed_fields(instance, result, context)

        return result

    def serialize_many(
        self, instances, context: SerializationContext | None = None
    ) -> list[dict[str, Any]]:
        """Serialize multiple instances"""
        if not instances:
            return []

        return [self.serialize(instance, context) for instance in instances]

    def deserialize(
        self,
        data: dict[str, Any],
        instance=None,
        context: SerializationContext | None = None,
    ) -> dict[str, Any]:
        """
        Deserialize dictionary to model field data

        Args:
            data: Dictionary data to deserialize
            instance: Existing instance (for updates)
            context: Deserialization context

        Returns:
            Dictionary of model field data ready for create/update
        """
        context = context or SerializationContext()
        result = {}

        for api_field, value in data.items():
            # Skip read-only fields
            if api_field in self.config.read_only_fields:
                continue

            # Reverse field mapping
            model_field = self._reverse_field_mapping(api_field)

            # Apply reverse transformation if configured
            if model_field in self.config.transforms:
                transform_func = self.config.transforms[model_field]
                if callable(transform_func) and hasattr(transform_func, "reverse"):
                    value = transform_func.reverse(value)

            result[model_field] = value

        return result

    def _get_model_fields(self, instance) -> list[str]:
        """Get list of model field names"""
        if hasattr(instance, "_meta") and hasattr(instance._meta, "fields"):
            # Django-style model
            return list(instance._meta.fields.keys())
        elif hasattr(instance, "__dict__"):
            # Simple object with attributes
            return [key for key in instance.__dict__.keys() if not key.startswith("_")]
        else:
            # Try to inspect the class
            return [
                attr
                for attr in dir(instance)
                if not attr.startswith("_") and not callable(getattr(instance, attr))
            ]

    def _get_fields_to_include(self, model_fields: list[str]) -> list[str]:
        """Determine which fields to include in serialization"""
        if self.config.include is not None:
            # Only include explicitly listed fields
            fields = []
            for field_spec in self.config.include:
                if "." in field_spec:
                    # Related field (e.g., 'user.name')
                    base_field = field_spec.split(".")[0]
                    if base_field not in fields:
                        fields.append(base_field)
                else:
                    fields.append(field_spec)
        else:
            # Include all model fields
            fields = model_fields.copy()

        # Remove excluded fields
        for excluded_field in self.config.exclude:
            if excluded_field in fields:
                fields.remove(excluded_field)

        return fields

    def _serialize_model_fields(
        self,
        instance,
        fields_to_include: list[str],
        result: dict[str, Any],
        context: SerializationContext,
    ) -> None:
        """Serialize regular model fields"""
        for field_name in fields_to_include:
            if field_name in self.config.write_only_fields:
                continue

            field_value = self._get_field_value_safely(instance, field_name)
            if field_value is None and not hasattr(instance, field_name):
                continue

            field_value = self._apply_field_transformation(
                field_value, field_name, context
            )
            field_value = self._serialize_related_field(
                field_value, field_name, context
            )

            api_field_name = self.config.field_mappings.get(field_name, field_name)
            result[api_field_name] = self._serialize_value(field_value)

    def _serialize_computed_fields(
        self, instance, result: dict[str, Any], context: SerializationContext
    ) -> None:
        """Serialize computed fields"""
        for field_name, compute_func in self.config.computed_fields.items():
            computed_value = self._compute_field_value_safely(
                compute_func, instance, context
            )
            if computed_value is not None:
                result[field_name] = self._serialize_value(computed_value)

    def _get_field_value_safely(self, instance, field_name: str):
        """Get field value from instance, handling AttributeError"""
        try:
            return getattr(instance, field_name, None)
        except AttributeError:
            return None

    def _apply_field_transformation(
        self, field_value, field_name: str, context: SerializationContext
    ):
        """Apply transformation to field value if configured"""
        if field_name not in self.config.transforms:
            return field_value

        transform_func = self.config.transforms[field_name]
        if not callable(transform_func):
            return field_value

        sig = inspect.signature(transform_func)
        if "context" in sig.parameters:
            return transform_func(field_value, context=context)
        else:
            return transform_func(field_value)

    def _serialize_related_field(
        self, field_value, field_name: str, context: SerializationContext
    ):
        """Serialize related field if configured"""
        if field_name not in self.config.related or field_value is None:
            return field_value

        related_config = self.config.related[field_name]
        related_serializer = ModelSerializer(related_config)

        if isinstance(field_value, list | tuple):
            return [related_serializer.serialize(item, context) for item in field_value]
        else:
            return related_serializer.serialize(field_value, context)

    def _compute_field_value_safely(
        self, compute_func: Callable, instance, context: SerializationContext
    ):
        """Compute field value, handling exceptions gracefully"""
        try:
            if not callable(compute_func):
                return None

            sig = inspect.signature(compute_func)
            if "context" in sig.parameters:
                return compute_func(instance, context=context)
            else:
                return compute_func(instance)
        except Exception:
            # Log error in production
            return None

    def _reverse_field_mapping(self, api_field: str) -> str:
        """Reverse field mapping from API field to model field"""
        for model_field, mapped_api_field in self.config.field_mappings.items():
            if mapped_api_field == api_field:
                return model_field
        return api_field

    def _serialize_value(self, value) -> Any:
        """Serialize individual value with type handling"""
        if value is None:
            return None
        elif isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, Enum):
            return value.value
        elif hasattr(value, "to_dict"):
            # Model with to_dict method
            return value.to_dict()
        elif hasattr(value, "__dict__") and not isinstance(value, type):
            # Simple object - convert to dict
            return {k: v for k, v in value.__dict__.items() if not k.startswith("_")}
        else:
            return value


# Common field transformations
class FieldTransforms:
    """Common field transformation functions"""

    @staticmethod
    def cents_to_dollars(cents_value):
        """Convert cents to dollars"""
        if cents_value is None:
            return None
        return cents_value / 100

    @staticmethod
    def dollars_to_cents(dollar_value):
        """Convert dollars to cents"""
        if dollar_value is None:
            return None
        return int(dollar_value * 100)

    @staticmethod
    def format_datetime(dt, format_str="%Y-%m-%d %H:%M:%S"):
        """Format datetime to string"""
        if dt is None:
            return None
        if isinstance(dt, str):
            return dt
        return dt.strftime(format_str)

    @staticmethod
    def boolean_to_int(bool_value):
        """Convert boolean to integer"""
        if bool_value is None:
            return None
        return 1 if bool_value else 0

    @staticmethod
    def int_to_boolean(int_value):
        """Convert integer to boolean"""
        if int_value is None:
            return None
        return bool(int_value)

    @staticmethod
    def json_list_to_string(json_list):
        """Convert JSON list to comma-separated string"""
        if not json_list:
            return ""
        return ", ".join(str(item) for item in json_list)

    @staticmethod
    def string_to_json_list(string_value):
        """Convert comma-separated string to list"""
        if not string_value:
            return []
        return [item.strip() for item in string_value.split(",")]


# Set up reverse relationships after class definition
FieldTransforms.cents_to_dollars.reverse = FieldTransforms.dollars_to_cents
FieldTransforms.boolean_to_int.reverse = FieldTransforms.int_to_boolean
FieldTransforms.json_list_to_string.reverse = FieldTransforms.string_to_json_list


class SerializerMixin:
    """
    Mixin for models to add serialization capabilities
    Add this to your model classes to eliminate to_dict() boilerplate
    """

    # Override in subclass to configure serialization
    _serializer_config: SerializerConfig | None = None

    def to_dict(self, context: SerializationContext | None = None) -> dict[str, Any]:
        """Serialize model instance to dictionary"""
        config = self._get_serializer_config()
        serializer = ModelSerializer(config)
        return serializer.serialize(self, context)

    def to_api_dict(
        self, context: SerializationContext | None = None
    ) -> dict[str, Any]:
        """Alias for to_dict() for clarity"""
        return self.to_dict(context)

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], context: SerializationContext | None = None
    ):
        """Create model instance from dictionary data"""
        config = cls._get_serializer_config()
        serializer = ModelSerializer(config)
        model_data = serializer.deserialize(data, context=context)
        return cls(**model_data)

    @classmethod
    def _get_serializer_config(cls) -> SerializerConfig:
        """Get serializer configuration for this model"""
        if cls._serializer_config:
            return cls._serializer_config

        # Create default configuration
        return SerializerConfig()

    @classmethod
    def serialize_many(
        cls, instances, context: SerializationContext | None = None
    ) -> list[dict[str, Any]]:
        """Serialize multiple instances of this model"""
        config = cls._get_serializer_config()
        serializer = ModelSerializer(config)
        return serializer.serialize_many(instances, context)


# Utility functions for quick serialization
def serialize_model(
    instance,
    config: SerializerConfig | None = None,
    context: SerializationContext | None = None,
) -> dict[str, Any]:
    """Quick function to serialize a model instance"""
    serializer = ModelSerializer(config or SerializerConfig())
    return serializer.serialize(instance, context)


def serialize_models(
    instances,
    config: SerializerConfig | None = None,
    context: SerializationContext | None = None,
) -> list[dict[str, Any]]:
    """Quick function to serialize multiple model instances"""
    serializer = ModelSerializer(config or SerializerConfig())
    return serializer.serialize_many(instances, context)
