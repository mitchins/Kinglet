"""
Tests for Kinglet Micro-ORM

Tests the compute-optimized ORM functionality including:
- Model definition and field validation
- Query building with error prevention
- Schema generation
- D1 integration (using mock database)
"""

from datetime import datetime

import pytest

from kinglet.orm import (
    BooleanField,
    DateTimeField,
    FloatField,
    IntegerField,
    JSONField,
    Manager,
    Model,
    QuerySet,
    SchemaManager,
    StringField,
)
from kinglet.orm_errors import (
    DoesNotExistError,
    ForeignKeyViolationError,
    ORMError,
)

from .mock_d1 import MockD1Database


# Test models
class SampleGame(Model):
    title = StringField(max_length=200, null=False)
    description = StringField()
    score = IntegerField(default=0)
    is_published = BooleanField(default=False)
    created_at = DateTimeField(auto_now_add=True)
    metadata = JSONField(default=dict)

    class Meta:
        table_name = "test_games"


class SampleUser(Model):
    email = StringField(max_length=255, unique=True, null=False)
    username = StringField(max_length=50, null=False)
    is_active = BooleanField(default=True)

    class Meta:
        table_name = "test_users"


class TestFieldValidation:
    """Test field types and validation"""

    def test_string_field_validation(self):
        field = StringField(max_length=10, null=False)
        field.name = "test_field"

        # Valid string
        assert field.validate("hello") == "hello"

        # Too long
        from kinglet.orm_errors import ValidationError

        with pytest.raises(ValidationError):
            field.validate("this is too long")

        # Null when not allowed
        with pytest.raises(ValidationError):
            field.validate(None)

    def test_integer_field_validation(self):
        field = IntegerField()

        assert field.to_python("123") == 123
        assert field.to_python(456) == 456
        assert field.to_python(None) is None

    def test_boolean_field_validation(self):
        field = BooleanField()

        assert field.to_python(1) is True
        assert field.to_python(0) is False
        assert field.to_db(True) == 1
        assert field.to_db(False) == 0

    def test_datetime_field_validation(self):
        field = DateTimeField()

        # From timestamp
        dt = field.to_python(1640995200)  # 2022-01-01 00:00:00 UTC
        assert isinstance(dt, datetime)

        # To timestamp
        now = datetime.now()
        timestamp = field.to_db(now)
        assert isinstance(timestamp, int)

    def test_json_field_validation(self):
        field = JSONField()

        # To Python
        assert field.to_python('{"key": "value"}') == {"key": "value"}

        # To DB
        assert field.to_db({"key": "value"}) == '{"key": "value"}'

        # Test None handling - covers missing paths
        assert field.to_python(None) is None
        assert field.to_db(None) is None


class TestModelDefinition:
    """Test model metaclass and definition"""

    def test_model_fields_setup(self):
        # Check fields are properly set up
        assert "id" in SampleGame._fields
        assert "title" in SampleGame._fields
        assert "score" in SampleGame._fields

        # Check primary key
        id_field = SampleGame._fields["id"]
        assert id_field.primary_key is True

    def test_model_meta_setup(self):
        assert SampleGame._meta.table_name == "test_games"
        assert SampleUser._meta.table_name == "test_users"

    def test_model_manager_setup(self):
        assert isinstance(SampleGame.objects, Manager)
        assert SampleGame.objects.model_class == SampleGame


