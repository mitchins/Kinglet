"""
Tests for Kinglet OpenAPI Schema Generator
Comprehensive test coverage for OpenAPI 3.0 spec generation
"""

import pytest

from kinglet import Kinglet, SchemaGenerator
from kinglet.orm import BooleanField, DateTimeField, IntegerField, Model, StringField
from kinglet.validation import (
    ChoicesValidator,
    DateValidator,
    EmailValidator,
    LengthValidator,
    PasswordValidator,
    RangeValidator,
    RequiredValidator,
)


class TestSchemaGenerator:
    """Test SchemaGenerator initialization and basic functionality"""

    def test_init_default_values(self):
        """Test SchemaGenerator with default values"""
        app = Kinglet()
        generator = SchemaGenerator(app)

        assert generator.app is app
        assert generator.title == "API"
        assert generator.version == "1.0.0"
        assert generator.description == ""

    def test_init_custom_values(self):
        """Test SchemaGenerator with custom values"""
        app = Kinglet()
        generator = SchemaGenerator(
            app,
            title="My API",
            version="2.0.0",
            description="Custom API description",
        )

        assert generator.title == "My API"
        assert generator.version == "2.0.0"
        assert generator.description == "Custom API description"

    def test_generate_spec_structure(self):
        """Test that generate_spec returns valid OpenAPI 3.0 structure"""
        app = Kinglet()
        generator = SchemaGenerator(app, title="Test API", version="1.0.0")

        spec = generator.generate_spec()

        assert spec["openapi"] == "3.0.0"
        assert "info" in spec
        assert spec["info"]["title"] == "Test API"
        assert spec["info"]["version"] == "1.0.0"
        assert "paths" in spec
        assert "components" in spec


class TestPathGeneration:
    """Test OpenAPI path generation from routes"""

    def test_simple_get_route(self):
        """Test generating path for simple GET route"""
        app = Kinglet()

        @app.get("/users")
        async def get_users(request):
            """Get all users"""
            return {"users": []}

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        assert "/users" in spec["paths"]
        assert "get" in spec["paths"]["/users"]
        assert spec["paths"]["/users"]["get"]["summary"] == "Get Users"

    def test_path_parameters(self):
        """Test generating path with parameters"""
        app = Kinglet()

        @app.get("/users/{user_id}")
        async def get_user(request, user_id):
            return {"id": user_id}

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        assert "/users/{user_id}" in spec["paths"]
        params = spec["paths"]["/users/{user_id}"]["get"]["parameters"]
        assert len(params) == 1
        assert params[0]["name"] == "user_id"
        assert params[0]["in"] == "path"
        assert params[0]["required"] is True

    def test_typed_path_parameters(self):
        """Test path parameters with type hints"""
        app = Kinglet()

        @app.get("/posts/{post_id:int}")
        async def get_post(request, post_id):
            return {"id": post_id}

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        # Path should be normalized to {post_id}
        assert "/posts/{post_id}" in spec["paths"]

    def test_multiple_methods(self):
        """Test route with multiple HTTP methods"""
        app = Kinglet()

        @app.route("/items", methods=["GET", "POST"])
        async def items(request):
            return {}

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        assert "/items" in spec["paths"]
        assert "get" in spec["paths"]["/items"]
        assert "post" in spec["paths"]["/items"]

    def test_tags_from_path(self):
        """Test tag extraction from path"""
        app = Kinglet()

        @app.get("/users/profile")
        async def get_profile(request):
            return {}

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        assert "tags" in spec["paths"]["/users/profile"]["get"]
        assert spec["paths"]["/users/profile"]["get"]["tags"] == ["users"]


