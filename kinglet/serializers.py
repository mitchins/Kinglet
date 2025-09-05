"""
Kinglet Model Serialization System
Eliminates boilerplate for model-to-API response formatting
"""

import inspect
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set


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
    include: Optional[List[str]] = None

    # Fields to exclude
    exclude: Optional[List[str]] = field(default_factory=list)

    # Field transformations: field_name -> function
    transforms: Optional[Dict[str, Callable]] = field(default_factory=dict)

    # Related field serialization: field_name -> nested serializer config
    related: Optional[Dict[str, "SerializerConfig"]] = field(default_factory=dict)

    # Custom field mappings: model_field -> api_field
    field_mappings: Optional[Dict[str, str]] = field(default_factory=dict)

    # Additional computed fields: field_name -> function
    computed_fields: Optional[Dict[str, Callable]] = field(default_factory=dict)

    # Read-only fields (excluded from deserialization)
    read_only_fields: Optional[Set[str]] = field(default_factory=set)

    # Write-only fields (excluded from serialization)
    write_only_fields: Optional[Set[str]] = field(default_factory=set)


class ModelSerializer:
    """
    Base model serializer with automatic field detection
    Eliminates manual to_dict() method boilerplate
    """

    def __init__(self, config: Optional[SerializerConfig] = None):
        self.config = config or SerializerConfig()

    def serialize(
        self, instance, context: Optional[SerializationContext] = None
    ) -> Dict[str, Any]:
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

        # Get all model fields
        model_fields = self._get_model_fields(instance)

        # Determine fields to include
        fields_to_include = self._get_fields_to_include(model_fields)

        # Serialize each field
        for field_name in fields_to_include:
            # Skip write-only fields
            if field_name in self.config.write_only_fields:
                continue

            try:
                # Get field value
                field_value = getattr(instance, field_name, None)

                # Apply transformation if configured
                if field_name in self.config.transforms:
                    transform_func = self.config.transforms[field_name]
                    if callable(transform_func):
                        # Pass context to transform function if it accepts it
                        sig = inspect.signature(transform_func)
                        if "context" in sig.parameters:
                            field_value = transform_func(field_value, context=context)
                        else:
                            field_value = transform_func(field_value)

                # Handle related field serialization
                if field_name in self.config.related and field_value is not None:
                    related_config = self.config.related[field_name]
                    related_serializer = ModelSerializer(related_config)

                    # Handle list of related objects
                    if isinstance(field_value, (list, tuple)):
                        field_value = [
                            related_serializer.serialize(item, context)
                            for item in field_value
                        ]
                    else:
                        field_value = related_serializer.serialize(field_value, context)

                # Apply field mapping
                api_field_name = self.config.field_mappings.get(field_name, field_name)

                # Set serialized value
                result[api_field_name] = self._serialize_value(field_value)

            except AttributeError:
                # Field doesn't exist on model, skip
                continue

        # Add computed fields
        for field_name, compute_func in self.config.computed_fields.items():
            try:
                # Pass instance and context to compute function
                sig = inspect.signature(compute_func)
                if "context" in sig.parameters:
                    computed_value = compute_func(instance, context=context)
                else:
                    computed_value = compute_func(instance)

                result[field_name] = self._serialize_value(computed_value)
            except Exception:
                # Skip failed computed fields
                continue

        return result

    def serialize_many(
        self, instances, context: Optional[SerializationContext] = None
    ) -> List[Dict[str, Any]]:
        """Serialize multiple instances"""
        if not instances:
            return []

        return [self.serialize(instance, context) for instance in instances]

    def deserialize(
        self,
        data: Dict[str, Any],
        instance=None,
        context: Optional[SerializationContext] = None,
    ) -> Dict[str, Any]:
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

    def _get_model_fields(self, instance) -> List[str]:
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

    def _get_fields_to_include(self, model_fields: List[str]) -> List[str]:
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

    # Make it reversible
    cents_to_dollars.reverse = dollars_to_cents

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

    boolean_to_int.reverse = int_to_boolean

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

    json_list_to_string.reverse = string_to_json_list


class SerializerMixin:
    """
    Mixin for models to add serialization capabilities
    Add this to your model classes to eliminate to_dict() boilerplate
    """

    # Override in subclass to configure serialization
    _serializer_config: Optional[SerializerConfig] = None

    def to_dict(self, context: Optional[SerializationContext] = None) -> Dict[str, Any]:
        """Serialize model instance to dictionary"""
        config = self._get_serializer_config()
        serializer = ModelSerializer(config)
        return serializer.serialize(self, context)

    def to_api_dict(
        self, context: Optional[SerializationContext] = None
    ) -> Dict[str, Any]:
        """Alias for to_dict() for clarity"""
        return self.to_dict(context)

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], context: Optional[SerializationContext] = None
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
        cls, instances, context: Optional[SerializationContext] = None
    ) -> List[Dict[str, Any]]:
        """Serialize multiple instances of this model"""
        config = cls._get_serializer_config()
        serializer = ModelSerializer(config)
        return serializer.serialize_many(instances, context)


# Utility functions for quick serialization
def serialize_model(
    instance,
    config: Optional[SerializerConfig] = None,
    context: Optional[SerializationContext] = None,
) -> Dict[str, Any]:
    """Quick function to serialize a model instance"""
    serializer = ModelSerializer(config or SerializerConfig())
    return serializer.serialize(instance, context)


def serialize_models(
    instances,
    config: Optional[SerializerConfig] = None,
    context: Optional[SerializationContext] = None,
) -> List[Dict[str, Any]]:
    """Quick function to serialize multiple model instances"""
    serializer = ModelSerializer(config or SerializerConfig())
    return serializer.serialize_many(instances, context)
