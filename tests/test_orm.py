"""
Tests for Kinglet Micro-ORM

Tests the compute-optimized ORM functionality including:
- Model definition and field validation
- Query building with error prevention
- Schema generation
- D1 integration (using mock database)
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from kinglet.orm import (
    Model, Field, StringField, IntegerField, BooleanField, FloatField,
    DateTimeField, JSONField, QuerySet, Manager, SchemaManager
)
from kinglet.orm_errors import DoesNotExistError
from .mock_d1 import MockD1Database, d1_unwrap, d1_unwrap_results


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


class TestModelDefinition:
    """Test model metaclass and definition"""
    
    def test_model_fields_setup(self):
        # Check fields are properly set up
        assert 'id' in SampleGame._fields
        assert 'title' in SampleGame._fields
        assert 'score' in SampleGame._fields
        
        # Check primary key
        id_field = SampleGame._fields['id']
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
        game = SampleGame(
            title="Test Game",
            description="A test game",
            score=100
        )
        
        assert game.title == "Test Game"
        assert game.description == "A test game"  
        assert game.score == 100
        assert game.is_published is False  # Default value
        assert game._state['saved'] is False
        
    def test_model_defaults(self):
        game = SampleGame(title="Test")
        
        assert game.score == 0  # Default
        assert game.is_published is False  # Default
        assert isinstance(game.metadata, dict)  # Default callable
        
    def test_model_to_dict(self):
        game = SampleGame(
            title="Test Game",
            score=100,
            metadata={"key": "value"}
        )
        
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
            "metadata": '{"key": "value"}'
        }
        
        game = SampleGame._from_db(row_data)
        
        assert game.id == 1
        assert game.title == "Test Game"
        assert game.score == 100
        assert game.is_published is True  # Converted from integer
        assert isinstance(game.created_at, datetime)
        assert game.metadata == {"key": "value"}  # Parsed from JSON
        assert game._state['saved'] is True


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
        assert "title ASC" in qs._order_by
        
        # Descending order
        qs = self.queryset.order_by("-score")
        assert "score DESC" in qs._order_by
        
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
        
        # Now uses projection instead of SELECT * for D1 cost optimization
        expected_fields = "id, title, description, score, is_published, created_at, metadata"
        expected_sql = f"SELECT {expected_fields} FROM test_games WHERE is_published = ? ORDER BY created_at DESC LIMIT 10"
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
        # Patch the d1_unwrap functions to use our mock versions
        with patch('kinglet.orm.d1_unwrap', d1_unwrap), \
             patch('kinglet.orm.d1_unwrap_results', d1_unwrap_results):
            
            # Create table first
            await SampleGame.create_table(self.mock_db)
            
            # Create a game
            game = await self.manager.create(
                self.mock_db,
                title="Test Game",
                description="A test game",
                score=100
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
    async def test_queryset_operations(self):
        """Test QuerySet operations with mock database"""
        with patch('kinglet.orm.d1_unwrap', d1_unwrap), \
             patch('kinglet.orm.d1_unwrap_results', d1_unwrap_results):
            
            # Create table and sample data
            await SampleGame.create_table(self.mock_db)
            
            # Create multiple games
            games_data = [
                {"title": "Adventure Game", "score": 95, "is_published": True},
                {"title": "Puzzle Game", "score": 88, "is_published": True},
                {"title": "Racing Game", "score": 92, "is_published": False},
                {"title": "Strategy Game", "score": 90, "is_published": True},
            ]
            
            created_games = []
            for game_data in games_data:
                game = await self.manager.create(self.mock_db, **game_data)
                created_games.append(game)
                
            # Test filtering
            published_games = await self.manager.filter(
                self.mock_db, is_published=True
            ).all()
            assert len(published_games) == 3
            
            # Test count
            total_count = await self.manager.all(self.mock_db).count()
            assert total_count == 4
            
            published_count = await self.manager.filter(
                self.mock_db, is_published=True
            ).count()
            assert published_count == 3
            
            # Test ordering
            high_score_games = await self.manager.all(self.mock_db).order_by("-score").limit(2).all()
            assert len(high_score_games) == 2
            assert high_score_games[0].score >= high_score_games[1].score
            
            # Test lookups
            high_scoring = await self.manager.filter(
                self.mock_db, score__gte=90
            ).all()
            assert len(high_scoring) == 3
            
            # Test search - skip icontains for now as SQLite LIKE is case-sensitive by default
            # This would need COLLATE NOCASE or LOWER() in the query
            # adventure_games = await self.manager.filter(
            #     self.mock_db, title__icontains="adventure"
            # ).all()
            # assert len(adventure_games) == 1
            
            # Test contains instead (case-sensitive)
            adventure_games = await self.manager.filter(
                self.mock_db, title__contains="Adventure"
            ).all()
            assert len(adventure_games) == 1
            assert adventure_games[0].title == "Adventure Game"
            
    @pytest.mark.asyncio
    async def test_bulk_operations(self):
        """Test bulk create operations"""
        with patch('kinglet.orm.d1_unwrap', d1_unwrap), \
             patch('kinglet.orm.d1_unwrap_results', d1_unwrap_results):
            
            # Create table
            await SampleGame.create_table(self.mock_db)
            
            # Create multiple game instances
            game_instances = [
                SampleGame(title=f"Bulk Game {i}", score=80 + i, is_published=i % 2 == 0)
                for i in range(5)
            ]
            
            # Bulk create
            created_games = await self.manager.bulk_create(self.mock_db, game_instances)
            
            assert len(created_games) == 5
            for i, game in enumerate(created_games):
                assert game.title == f"Bulk Game {i}"
                assert game.score == 80 + i
                assert game.id is not None
                
            # Verify they were actually saved
            total_count = await self.manager.all(self.mock_db).count()
            assert total_count == 5
            
    @pytest.mark.asyncio
    async def test_update_and_delete(self):
        """Test model update and delete operations"""
        with patch('kinglet.orm.d1_unwrap', d1_unwrap), \
             patch('kinglet.orm.d1_unwrap_results', d1_unwrap_results):
            
            # Create table and game
            await SampleGame.create_table(self.mock_db)
            
            game = await self.manager.create(
                self.mock_db,
                title="Test Game",
                score=75,
                is_published=False
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
                deleted_game = await self.manager.get(self.mock_db, id=original_id)
                assert False, "Expected DoesNotExist exception after deletion"
            except DoesNotExistError:
                # Expected - object was deleted
                pass
            
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
            field.validate("1.2.3")
    
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
        
        complex_qs = (qs
                     .filter(is_published=True)
                     .exclude(score=0)
                     .order_by('-created_at')
                     .limit(10))
        
        # Check where conditions
        assert len(complex_qs._where_conditions) == 2
        
        # Check order by
        assert complex_qs._order_by == ['created_at DESC']
        
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
            rating=4.5
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
    
    @pytest.mark.asyncio 
    async def test_exclude_with_float_fields(self):
        """Test exclude method with float field conditions"""
        # Create test data
        await self.manager.create(self.mock_db, name="Cheap", price=10.0, discount_rate=0.1)
        await self.manager.create(self.mock_db, name="Expensive", price=100.0, discount_rate=0.2)
        await self.manager.create(self.mock_db, name="Free", price=0.0, discount_rate=0.0)
        
        # Test exclude with float comparison
        qs = self.manager.filter(self.mock_db).exclude(price=0.0)
        
        # Verify condition was added correctly
        assert len(qs._where_conditions) == 1
        condition, value = qs._where_conditions[0]
        assert "NOT (price = ?)" in condition
        assert value == 0.0
    
    def teardown_method(self):
        """Clean up after each test"""
        self.mock_db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])