class TestValidationSchemaConversion:
    """Test converting validation schemas to OpenAPI request schemas"""

    def test_email_validator(self):
        """Test EmailValidator conversion"""
        app = Kinglet()

        @app.post("/register")
        async def register(request):
            return {}

        # Manually add validation schema metadata
        register._validation_schema = {"email": [EmailValidator()]}

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        request_body = spec["paths"]["/register"]["post"]["requestBody"]
        schema = request_body["content"]["application/json"]["schema"]

        assert schema["properties"]["email"]["type"] == "string"
        assert schema["properties"]["email"]["format"] == "email"

    def test_required_validator(self):
        """Test RequiredValidator marks fields as required"""
        app = Kinglet()

        @app.post("/login")
        async def login(request):
            return {}

        login._validation_schema = {
            "email": [RequiredValidator(), EmailValidator()],
            "password": [RequiredValidator()],
        }

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        schema = spec["paths"]["/login"]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"]

        assert "required" in schema
        assert "email" in schema["required"]
        assert "password" in schema["required"]

    def test_length_validator(self):
        """Test LengthValidator conversion"""
        app = Kinglet()

        @app.post("/submit")
        async def submit(request):
            return {}

        submit._validation_schema = {
            "username": [LengthValidator(min_length=3, max_length=20)]
        }

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        schema = spec["paths"]["/submit"]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"]

        assert schema["properties"]["username"]["minLength"] == 3
        assert schema["properties"]["username"]["maxLength"] == 20

    def test_range_validator(self):
        """Test RangeValidator conversion"""
        app = Kinglet()

        @app.post("/create")
        async def create(request):
            return {}

        create._validation_schema = {
            "age": [RangeValidator(min_value=18, max_value=120)]
        }

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        schema = spec["paths"]["/create"]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"]

        assert schema["properties"]["age"]["type"] == "integer"
        assert schema["properties"]["age"]["minimum"] == 18
        assert schema["properties"]["age"]["maximum"] == 120

    def test_password_validator(self):
        """Test PasswordValidator conversion"""
        app = Kinglet()

        @app.post("/register")
        async def register(request):
            return {}

        register._validation_schema = {"password": [PasswordValidator(min_length=8)]}

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        schema = spec["paths"]["/register"]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"]

        assert schema["properties"]["password"]["minLength"] == 8

    def test_choices_validator(self):
        """Test ChoicesValidator conversion"""
        app = Kinglet()

        @app.post("/select")
        async def select(request):
            return {}

        select._validation_schema = {
            "status": [ChoicesValidator(choices=["active", "inactive", "pending"])]
        }

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        schema = spec["paths"]["/select"]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"]

        assert schema["properties"]["status"]["enum"] == [
            "active",
            "inactive",
            "pending",
        ]

    def test_date_validator(self):
        """Test DateValidator conversion"""
        app = Kinglet()

        @app.post("/schedule")
        async def schedule(request):
            return {}

        schedule._validation_schema = {"date": [DateValidator()]}

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        schema = spec["paths"]["/schedule"]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"]

        assert schema["properties"]["date"]["type"] == "string"
        assert schema["properties"]["date"]["format"] == "date"

    def test_combined_validators(self):
        """Test multiple validators on same field"""
        app = Kinglet()

        @app.post("/signup")
        async def signup(request):
            return {}

        signup._validation_schema = {
            "email": [RequiredValidator(), EmailValidator()],
            "password": [
                RequiredValidator(),
                PasswordValidator(min_length=8),
            ],
            "age": [RequiredValidator(), RangeValidator(min_value=13, max_value=120)],
        }

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        schema = spec["paths"]["/signup"]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"]

        # Check email
        assert schema["properties"]["email"]["format"] == "email"

        # Check password
        assert schema["properties"]["password"]["minLength"] == 8

        # Check age
        assert schema["properties"]["age"]["type"] == "integer"
        assert schema["properties"]["age"]["minimum"] == 13
        assert schema["properties"]["age"]["maximum"] == 120

        # Check all required
        assert set(schema["required"]) == {"email", "password", "age"}