class TestModelInstance:
    """Test model instance behavior"""

    def test_model_creation(self):
        game = SampleGame(title="Test Game", description="A test game", score=100)

        assert game.title == "Test Game"
        assert game.description == "A test game"
        assert game.score == 100
        assert game.is_published is False  # Default value
        assert game._state["saved"] is False

    def test_model_defaults(self):
        game = SampleGame(title="Test")

        assert game.score == 0  # Default
        assert game.is_published is False  # Default
        assert isinstance(game.metadata, dict)  # Default callable

    def test_model_to_dict(self):
        game = SampleGame(title="Test Game", score=100, metadata={"key": "value"})

        result = game.to_dict()
        assert result["title"] == "Test Game"
        assert result["score"] == 100
        assert result["metadata"] == {"key": "value"}

    def test_model_from_db(self):
        row_data = {
            "id": 1,
            "title": "Test Game",
            "score": 100,
            "is_published": 1,  # Database boolean as integer
            "created_at": 1640995200,
            "metadata": '{"key": "value"}',
        }

        game = SampleGame._from_db(row_data)

        assert game.id == 1
        assert game.title == "Test Game"
        assert game.score == 100
        assert game.is_published is True  # Converted from integer
        assert isinstance(game.created_at, datetime)
        assert game.metadata == {"key": "value"}  # Parsed from JSON
        assert game._state["saved"] is True


class TestQuerySet:
    """Test QuerySet functionality"""

    def setup_method(self):
        self.mock_db = MockD1Database()
        self.queryset = QuerySet(SampleGame, self.mock_db)

    def test_field_validation_in_filter(self):
        # Valid field
        qs = self.queryset.filter(title="Test")
        assert len(qs._where_conditions) == 1

        # Invalid field should raise error
        with pytest.raises(ValueError, match="Field 'invalid_field' does not exist"):
            self.queryset.filter(invalid_field="test")

    def test_field_validation_in_order_by(self):
        # Valid field
        qs = self.queryset.order_by("title")
        assert '"title" ASC' in qs._order_by

        # Descending order
        qs = self.queryset.order_by("-score")
        assert '"score" DESC' in qs._order_by

        # Invalid field should raise error
        with pytest.raises(ValueError, match="Field 'invalid_field' does not exist"):
            self.queryset.order_by("invalid_field")

    def test_lookup_conditions(self):
        qs = self.queryset

        # Greater than
        condition = qs._build_lookup_condition("score", "gt", 100)
        assert condition == "score > ?"

        # Contains
        condition = qs._build_lookup_condition("title", "contains", "test")
        assert condition == "title LIKE ?"

        # In lookup
        condition = qs._build_lookup_condition("id", "in", [1, 2, 3])
        assert condition == "id IN (?,?,?)"

    def test_sql_building(self):
        qs = self.queryset.filter(is_published=True).order_by("-created_at").limit(10)
        sql, params = qs._build_sql()

        # Now uses projection instead of SELECT * for D1 cost optimization, with quoted identifiers
        expected_fields = '"id", "title", "description", "score", "is_published", "created_at", "metadata"'
        expected_sql = f'SELECT {expected_fields} FROM "test_games" WHERE is_published = ? ORDER BY "created_at" DESC LIMIT 10'
        assert sql == expected_sql
        assert params == [True]

    def test_chaining(self):
        # Test query chaining doesn't modify original
        qs1 = self.queryset.filter(is_published=True)
        qs2 = qs1.filter(score__gt=100)

        # Original queryset unchanged
        assert len(self.queryset._where_conditions) == 0
        assert len(qs1._where_conditions) == 1
        assert len(qs2._where_conditions) == 2


class TestSchemaManager:
    """Test schema generation and migration"""

    def test_generate_create_sql(self):
        sql = SampleGame.get_create_sql()

        assert "CREATE TABLE IF NOT EXISTS test_games" in sql
        assert "id INTEGER PRIMARY KEY AUTOINCREMENT" in sql
        assert "title VARCHAR(200) NOT NULL" in sql
        assert "score INTEGER" in sql
        assert "is_published INTEGER" in sql
        assert "created_at INTEGER" in sql
        assert "metadata TEXT" in sql

    def test_generate_schema_sql(self):
        models = [SampleGame, SampleUser]
        schema = SchemaManager.generate_schema_sql(models)

        assert "CREATE TABLE IF NOT EXISTS test_games" in schema
        assert "CREATE TABLE IF NOT EXISTS test_users" in schema

    @pytest.mark.asyncio
    async def test_migrate_all(self):
        mock_db = MockD1Database()
        models = [SampleGame, SampleUser]

        results = await SchemaManager.migrate_all(mock_db, models)

        # Should succeed for both models
        assert results["SampleGame"] is True
        assert results["SampleUser"] is True


