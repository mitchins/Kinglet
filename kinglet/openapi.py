"""
Kinglet OpenAPI 3.0 Schema Generator
Automatically generates OpenAPI documentation from routes, validators, and models
"""

from __future__ import annotations

import inspect
import re
from typing import Any, get_args, get_origin

from .core import Kinglet, Route
from .orm import (
    BooleanField,
    DateTimeField,
    Field,
    FloatField,
    IntegerField,
    JSONField,
    StringField,
)
from .validation import (
    ChoicesValidator,
    DateValidator,
    EmailValidator,
    LengthValidator,
    PasswordValidator,
    RangeValidator,
    RegexValidator,
    RequiredValidator,
    Validator,
)

# Constants
CONTENT_TYPE_JSON = "application/json"


class SchemaGenerator:
    """Generate OpenAPI 3.0 specification from Kinglet application"""

    def __init__(
        self,
        app: Kinglet,
        title: str = "API",
        version: str = "1.0.0",
        description: str = "",
    ):
        self.app = app
        self.title = title
        self.version = version
        self.description = description
        self._components_cache: dict[str, Any] = {}

    def generate_spec(self) -> dict[str, Any]:
        """Generate complete OpenAPI 3.0 specification"""
        return {
            "openapi": "3.0.0",
            "info": {
                "title": self.title,
                "version": self.version,
                "description": self.description,
            },
            "paths": self._generate_paths(),
            "components": self._generate_components(),
        }

    def _generate_paths(self) -> dict[str, dict]:
        """Extract routes and generate OpenAPI paths"""
        paths: dict[str, dict] = {}

        for route in self.app.router.routes:
            path_key = self._normalize_path(route.path)

            if path_key not in paths:
                paths[path_key] = {}

            for method in route.methods:
                method_lower = method.lower()
                paths[path_key][method_lower] = self._generate_endpoint(route, method)

        return paths

    def _generate_endpoint(self, route: Route, method: str) -> dict[str, Any]:
        """Generate OpenAPI endpoint definition"""
        endpoint: dict[str, Any] = {
            "summary": self._extract_summary(route.handler),
            "responses": self._extract_responses(route),
        }

        # Add description from docstring if available
        docstring = self._extract_docstring(route.handler)
        if docstring:
            endpoint["description"] = docstring

        # Add parameters (path and query)
        parameters = self._extract_parameters(route)
        if parameters:
            endpoint["parameters"] = parameters

        # Add request body for POST/PUT/PATCH
        if method.upper() in ["POST", "PUT", "PATCH"]:
            request_schema = self._extract_request_schema(route)
            if request_schema:
                endpoint["requestBody"] = {
                    "required": True,
                    "content": {CONTENT_TYPE_JSON: {"schema": request_schema}},
                }

        # Add tags based on path
        tags = self._extract_tags(route.path)
        if tags:
            endpoint["tags"] = tags

        return endpoint

    def _extract_request_schema(self, route: Route) -> dict[str, Any] | None:
        """Extract request schema from validation metadata"""
        if hasattr(route.handler, "_validation_schema"):
            schema = route.handler._validation_schema
            return self._schema_to_openapi(schema)
        return None

    def _extract_responses(self, route: Route) -> dict[str, Any]:
        """Extract response schemas from handler"""
        responses = {
            "200": {
                "description": "Successful response",
                "content": {
                    CONTENT_TYPE_JSON: {"schema": self._infer_response_schema(route)}
                },
            }
        }

        # Add common error responses
        responses.update(
            {
                "400": {"description": "Bad Request - Invalid input"},
                "401": {"description": "Unauthorized - Authentication required"},
                "404": {"description": "Not Found - Resource does not exist"},
                "500": {"description": "Internal Server Error"},
            }
        )

        return responses

    def _extract_parameters(self, route: Route) -> list[dict]:
        """Extract path and query parameters from route"""
        parameters = []

        # Extract path parameters from route.param_names
        for param in route.param_names:
            parameters.append(
                {
                    "name": param,
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string"},
                    "description": f"Path parameter {param}",
                }
            )

        return parameters

    def _generate_components(self) -> dict[str, Any]:
        """Generate reusable components (schemas, responses)"""
        return {
            "schemas": self._components_cache,
            "responses": {
                "UnauthorizedError": {
                    "description": "Authentication credentials were not provided or are invalid"
                },
                "NotFoundError": {
                    "description": "The requested resource was not found"
                },
                "ValidationError": {
                    "description": "Input validation failed",
                    "content": {
                        CONTENT_TYPE_JSON: {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "error": {"type": "string"},
                                    "errors": {
                                        "type": "object",
                                        "additionalProperties": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                    },
                                },
                            }
                        }
                    },
                },
            },
        }

    def serve_swagger_ui(self, spec_url: str = "/openapi.json") -> str:
        """Generate Swagger UI HTML page"""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="description" content="SwaggerUI" />
    <title>{self.title} - API Documentation</title>
    <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5.11.0/swagger-ui.css" />