class TestModelConversion:
    """Test converting ORM Models to OpenAPI response schemas"""

    def test_simple_model(self):
        """Test converting simple model to schema"""

        class User(Model):
            email = StringField(max_length=255)
            age = IntegerField()
            is_active = BooleanField()

        app = Kinglet()
        generator = SchemaGenerator(app)

        schema = generator._model_to_schema(User)

        assert "$ref" in schema
        assert "User" in generator._components_cache

        user_schema = generator._components_cache["User"]
        assert user_schema["type"] == "object"
        assert "email" in user_schema["properties"]
        assert "age" in user_schema["properties"]
        assert "is_active" in user_schema["properties"]

    def test_model_with_constraints(self):
        """Test model field constraints are preserved"""

        class Product(Model):
            name = StringField(max_length=100)
            price = IntegerField()

        app = Kinglet()
        generator = SchemaGenerator(app)

        generator._model_to_schema(Product)
        schema = generator._components_cache["Product"]

        assert schema["properties"]["name"]["maxLength"] == 100
        assert schema["properties"]["price"]["type"] == "integer"

    def test_model_with_datetime(self):
        """Test DateTimeField conversion"""

        class Event(Model):
            name = StringField()
            created_at = DateTimeField()

        app = Kinglet()
        generator = SchemaGenerator(app)

        generator._model_to_schema(Event)
        schema = generator._components_cache["Event"]

        assert schema["properties"]["created_at"]["type"] == "string"
        assert schema["properties"]["created_at"]["format"] == "date-time"

    def test_model_caching(self):
        """Test that models are cached and referenced"""

        class User(Model):
            name = StringField()

        app = Kinglet()
        generator = SchemaGenerator(app)

        # First call should cache
        schema1 = generator._model_to_schema(User)
        # Second call should return reference
        schema2 = generator._model_to_schema(User)

        assert schema1 == schema2
        assert schema1 == {"$ref": "#/components/schemas/User"}


class TestResponseInference:
    """Test response schema inference from return types"""

    def test_no_return_annotation(self):
        """Test default schema when no return annotation"""
        app = Kinglet()

        @app.get("/data")
        async def get_data(request):
            return {}

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        response_schema = spec["paths"]["/data"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]

        assert response_schema["type"] == "object"

    def test_model_return_annotation(self):
        """Test model return type annotation"""

        class User(Model):
            name = StringField()
            email = StringField()

        app = Kinglet()

        @app.get("/user")
        async def get_user(request) -> User:
            return None

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        response_schema = spec["paths"]["/user"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]

        assert "$ref" in response_schema
        assert response_schema["$ref"] == "#/components/schemas/User"

    def test_list_return_annotation(self):
        """Test list of models return annotation"""

        class User(Model):
            name = StringField()

        app = Kinglet()

        @app.get("/users")
        async def get_users(request) -> list[User]:
            return []

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        response_schema = spec["paths"]["/users"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]

        assert response_schema["type"] == "array"
        assert "$ref" in response_schema["items"]


class TestSwaggerUI:
    """Test Swagger UI HTML generation"""

    def test_serve_swagger_ui(self):
        """Test Swagger UI HTML generation"""
        app = Kinglet()
        generator = SchemaGenerator(app, title="Test API")

        html = generator.serve_swagger_ui()

        assert "<!DOCTYPE html>" in html
        assert "Test API" in html
        assert "swagger-ui" in html
        assert "/openapi.json" in html
        assert "SwaggerUIBundle" in html

    def test_serve_swagger_ui_custom_spec_url(self):
        """Test Swagger UI with custom spec URL"""
        app = Kinglet()
        generator = SchemaGenerator(app)

        html = generator.serve_swagger_ui(spec_url="/custom/spec.json")

        assert "/custom/spec.json" in html


class TestReDoc:
    """Test ReDoc HTML generation"""

    def test_serve_redoc(self):
        """Test ReDoc HTML generation"""
        app = Kinglet()
        generator = SchemaGenerator(app, title="Test API")

        html = generator.serve_redoc()

        assert "<!DOCTYPE html>" in html
        assert "Test API" in html
        assert "redoc" in html
        assert "/openapi.json" in html

    def test_serve_redoc_custom_spec_url(self):
        """Test ReDoc with custom spec URL"""
        app = Kinglet()
        generator = SchemaGenerator(app)

        html = generator.serve_redoc(spec_url="/api/schema.json")

        assert "/api/schema.json" in html


