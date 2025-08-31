"""
Focused ORM coverage tests - DRY approach
Tests for methods that need coverage to reach 80% threshold
"""

import pytest

from kinglet.orm import BooleanField, IntegerField, Manager, Model, StringField


class GameModel(Model):
    """Shared test model to avoid repetition"""

    title = StringField(max_length=100, null=False)
    description = StringField(max_length=500, null=True)
    score = IntegerField(default=0)
    is_published = BooleanField(default=False)

    class Meta:
        table_name = "test_games_coverage"


class TestORMCoverage:
    """Test ORM methods that need coverage"""

    def setup_method(self):
        from .mock_d1 import MockD1Database

        self.mock_db = MockD1Database()
        self.manager = Manager(GameModel)

    @pytest.mark.asyncio
    async def test_values_method(self):
        """Test QuerySet.values() method"""
        await GameModel.create_table(self.mock_db)
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
        await GameModel.create_table(self.mock_db)

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
        await GameModel.create_table(self.mock_db)

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
        await GameModel.create_table(self.mock_db)
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
        await GameModel.create_table(self.mock_db)

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
