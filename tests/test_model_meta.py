"""
Tests for ModelMeta helper methods to ensure the refactored metaclass
functionality works correctly and has proper test coverage.
"""

from kinglet.orm import IntegerField, Model, ModelMeta, StringField
from kinglet.orm_errors import DoesNotExistError


class TestModelMetaHelperMethods:
    """Test the helper methods in ModelMeta class"""

    def test_extract_fields_with_auto_id(self):
        """Test _extract_fields creates auto ID when no primary key exists"""
        attrs = {
            "name": StringField(max_length=100),
            "description": StringField(max_length=255),
        }

        fields = ModelMeta._extract_fields(attrs)

        # Should have auto-generated ID field
        assert "id" in fields
        assert "name" in fields
        assert "description" in fields
        assert fields["id"].primary_key is True
        assert isinstance(fields["id"], IntegerField)
        assert fields["id"].name == "id"

        # Original attrs should be modified to include ID
        assert "id" in attrs
        assert attrs["id"] is fields["id"]

    def test_extract_fields_with_explicit_primary_key(self):
        """Test _extract_fields doesn't add auto ID when primary key exists"""
        attrs = {
            "uuid": StringField(primary_key=True, max_length=36),
            "name": StringField(max_length=100),
        }

        fields = ModelMeta._extract_fields(attrs)

        # Should not have auto-generated ID field
        assert "id" not in fields
        assert "uuid" in fields
        assert "name" in fields
        assert fields["uuid"].primary_key is True
        assert fields["uuid"].name == "uuid"
        assert fields["name"].name == "name"

    def test_extract_fields_sets_field_names(self):
        """Test that _extract_fields sets the name attribute on all fields"""
        attrs = {
            "title": StringField(max_length=100),
            "content": StringField(max_length=1000),
            "active": IntegerField(),
        }

        fields = ModelMeta._extract_fields(attrs)

        # All fields should have their names set
        for field_name, field in fields.items():
            assert field.name == field_name

    def test_create_meta_attrs_with_explicit_meta(self):
        """Test _create_meta_attrs with explicit Meta class"""

        class TestMeta:
            table_name = "custom_table"
            ordering = ["created_at"]

        attrs = {"Meta": TestMeta}

        meta_attrs = ModelMeta._create_meta_attrs(attrs, "TestModel")

        assert meta_attrs["table_name"] == "custom_table"
        assert meta_attrs["ordering"] == ["created_at"]

    def test_create_meta_attrs_with_default_table_name(self):
        """Test _create_meta_attrs generates default table name"""
        attrs = {}

        meta_attrs = ModelMeta._create_meta_attrs(attrs, "UserProfile")

        assert meta_attrs["table_name"] == "userprofiles"

    def test_create_meta_attrs_preserves_existing_table_name(self):
        """Test _create_meta_attrs preserves explicit table_name"""

        class TestMeta:
            table_name = "users"

        attrs = {"Meta": TestMeta}

        meta_attrs = ModelMeta._create_meta_attrs(attrs, "UserModel")

        # Should keep explicit table_name, not generate default
        assert meta_attrs["table_name"] == "users"

    def test_add_model_exception(self):
        """Test _add_model_exception adds DoesNotExist class"""

        class TestModel:
            pass

        ModelMeta._add_model_exception(TestModel)

        # Should have DoesNotExist attribute
        assert hasattr(TestModel, "DoesNotExist")
        assert issubclass(TestModel.DoesNotExist, DoesNotExistError)

        # Should be able to instantiate and raise
        exception = TestModel.DoesNotExist("Test error")
        assert "Test error" in str(exception)  # DoesNotExistError may modify message
        assert isinstance(exception, DoesNotExistError)