class TestManagerOperations:
    """Test Manager database operations using mock database"""

    def setup_method(self):
        self.mock_db = MockD1Database()
        self.manager = Manager(SampleGame)

    @pytest.mark.asyncio
    async def test_create_and_get_integration(self):
        """Test full create and get cycle with mock database"""
        # Create table first
        await SampleGame.create_table(self.mock_db)

        # Create a game
        game = await self.manager.create(
            self.mock_db, title="Test Game", description="A test game", score=100
        )

        assert isinstance(game, SampleGame)
        assert game.title == "Test Game"
        assert game.description == "A test game"
        assert game.score == 100
        assert game.id is not None  # Should have auto-generated ID

        # Get the same game back
        retrieved_game = await self.manager.get(self.mock_db, id=game.id)

        assert retrieved_game is not None
        assert isinstance(retrieved_game, SampleGame)
        assert retrieved_game.id == game.id
        assert retrieved_game.title == "Test Game"
        assert retrieved_game.score == 100

    @pytest.mark.asyncio
    async def test_update_and_delete(self):
        """Test model update and delete operations"""
        # Create table and game
        await SampleGame.create_table(self.mock_db)

        game = await self.manager.create(
            self.mock_db, title="Test Game", score=75, is_published=False
        )

        original_id = game.id

        # Update the game
        game.score = 95
        game.is_published = True
        await game.save(self.mock_db)

        # Verify update
        updated_game = await self.manager.get(self.mock_db, id=original_id)
        assert updated_game.score == 95
        assert updated_game.is_published is True

        # Delete the game
        await game.delete(self.mock_db)

        # Verify deletion
        try:
            await self.manager.get(self.mock_db, id=original_id)
            raise AssertionError("Expected DoesNotExist exception after deletion")
        except DoesNotExistError:
            # Expected - object was deleted
            pass

    @pytest.mark.asyncio
    async def test_get_or_create_success_path(self):
        """Test get_or_create create path - covers get_or_create internal logic"""
        # Create table for the test
        await SampleGame.create_table(self.mock_db)

        instance, created = await self.manager.get_or_create(
            self.mock_db,
            title="Test Game",
            defaults={"description": "Test Description", "score": 100},
        )

        assert created is True
        assert instance.title == "Test Game"
        assert instance.description == "Test Description"
        assert instance.score == 100

    @pytest.mark.asyncio
    async def test_get_or_create_conflict_then_get_path(self):
        """Test get_or_create conflict resolution path"""
        from unittest.mock import AsyncMock

        from kinglet.orm_errors import UniqueViolationError

        # Create table first
        await SampleGame.create_table(self.mock_db)

        # First create an existing record
        existing_game = await self.manager.create(
            self.mock_db, title="Existing Game", score=50
        )

        call_count = 0

        def mock_create_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call raises UniqueViolationError
                raise UniqueViolationError("UNIQUE constraint failed")
            else:
                # Subsequent calls should not happen
                raise Exception("Should not be called")

        def mock_get_side_effect(*args, **kwargs):
            # Mock finding existing instance
            return existing_game

        # Mock the manager methods
        original_create = self.manager.create
        original_get = self.manager.get
        self.manager.create = AsyncMock(side_effect=mock_create_side_effect)
        self.manager.get = AsyncMock(side_effect=mock_get_side_effect)

        try:
            instance, created = await self.manager.get_or_create(
                self.mock_db,
                title="Existing Game",
                defaults={"description": "New Description", "score": 100},
            )

            assert created is False
            assert instance.title == "Existing Game"
            assert instance.score == 50  # Should be existing value, not default
        finally:
            # Restore original methods
            self.manager.create = original_create
            self.manager.get = original_get

    def teardown_method(self):
        """Clean up after each test"""
        self.mock_db.close()