</head>
<body>
<div id="swagger-ui"></div>
<script src="https://unpkg.com/swagger-ui-dist@5.11.0/swagger-ui-bundle.js" crossorigin></script>
<script>
  window.onload = () => {{
    window.ui = SwaggerUIBundle({{
      url: '{spec_url}',
      dom_id: '#swagger-ui',
      deepLinking: true,
      presets: [
        SwaggerUIBundle.presets.apis,
        SwaggerUIBundle.SwaggerUIStandalonePreset
      ],
      layout: "BaseLayout"
    }});
  }};
</script>
</body>
</html>"""

    def serve_redoc(self, spec_url: str = "/openapi.json") -> str:
        """Generate ReDoc HTML page"""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{self.title} - API Documentation</title>
    <link href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700" rel="stylesheet">
    <style>
      body {{
        margin: 0;
        padding: 0;
      }}
    </style>
</head>
<body>
    <redoc spec-url='{spec_url}'></redoc>
    <script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"></script>
</body>
</html>"""

    def _normalize_path(self, path: str) -> str:
        """Convert Kinglet path pattern to OpenAPI path format"""
        # Convert {param:type} to {param}
        normalized = re.sub(r"\{([^:}]+):[^}]+\}", r"{\1}", path)
        return normalized

    def _extract_summary(self, handler) -> str:
        """Extract endpoint summary from handler function name"""
        name = handler.__name__.replace("_", " ").title()
        return name

    def _extract_docstring(self, handler) -> str:
        """Extract description from handler docstring"""
        docstring = inspect.getdoc(handler)
        return docstring if docstring else ""

    def _extract_tags(self, path: str) -> list[str]:
        """Extract tags from path (e.g., /users/123 -> ['users'])"""
        parts = path.strip("/").split("/")
        if parts and parts[0] and not parts[0].startswith("{"):
            return [parts[0]]
        return []

    def _schema_to_openapi(self, schema: dict) -> dict[str, Any]:
        """Convert Kinglet ValidationSchema to OpenAPI schema"""
        properties = {}
        required = []

        for field_name, validators in schema.items():
            if not isinstance(validators, list):
                validators = [validators]

            field_schema = self._validators_to_schema(validators)
            properties[field_name] = field_schema

            # Check if field is required
            if any(isinstance(v, RequiredValidator) for v in validators):
                required.append(field_name)

        openapi_schema = {"type": "object", "properties": properties}

        if required:
            openapi_schema["required"] = required

        return openapi_schema

    def _validators_to_schema(self, validators: list[Validator]) -> dict[str, Any]:
        """Convert list of validators to OpenAPI field schema"""
        schema: dict[str, Any] = {"type": "string"}

        for validator in validators:
            self._apply_validator_to_schema(validator, schema)

        return schema

    def _apply_validator_to_schema(
        self, validator: Validator, schema: dict[str, Any]
    ) -> None:
        """Apply a single validator's constraints to the schema"""
        if isinstance(validator, EmailValidator):
            schema["format"] = "email"
        elif isinstance(validator, DateValidator):
            schema["type"] = "string"
            schema["format"] = "date"
        elif isinstance(validator, PasswordValidator):
            self._apply_length_constraint(validator, schema, "min_length", "minLength")
        elif isinstance(validator, LengthValidator):
            self._apply_length_constraint(validator, schema, "min_length", "minLength")
            self._apply_length_constraint(validator, schema, "max_length", "maxLength")
        elif isinstance(validator, RangeValidator):
            schema["type"] = "integer"
            self._apply_range_constraint(validator, schema)
        elif isinstance(validator, ChoicesValidator):
            if hasattr(validator, "choices"):
                schema["enum"] = list(validator.choices)
        elif isinstance(validator, RegexValidator):
            if hasattr(validator, "pattern"):
                schema["pattern"] = validator.pattern

    def _apply_length_constraint(
        self, validator: Validator, schema: dict[str, Any], attr: str, schema_key: str
    ) -> None:
        """Apply a length constraint from validator to schema"""
        if hasattr(validator, attr) and getattr(validator, attr):
            schema[schema_key] = getattr(validator, attr)

    def _apply_range_constraint(
        self, validator: Validator, schema: dict[str, Any]
    ) -> None:
        """Apply min/max range constraints from validator to schema"""
        if hasattr(validator, "min_value") and validator.min_value is not None:
            schema["minimum"] = validator.min_value
        if hasattr(validator, "max_value") and validator.max_value is not None:
            schema["maximum"] = validator.max_value

    def _infer_response_schema(self, route: Route) -> dict[str, Any]:
        """Infer response schema from handler return type annotation"""
        # Check for return type annotation
        sig = inspect.signature(route.handler)
        return_annotation = sig.return_annotation

        if return_annotation != inspect.Signature.empty:
            # Handle generic types (like list[Model])
            origin = get_origin(return_annotation)
            if origin is list:
                args = get_args(return_annotation)
                if args and hasattr(args[0], "_fields"):
                    # List of models
                    return {
                        "type": "array",
                        "items": self._model_to_schema(args[0]),
                    }

            # Handle single model
            if hasattr(return_annotation, "_fields"):
                return self._model_to_schema(return_annotation)

        # Default: generic object
        return {"type": "object"}

    def _model_to_schema(self, model_class) -> dict[str, Any]:
        """Convert ORM Model to OpenAPI schema"""
        model_name = model_class.__name__

        # Check cache first
        if model_name in self._components_cache:
            return {"$ref": f"#/components/schemas/{model_name}"}

        properties, required = self._extract_model_properties(model_class)

        schema = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required

        # Cache and return reference
        self._components_cache[model_name] = schema
        return {"$ref": f"#/components/schemas/{model_name}"}

    def _extract_model_properties(
        self, model_class
    ) -> tuple[dict[str, Any], list[str]]:
        """Extract properties and required fields from a model class"""
        properties: dict[str, Any] = {}
        required: list[str] = []

        if not hasattr(model_class, "_fields"):
            return properties, required

        serializer_config = getattr(model_class, "_serializer_config", None)

        for field_name, field_obj in model_class._fields.items():
            if self._should_skip_field(field_name, serializer_config):
                continue

            properties[field_name] = self._field_to_schema(field_obj)

            if not field_obj.null and field_obj.default is None:
                required.append(field_name)

        return properties, required

    def _should_skip_field(self, field_name: str, config) -> bool:
        """Check if a field should be excluded from the schema"""
        if config is None:
            return False
        if config.exclude and field_name in config.exclude:
            return True
        if config.write_only_fields and field_name in config.write_only_fields:
            return True
        if config.include and field_name not in config.include:
            return True
        return False

    def _field_to_schema(self, field: Field) -> dict[str, Any]:
        """Convert ORM Field to OpenAPI schema property"""
        schema = self._get_base_field_schema(field)

        if field.default is not None:
            schema["default"] = field.default

        return schema

    def _get_base_field_schema(self, field: Field) -> dict[str, Any]:
        """Get the base schema for a field based on its type"""
        if isinstance(field, StringField):
            return self._string_field_schema(field)
        if isinstance(field, IntegerField):
            return self._numeric_field_schema(field, "integer")
        if isinstance(field, FloatField):
            return self._numeric_field_schema(field, "number")
        if isinstance(field, BooleanField):
            return {"type": "boolean"}
        if isinstance(field, DateTimeField):
            return {"type": "string", "format": "date-time"}
        if isinstance(field, JSONField):
            return {"type": "object"}
        return {"type": "string"}

    def _string_field_schema(self, field: StringField) -> dict[str, Any]:
        """Generate schema for a string field"""
        schema: dict[str, Any] = {"type": "string"}
        if field.max_length:
            schema["maxLength"] = field.max_length
        return schema

    def _numeric_field_schema(self, field: Field, type_name: str) -> dict[str, Any]:
        """Generate schema for numeric fields (integer or number)"""
        schema: dict[str, Any] = {"type": type_name}
        if hasattr(field, "min_value") and field.min_value is not None:
            schema["minimum"] = field.min_value
        if hasattr(field, "max_value") and field.max_value is not None:
            schema["maximum"] = field.max_value
        return schema