class TestModelMetaIntegration:
    """Integration tests for the complete ModelMeta functionality"""

    def test_complete_model_creation(self):
        """Test that ModelMeta creates a complete model class"""

        class TestModel(Model):
            name = StringField(max_length=100)
            age = IntegerField()

            class Meta:
                table_name = "test_models"

        # Should have all expected attributes
        assert hasattr(TestModel, "_fields")
        assert hasattr(TestModel, "_meta")
        assert hasattr(TestModel, "objects")
        assert hasattr(TestModel, "DoesNotExist")

        # Fields should be properly set up
        assert "id" in TestModel._fields
        assert "name" in TestModel._fields
        assert "age" in TestModel._fields

        # Meta should be set up
        assert TestModel._meta.table_name == "test_models"

        # Manager should be set up
        assert TestModel.objects is not None
        assert TestModel.objects.model_class is TestModel

    def test_model_without_explicit_meta(self):
        """Test model creation without explicit Meta class"""

        class SimpleModel(Model):
            title = StringField(max_length=50)

        # Should have default table name
        assert SimpleModel._meta.table_name == "simplemodels"

        # Should still have all required attributes
        assert hasattr(SimpleModel, "_fields")
        assert hasattr(SimpleModel, "_meta")
        assert hasattr(SimpleModel, "objects")
        assert hasattr(SimpleModel, "DoesNotExist")

    def test_model_with_custom_primary_key(self):
        """Test model creation with custom primary key"""

        class CustomPKModel(Model):
            slug = StringField(primary_key=True, max_length=50)
            content = StringField(max_length=1000)

        # Should not have auto ID field
        assert "id" not in CustomPKModel._fields
        assert "slug" in CustomPKModel._fields
        assert CustomPKModel._fields["slug"].primary_key is True

    def test_multiple_models_independent(self):
        """Test that multiple models don't interfere with each other"""

        class ModelA(Model):
            name = StringField(max_length=100)

        class ModelB(Model):
            title = StringField(max_length=200)

            class Meta:
                table_name = "custom_b"

        # Each should have its own fields and meta
        assert set(ModelA._fields.keys()) == {"id", "name"}
        assert set(ModelB._fields.keys()) == {"id", "title"}

        assert ModelA._meta.table_name == "modelas"
        assert ModelB._meta.table_name == "custom_b"

        # Each should have its own DoesNotExist class
        assert ModelA.DoesNotExist != ModelB.DoesNotExist
        assert issubclass(ModelA.DoesNotExist, DoesNotExistError)
        assert issubclass(ModelB.DoesNotExist, DoesNotExistError)


class TestModelMetaErrorHandling:
    """Test error handling in ModelMeta"""

    def test_extract_fields_handles_non_field_attributes(self):
        """Test that _extract_fields ignores non-Field attributes"""
        attrs = {
            "name": StringField(max_length=100),
            "some_method": lambda self: None,
            "some_value": 42,
            "another_field": StringField(max_length=50),
        }

        fields = ModelMeta._extract_fields(attrs)

        # Should only include Field instances
        field_names = set(fields.keys())
        expected_names = {"id", "name", "another_field"}  # id is auto-added
        assert field_names == expected_names

    def test_create_meta_attrs_handles_empty_meta(self):
        """Test _create_meta_attrs works with empty Meta class"""

        class EmptyMeta:
            pass

        attrs = {"Meta": EmptyMeta}

        meta_attrs = ModelMeta._create_meta_attrs(attrs, "TestModel")

        # Should still have default table_name
        assert "table_name" in meta_attrs
        assert meta_attrs["table_name"] == "testmodels"

    def test_create_meta_attrs_ignores_private_attributes(self):
        """Test _create_meta_attrs ignores private attributes in Meta"""

        class MetaWithPrivate:
            table_name = "public_table"
            _private_attr = "should be ignored"
            __dunder_attr = "also ignored"

        attrs = {"Meta": MetaWithPrivate}

        meta_attrs = ModelMeta._create_meta_attrs(attrs, "TestModel")

        assert "table_name" in meta_attrs
        assert "_private_attr" not in meta_attrs
        assert "__dunder_attr" not in meta_attrs