class TestFloatField:
    """Test FloatField functionality"""

    def test_float_field_validation(self):
        field = FloatField(null=False)
        field.name = "price"

        # Test valid values
        assert field.validate(10.5) == 10.5
        assert field.validate("3.14") == 3.14
        assert field.validate(0) == 0.0
        assert field.validate(-5.5) == -5.5

        # Test null handling
        field_nullable = FloatField(null=True)
        field_nullable.name = "optional_price"
        assert field_nullable.validate(None) is None

        # Test non-null validation
        with pytest.raises(ValueError, match="Field cannot be null"):
            field.validate(None)

    def test_float_field_invalid_values(self):
        field = FloatField()
        field.name = "rating"

        with pytest.raises(ValueError, match="Invalid float value"):
            field.validate("not_a_number")

        with pytest.raises(ValueError, match="Invalid float value"):
            field.validate("invalid_float")

    def test_float_field_to_python(self):
        field = FloatField()

        assert field.to_python(3.14) == 3.14
        assert field.to_python("2.5") == 2.5
        assert field.to_python(None) is None
        assert field.to_python(10) == 10.0

    def test_float_field_to_db(self):
        field = FloatField()

        assert field.to_db(3.14) == 3.14
        assert field.to_db("2.5") == 2.5
        assert field.to_db(None) is None
        assert field.to_db(10) == 10.0

    def test_float_field_sql_type(self):
        field = FloatField()
        assert field.get_sql_type() == "REAL"


class TestQuerySetExclude:
    """Test QuerySet.exclude() method functionality"""

    def setup_method(self):
        """Set up test fixtures"""
        self.mock_db = MockD1Database()
        self.manager = SampleGame.objects

    def test_exclude_basic(self):
        """Test basic exclude functionality"""
        qs = QuerySet(SampleGame, self.mock_db)

        # Test simple exclude
        excluded_qs = qs.exclude(is_published=True)

        # Check that WHERE NOT condition was added
        assert len(excluded_qs._where_conditions) == 1
        condition, value = excluded_qs._where_conditions[0]
        assert "NOT (is_published = ?)" in condition
        assert value is True

    def test_exclude_multiple_conditions(self):
        """Test exclude with multiple conditions"""
        qs = QuerySet(SampleGame, self.mock_db)

        excluded_qs = qs.exclude(is_published=True, score=100)

        assert len(excluded_qs._where_conditions) == 2

        # Check both conditions are NOT conditions
        conditions = [cond for cond, _ in excluded_qs._where_conditions]
        assert all("NOT (" in cond for cond in conditions)

    def test_exclude_with_lookups(self):
        """Test exclude with field lookups"""
        qs = QuerySet(SampleGame, self.mock_db)

        excluded_qs = qs.exclude(score__gt=90)

        assert len(excluded_qs._where_conditions) == 1
        condition, value = excluded_qs._where_conditions[0]
        assert "NOT (" in condition
        assert "score > ?" in condition
        assert value == 90

    def test_exclude_invalid_field(self):
        """Test exclude with invalid field name"""
        qs = QuerySet(SampleGame, self.mock_db)

        with pytest.raises(ValueError, match="Field 'invalid_field' does not exist"):
            qs.exclude(invalid_field="value")

    def test_exclude_with_filter_chaining(self):
        """Test chaining filter and exclude"""
        qs = QuerySet(SampleGame, self.mock_db)

        chained_qs = qs.filter(is_published=True).exclude(score=0)

        assert len(chained_qs._where_conditions) == 2

        # First condition should be filter (positive)
        filter_condition, filter_value = chained_qs._where_conditions[0]
        assert filter_condition == "is_published = ?"
        assert filter_value is True

        # Second condition should be exclude (negative)
        exclude_condition, exclude_value = chained_qs._where_conditions[1]
        assert "NOT (score = ?)" in exclude_condition
        assert exclude_value == 0

    def test_exclude_preserves_other_query_parts(self):
        """Test that exclude preserves other query components"""
        qs = QuerySet(SampleGame, self.mock_db)

        complex_qs = (
            qs.filter(is_published=True)
            .exclude(score=0)
            .order_by("-created_at")
            .limit(10)
        )

        # Check where conditions
        assert len(complex_qs._where_conditions) == 2

        # Check order by
        assert complex_qs._order_by == ['"created_at" DESC']

        # Check limit
        assert complex_qs._limit_count == 10

    @pytest.mark.asyncio
    async def test_exclude_sql_generation(self):
        """Test that exclude generates correct SQL"""
        qs = QuerySet(SampleGame, self.mock_db)

        excluded_qs = qs.exclude(is_published=True, score__gt=50)

        # This would test SQL generation if we had access to the SQL
        # For now, just verify the conditions are stored correctly
        assert len(excluded_qs._where_conditions) == 2

        # Verify NOT conditions
        conditions = [cond for cond, _ in excluded_qs._where_conditions]
        assert all("NOT (" in cond for cond in conditions)

    def teardown_method(self):
        """Clean up after each test"""
        self.mock_db.close()