class TestComponentsGeneration:
    """Test OpenAPI components section generation"""

    def test_components_structure(self):
        """Test components section has correct structure"""
        app = Kinglet()
        generator = SchemaGenerator(app)

        components = generator._generate_components()

        assert "schemas" in components
        assert "responses" in components
        assert "UnauthorizedError" in components["responses"]
        assert "NotFoundError" in components["responses"]
        assert "ValidationError" in components["responses"]

    def test_components_with_models(self):
        """Test components includes model schemas"""

        class User(Model):
            name = StringField()

        app = Kinglet()

        @app.get("/user")
        async def get_user(request) -> User:
            return None

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        assert "User" in spec["components"]["schemas"]


class TestHelperMethods:
    """Test helper methods"""

    def test_normalize_path(self):
        """Test path normalization"""
        app = Kinglet()
        generator = SchemaGenerator(app)

        assert generator._normalize_path("/users/{id}") == "/users/{id}"
        assert generator._normalize_path("/posts/{id:int}") == "/posts/{id}"
        assert generator._normalize_path("/files/{path:path}") == "/files/{path}"

    def test_extract_summary(self):
        """Test summary extraction from function name"""
        app = Kinglet()
        generator = SchemaGenerator(app)

        async def get_user_profile(request):
            pass

        assert generator._extract_summary(get_user_profile) == "Get User Profile"

    def test_extract_docstring(self):
        """Test docstring extraction"""
        app = Kinglet()
        generator = SchemaGenerator(app)

        async def example_handler(request):
            """This is a detailed description of the endpoint"""
            pass

        docstring = generator._extract_docstring(example_handler)
        assert docstring == "This is a detailed description of the endpoint"

    def test_extract_tags(self):
        """Test tag extraction from paths"""
        app = Kinglet()
        generator = SchemaGenerator(app)

        assert generator._extract_tags("/users/123") == ["users"]
        assert generator._extract_tags("/api/posts") == ["api"]
        assert generator._extract_tags("/{id}/items") == []


class TestIntegration:
    """Integration tests with realistic scenarios"""

    def test_complete_crud_api(self):
        """Test complete CRUD API spec generation"""

        class User(Model):
            name = StringField(max_length=100)
            email = StringField(max_length=255)
            age = IntegerField()

        app = Kinglet()

        @app.get("/users")
        async def list_users(request) -> list[User]:
            """List all users"""
            return []

        @app.get("/users/{user_id}")
        async def get_user(request, user_id) -> User:
            """Get a specific user"""
            return None

        @app.post("/users")
        async def create_user(request) -> User:
            """Create a new user"""
            return None

        create_user._validation_schema = {
            "name": [RequiredValidator(), LengthValidator(max_length=100)],
            "email": [RequiredValidator(), EmailValidator()],
            "age": [RequiredValidator(), RangeValidator(min_value=18, max_value=120)],
        }

        @app.put("/users/{user_id}")
        async def update_user(request, user_id) -> User:
            """Update a user"""
            return None

        @app.delete("/users/{user_id}")
        async def delete_user(request, user_id):
            """Delete a user"""
            return {"deleted": True}

        generator = SchemaGenerator(
            app, title="User API", version="1.0.0", description="User management API"
        )

        spec = generator.generate_spec()

        # Verify info
        assert spec["info"]["title"] == "User API"
        assert spec["info"]["version"] == "1.0.0"

        # Verify all endpoints exist
        assert "/users" in spec["paths"]
        assert "/users/{user_id}" in spec["paths"]

        # Verify methods
        assert "get" in spec["paths"]["/users"]
        assert "post" in spec["paths"]["/users"]
        assert "get" in spec["paths"]["/users/{user_id}"]
        assert "put" in spec["paths"]["/users/{user_id}"]
        assert "delete" in spec["paths"]["/users/{user_id}"]

        # Verify request body on POST
        post_spec = spec["paths"]["/users"]["post"]
        assert "requestBody" in post_spec
        assert post_spec["requestBody"]["required"] is True

        # Verify response schema
        get_spec = spec["paths"]["/users"]["get"]
        response_schema = get_spec["responses"]["200"]["content"]["application/json"][
            "schema"
        ]
        assert response_schema["type"] == "array"

        # Verify components
        assert "User" in spec["components"]["schemas"]

    def test_api_with_docstrings_and_tags(self):
        """Test that docstrings and tags are properly included"""
        app = Kinglet()

        @app.get("/products")
        async def list_products(request):
            """
            List all products in the catalog.

            Returns a paginated list of products with basic information.
            """
            return []

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        endpoint = spec["paths"]["/products"]["get"]
        assert "description" in endpoint
        assert "List all products" in endpoint["description"]
        assert endpoint["tags"] == ["products"]

    def test_spec_validation_compliance(self):
        """Test that generated spec follows OpenAPI 3.0 structure"""

        class User(Model):
            name = StringField()

        app = Kinglet()

        @app.get("/users")
        async def get_users(request) -> list[User]:
            return []

        @app.post("/users")
        async def create_user(request):
            return {}

        create_user._validation_schema = {"name": [RequiredValidator()]}

        generator = SchemaGenerator(app, title="API", version="1.0.0")
        spec = generator.generate_spec()

        # OpenAPI 3.0 required fields
        assert spec["openapi"] == "3.0.0"
        assert "info" in spec
        assert "title" in spec["info"]
        assert "version" in spec["info"]
        assert "paths" in spec

        # Paths structure
        for _path, methods in spec["paths"].items():
            for _method, operation in methods.items():
                assert "responses" in operation
                assert "200" in operation["responses"]

        # Components structure
        assert "components" in spec
        if spec["components"].get("schemas"):
            for _schema_name, schema in spec["components"]["schemas"].items():
                assert "type" in schema