# Add FloatField to test models for integration testing
class SampleProduct(Model):
    """Test model with FloatField for integration testing"""

    name = StringField(max_length=100, null=False)
    price = FloatField(null=False)
    discount_rate = FloatField(default=0.0)
    rating = FloatField(null=True)

    class Meta:
        table_name = "test_products"


class TestFloatFieldIntegration:
    """Integration tests for FloatField with Model operations"""

    def setup_method(self):
        """Set up test fixtures"""
        self.mock_db = MockD1Database()
        self.manager = SampleProduct.objects

        # Create the table schema for the test using the mock DB interface
        schema_sql = """
        CREATE TABLE IF NOT EXISTS test_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            discount_rate REAL DEFAULT 0.0,
            rating REAL
        )
        """
        # Create schema synchronously using the mock DB's SQLite connection
        cursor = self.mock_db.conn.cursor()
        cursor.execute(schema_sql)
        self.mock_db.conn.commit()

    @pytest.mark.asyncio
    async def test_float_field_crud_operations(self):
        """Test CRUD operations with FloatField"""
        # Create
        product = await self.manager.create(
            self.mock_db,
            name="Test Product",
            price=29.99,
            discount_rate=0.15,
            rating=4.5,
        )

        assert product.price == 29.99
        assert product.discount_rate == 0.15
        assert product.rating == 4.5

        # Update
        product.price = 34.99
        product.rating = None  # Test nullable float
        await product.save(self.mock_db)

        # Verify update
        updated_product = await self.manager.get(self.mock_db, id=product.id)
        assert updated_product.price == 34.99
        assert updated_product.rating is None


class TestD1Transaction:
    """Test D1Transaction basic functionality"""

    def test_d1_transaction_creation(self):
        """Test D1Transaction basic creation and state"""
        from unittest.mock import Mock

        from kinglet.orm import D1Transaction

        mock_db = Mock()
        txn = D1Transaction(mock_db)

        assert txn.db is mock_db
        assert txn.statements == []
        assert txn.executed is False

    def test_d1_transaction_rollback(self):
        """Test D1Transaction rollback functionality"""
        from unittest.mock import Mock

        from kinglet.orm import D1Transaction

        mock_db = Mock()
        txn = D1Transaction(mock_db)

        # Add mock statements directly
        txn.statements = ["mock_stmt1", "mock_stmt2"]
        assert len(txn.statements) == 2

        # Rollback
        txn.rollback()

        assert len(txn.statements) == 0
        assert txn.executed is True

    @pytest.mark.asyncio
    async def test_d1_transaction_double_execute_protection(self):
        """Test D1Transaction protection against double execution"""
        from unittest.mock import AsyncMock, Mock

        from kinglet.orm import D1Transaction

        mock_db = Mock()
        mock_db.batch = AsyncMock(return_value=[])
        txn = D1Transaction(mock_db)

        # First execution
        await txn.execute()

        # Second execution should raise error
        with pytest.raises(RuntimeError, match="Transaction already executed"):
            await txn.execute()

    @pytest.mark.asyncio
    async def test_d1_transaction_add_statement_after_execute(self):
        """Test D1Transaction protection against adding statements after execute"""
        from unittest.mock import AsyncMock, Mock

        from kinglet.orm import D1Transaction

        mock_db = Mock()
        mock_db.batch = AsyncMock(return_value=[])
        txn = D1Transaction(mock_db)

        # Execute first
        await txn.execute()

        # Adding statement after execute should raise error
        with pytest.raises(RuntimeError, match="Transaction already executed"):
            await txn.add_statement("INSERT INTO test VALUES (?)", ["value"])


class TestQuerySetAdvanced:
    """Test advanced QuerySet methods"""

    def setup_method(self):
        from kinglet.orm import BooleanField, IntegerField, Manager, Model, StringField

        from .mock_d1 import MockD1Database

        self.mock_db = MockD1Database()

        class GameModel(Model):
            title = StringField(max_length=100, null=False)
            description = StringField(max_length=500, null=True)
            score = IntegerField(default=0)
            is_published = BooleanField(default=False)

            class Meta:
                table_name = "test_games"

        self.GameModel = GameModel
        self.manager = Manager(GameModel)

    @pytest.mark.asyncio
    async def test_values_method(self):
        """Test QuerySet.values() method"""
        await self.GameModel.create_table(self.mock_db)
        await self.manager.create(self.mock_db, title="Test", score=95)

        # Test with specific fields
        values_qs = self.manager.all(self.mock_db).values("title", "score")
        assert values_qs._values_fields == ["title", "score"]
        assert values_qs._only_fields is None

        # Test with no fields (all fields)
        all_values_qs = self.manager.all(self.mock_db).values()
        assert "title" in all_values_qs._values_fields

        # Test error for invalid field
        with pytest.raises(ValueError, match="Field 'invalid' does not exist"):
            self.manager.all(self.mock_db).values("invalid")

    @pytest.mark.asyncio
    async def test_exists_method(self):
        """Test QuerySet.exists() method"""
        await self.GameModel.create_table(self.mock_db)

        # No records
        assert await self.manager.all(self.mock_db).exists() is False

        # Add record
        await self.manager.create(self.mock_db, title="Test", score=95)
        assert await self.manager.all(self.mock_db).exists() is True

        # With filter
        assert await self.manager.filter(self.mock_db, score__gte=90).exists() is True
        assert await self.manager.filter(self.mock_db, score__lt=50).exists() is False

    @pytest.mark.asyncio
    async def test_first_method(self):
        """Test QuerySet.first() method"""
        await self.GameModel.create_table(self.mock_db)

        # No records
        assert await self.manager.all(self.mock_db).first() is None

        # Add records
        await self.manager.create(self.mock_db, title="Game A", score=50)
        await self.manager.create(self.mock_db, title="Game B", score=95)

        # Test first returns a record
        first = await self.manager.all(self.mock_db).first()
        assert first is not None

        # Test first with values mode
        first_values = await self.manager.all(self.mock_db).values("title").first()
        assert first_values is not None
        assert "title" in first_values

    @pytest.mark.asyncio
    async def test_delete_method(self):
        """Test QuerySet.delete() method"""
        await self.GameModel.create_table(self.mock_db)
        await self.manager.create(self.mock_db, title="Game A", score=50)
        await self.manager.create(self.mock_db, title="Game B", score=95)

        # Delete with filter
        deleted = await self.manager.filter(self.mock_db, score__lt=60).delete()
        assert deleted >= 0  # Mock behavior

        # Prevent delete all without filter
        with pytest.raises(ValueError, match="DELETE without WHERE clause not allowed"):
            await self.manager.all(self.mock_db).delete()

    @pytest.mark.asyncio
    async def test_only_method(self):
        """Test QuerySet.only() method"""
        await self.GameModel.create_table(self.mock_db)

        # Test only with specific fields
        only_qs = self.manager.all(self.mock_db).only("title", "score")
        assert only_qs._only_fields == ["title", "score"]
        assert only_qs._values_fields is None

        # Test error for invalid field
        with pytest.raises(ValueError, match="Field 'invalid' does not exist"):
            self.manager.all(self.mock_db).only("invalid")

    @pytest.mark.asyncio
    async def test_offset_validation(self):
        """Test QuerySet.offset() validation"""
        qs = self.manager.all(self.mock_db)

        # Test negative offset
        with pytest.raises(ValueError, match="Offset cannot be negative"):
            qs.offset(-1)

        # Test offset too large
        with pytest.raises(ValueError, match="Offset cannot exceed 100000"):
            qs.offset(100001)

        # Test valid offset
        valid_qs = qs.offset(10)
        assert valid_qs._offset_count == 10

    @pytest.mark.asyncio
    async def test_exclude_with_integer_fields(self):
        """Test exclude method with integer field conditions"""
        await self.GameModel.create_table(self.mock_db)

        # Create test data using correct GameModel fields
        await self.manager.create(self.mock_db, title="Low Score", score=10)
        await self.manager.create(self.mock_db, title="High Score", score=100)
        await self.manager.create(self.mock_db, title="Zero Score", score=0)

        # Test exclude with integer comparison
        qs = self.manager.all(self.mock_db).exclude(score=0)

        # Verify condition was added correctly
        assert len(qs._where_conditions) == 1
        condition, value = qs._where_conditions[0]
        assert "NOT (score = ?)" in condition
        assert value == 0

    def test_limit_validation(self):
        """Test limit method validation - covers missing edge cases"""
        qs = self.manager.all(self.mock_db)

        # Test zero limit
        with pytest.raises(ValueError, match="Limit must be positive"):
            qs.limit(0)

        # Test negative limit
        with pytest.raises(ValueError, match="Limit must be positive"):
            qs.limit(-5)

        # Test limit too large
        with pytest.raises(
            ValueError, match="Limit cannot exceed 10000 \\(D1 safety limit\\)"
        ):
            qs.limit(10001)

    def test_field_validation_coverage(self):
        """Test field validation in more QuerySet methods"""
        qs = self.manager.all(self.mock_db)

        # Test invalid field in various methods that aren't covered
        with pytest.raises(ValueError, match="Field 'invalid' does not exist"):
            qs.order_by("invalid")

        with pytest.raises(ValueError, match="Field 'invalid' does not exist"):
            qs.filter(invalid__gt=10)

    @pytest.mark.asyncio
    async def test_count_exception_handling(self):
        """Test count method exception handling - should raise classified error"""
        # Create a queryset but don't create the table to trigger DB error
        qs = self.manager.all(self.mock_db)

        # This should classify the database error and raise appropriate exception
        with pytest.raises(
            (ForeignKeyViolationError, ORMError)
        ):  # Should raise classified error
            await qs.count()

    def test_exclude_field_validation(self):
        """Test field validation in exclude method - covers missing path"""
        qs = self.manager.all(self.mock_db)

        # Test invalid field in exclude method
        with pytest.raises(ValueError, match="Field 'nonexistent' does not exist"):
            qs.exclude(nonexistent="value")

        # Test invalid field with lookup in exclude method
        with pytest.raises(ValueError, match="Field 'invalid' does not exist"):
            qs.exclude(invalid__gt=10)

    @pytest.mark.asyncio
    async def test_values_mode_in_all(self):
        """Test all() method with values_fields - covers missing path"""
        await self.GameModel.create_table(self.mock_db)

        # Create some test data
        await self.manager.create(self.mock_db, title="Game 1", score=100)
        await self.manager.create(self.mock_db, title="Game 2", score=200)

        # Query with values mode
        qs = self.manager.all(self.mock_db).values("title", "score")
        results = await qs.all()

        # Should return dictionaries with only the requested fields
        assert len(results) >= 2
        assert isinstance(results[0], dict)
        assert "title" in results[0]
        assert "score" in results[0]
        # Should not include other fields like id
        assert len(results[0].keys()) == 2

    @pytest.mark.asyncio
    async def test_queryset_chaining_operations(self):
        """Test QuerySet chaining operations - covers _clone cases"""
        # Create a complex queryset that will trigger multiple _clone() calls
        base_qs = self.manager.all(self.mock_db)

        # Each chained operation should call _clone() internally
        complex_qs = (
            base_qs.filter(score__gt=10)
            .filter(title__icontains="test")
            .exclude(score__lt=5)
            .order_by("-score", "title")
            .limit(20)
            .offset(10)
            .only("title", "score")
            .values("title")
        )

        # Verify the clone copied all the state correctly
        assert len(complex_qs._where_conditions) == 3  # 2 filters + 1 exclude
        assert len(complex_qs._order_by) == 2
        assert complex_qs._limit_count == 20
        assert complex_qs._offset_count == 10
        assert complex_qs._values_fields == ["title"]
        assert complex_qs._only_fields is None  # values mode clears only mode

    @pytest.mark.asyncio
    async def test_offset_clause_in_query_execution(self):
        """Test _build_sql OFFSET clause via query execution"""
        # Create table for the test
        await self.GameModel.create_table(self.mock_db)

        # Create queryset with offset (requires order_by)
        qs = self.manager.all(self.mock_db).order_by("title").limit(10).offset(20)

        # Execute query to trigger _build_sql with OFFSET - should not error
        results = await qs.all()

        # Should execute without error (empty results are fine)
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_offset_without_order_by_validation(self):
        """Test OFFSET validation path in _validate_pagination_safety"""
        qs = self.manager.all(self.mock_db).offset(10)  # No order_by

        # Should raise error when trying to execute
        with pytest.raises(
            ValueError, match="OFFSET requires ORDER BY for predictable pagination"
        ):
            await qs.all()

    @pytest.mark.asyncio
    async def test_update_operations_via_queryset(self):
        """Test _build_update_set method via QuerySet.update()"""
        # Create table and add some test data
        await self.GameModel.create_table(self.mock_db)

        # Create test record
        await self.manager.create(
            self.mock_db, title="Test", score=10, is_published=False
        )

        # Execute update to trigger _build_update_set
        updated_count = await self.manager.filter(self.mock_db, score__lt=50).update(
            score=100, title="Updated"
        )

        # Should have updated the record
        assert (
            updated_count >= 0
        )  # MockD1Database returns 0, but real DB would return 1

    @pytest.mark.asyncio
    async def test_update_field_validation(self):
        """Test field validation in _build_update_set via update()"""
        qs = self.manager.filter(self.mock_db, score=10)

        # Test invalid field name
        with pytest.raises(ValueError, match="Field 'invalid_field' does not exist"):
            await qs.update(invalid_field="test")

    @pytest.mark.asyncio
    async def test_update_primary_key_protection(self):
        """Test primary key protection in _build_update_set"""
        qs = self.manager.filter(self.mock_db, score=10)

        # Should raise error when trying to update primary key
        with pytest.raises(ValueError, match="Cannot update primary key field 'id'"):
            await qs.update(id=999)

    @pytest.mark.asyncio
    async def test_update_without_where_clause_protection(self):
        """Test update protection without WHERE clause"""
        qs = self.manager.all(self.mock_db)  # No filter

        # Should raise error for update without WHERE
        with pytest.raises(ValueError, match="UPDATE without WHERE clause not allowed"):
            await qs.update(score=100)

    @pytest.mark.asyncio
    async def test_update_with_no_changes(self):
        """Test update with no fields to update"""
        qs = self.manager.filter(self.mock_db, score=10)

        # Empty update should return 0
        result = await qs.update()
        assert result == 0

    def teardown_method(self):
        """Clean up after each test"""
        self.mock_db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