class TestEdgeCases:
    """Test edge cases for better coverage"""

    def test_single_validator_not_in_list(self):
        """Test validator passed as single item, not list"""
        from kinglet.validation import RegexValidator

        app = Kinglet()

        @app.post("/test")
        async def test_endpoint(request):
            return {}

        # Single validator, not wrapped in list
        test_endpoint._validation_schema = {"pattern_field": RegexValidator(r"^\d+$")}

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        schema = spec["paths"]["/test"]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"]
        assert "pattern" in schema["properties"]["pattern_field"]

    def test_regex_validator(self):
        """Test RegexValidator produces pattern in schema"""
        from kinglet.validation import RegexValidator

        app = Kinglet()

        @app.post("/test")
        async def test_endpoint(request):
            return {}

        test_endpoint._validation_schema = {"code": [RegexValidator(r"^[A-Z]{3}$")]}

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        schema = spec["paths"]["/test"]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"]
        # Pattern is stored as compiled regex, check it exists
        assert "pattern" in schema["properties"]["code"]

    def test_model_with_serializer_config_exclude(self):
        """Test model with excluded fields via serializer config"""
        from kinglet.serializers import SerializerConfig

        class SecretModel(Model):
            name = StringField()
            password = StringField()
            _serializer_config = SerializerConfig(exclude=["password"])

        app = Kinglet()

        @app.get("/secrets")
        async def get_secrets(request) -> SecretModel:
            return SecretModel()

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        # Should have schema but without password
        assert "SecretModel" in spec["components"]["schemas"]
        props = spec["components"]["schemas"]["SecretModel"]["properties"]
        assert "name" in props
        assert "password" not in props

    def test_model_with_serializer_config_write_only(self):
        """Test model with write-only fields via serializer config"""
        from kinglet.serializers import SerializerConfig

        class UserModel(Model):
            username = StringField()
            password = StringField()
            _serializer_config = SerializerConfig(write_only_fields=["password"])

        app = Kinglet()

        @app.get("/users")
        async def get_users(request) -> UserModel:
            return UserModel()

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        props = spec["components"]["schemas"]["UserModel"]["properties"]
        assert "username" in props
        assert "password" not in props

    def test_model_with_serializer_config_include(self):
        """Test model with include-only fields via serializer config"""
        from kinglet.serializers import SerializerConfig

        class PartialModel(Model):
            id = IntegerField()
            name = StringField()
            secret = StringField()
            _serializer_config = SerializerConfig(include=["id", "name"])

        app = Kinglet()

        @app.get("/partial")
        async def get_partial(request) -> PartialModel:
            return PartialModel()

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        props = spec["components"]["schemas"]["PartialModel"]["properties"]
        assert "id" in props
        assert "name" in props
        assert "secret" not in props

    def test_model_with_nullable_fields(self):
        """Test model handles nullable vs non-nullable fields"""

        class NullableModel(Model):
            required_field = StringField()  # Not nullable by default
            optional_field = StringField(null=True)  # Nullable

        app = Kinglet()

        @app.get("/nullable")
        async def get_nullable(request) -> NullableModel:
            return NullableModel()

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        schema = spec["components"]["schemas"]["NullableModel"]
        # Both fields should be in properties
        assert "required_field" in schema["properties"]
        assert "optional_field" in schema["properties"]

    def test_float_field(self):
        """Test FloatField produces number type"""
        from kinglet.orm import FloatField

        class PriceModel(Model):
            price = FloatField()

        app = Kinglet()

        @app.get("/prices")
        async def get_prices(request) -> PriceModel:
            return PriceModel()

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        props = spec["components"]["schemas"]["PriceModel"]["properties"]
        assert props["price"]["type"] == "number"

    def test_boolean_field(self):
        """Test BooleanField produces boolean type"""

        class FlagModel(Model):
            active = BooleanField()

        app = Kinglet()

        @app.get("/flags")
        async def get_flags(request) -> FlagModel:
            return FlagModel()

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        props = spec["components"]["schemas"]["FlagModel"]["properties"]
        assert props["active"]["type"] == "boolean"

    def test_json_field(self):
        """Test JSONField produces object type"""
        from kinglet.orm import JSONField

        class DataModel(Model):
            metadata = JSONField()

        app = Kinglet()

        @app.get("/data")
        async def get_data(request) -> DataModel:
            return DataModel()

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        props = spec["components"]["schemas"]["DataModel"]["properties"]
        assert props["metadata"]["type"] == "object"

    def test_integer_field_basic(self):
        """Test IntegerField produces integer type"""

        class CountModel(Model):
            count = IntegerField()

        app = Kinglet()

        @app.get("/counts")
        async def get_counts(request) -> CountModel:
            return CountModel()

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        props = spec["components"]["schemas"]["CountModel"]["properties"]
        assert props["count"]["type"] == "integer"

    def test_float_field_basic(self):
        """Test FloatField produces number type"""
        from kinglet.orm import FloatField

        class RateModel(Model):
            rate = FloatField()

        app = Kinglet()

        @app.get("/rates")
        async def get_rates(request) -> RateModel:
            return RateModel()

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        props = spec["components"]["schemas"]["RateModel"]["properties"]
        assert props["rate"]["type"] == "number"

    def test_string_field_with_max_length(self):
        """Test StringField with max_length"""

        class LimitedModel(Model):
            code = StringField(max_length=10)

        app = Kinglet()

        @app.get("/limited")
        async def get_limited(request) -> LimitedModel:
            return LimitedModel()

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        props = spec["components"]["schemas"]["LimitedModel"]["properties"]
        assert props["code"]["maxLength"] == 10

    def test_field_with_default(self):
        """Test field with default value"""

        class DefaultModel(Model):
            status = StringField(default="pending")

        app = Kinglet()

        @app.get("/defaults")
        async def get_defaults(request) -> DefaultModel:
            return DefaultModel()

        generator = SchemaGenerator(app)
        spec = generator.generate_spec()

        props = spec["components"]["schemas"]["DefaultModel"]["properties"]
        assert props["status"]["default"] == "pending"

    def test_model_without_fields_attribute(self):
        """Test handling of class without _fields attribute"""
        app = Kinglet()
        generator = SchemaGenerator(app)

        class NotAModel:
            pass

        # Direct call to internal method
        props, required = generator._extract_model_properties(NotAModel)
        assert props == {}
        assert required == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
