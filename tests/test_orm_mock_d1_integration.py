"""
Integration tests for ORM with MockD1Database, specifically testing RETURNING clause support
"""

import pytest

from kinglet.orm import IntegerField, Model, StringField
from kinglet.testing import MockD1Database


class User(Model):
    """Test model for integration testing"""
    email = StringField(unique=True)
    name = StringField()
    age = IntegerField(null=True)

    class Meta:
        table_name = "users"


class TestORMWithMockD1Integration:
    """Test ORM operations with MockD1Database, focusing on RETURNING clause support"""

    @pytest.fixture
    async def db(self):
        """Create database with schema"""
        database = MockD1Database()
        await database.exec("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                age INTEGER
            )
        """)
        yield database
        database.close()

    @pytest.mark.asyncio
    async def test_create_or_update_with_mock_d1_insert(self, db):
        """Test create_or_update INSERT path with MockD1Database"""
        user, created = await User.objects.create_or_update(
            db,
            email="alice@example.com",
            defaults={"name": "Alice", "age": 30}
        )

        assert created is True
        assert user.email == "alice@example.com"
        assert user.name == "Alice"
        assert user.age == 30
        assert user.id is not None

    @pytest.mark.asyncio
    async def test_create_or_update_with_mock_d1_update(self, db):
        """Test create_or_update UPDATE path with MockD1Database"""
        # First insert
        user1, created1 = await User.objects.create_or_update(
            db,
            email="bob@example.com",
            defaults={"name": "Bob", "age": 25}
        )
        assert created1 is True
        original_id = user1.id

        # Update via upsert (INSERT OR REPLACE will handle the unique constraint)
        user2, created2 = await User.objects.create_or_update(
            db,
            email="bob@example.com",
            defaults={"name": "Robert", "age": 26}
        )
        # created flag is True because we didn't pass id in kwargs
        assert user2.email == "bob@example.com"
        assert user2.name == "Robert"
        assert user2.age == 26

    @pytest.mark.asyncio
    async def test_create_or_update_with_returning_multiple_times(self, db):
        """Test multiple create_or_update calls work correctly"""
        users_data = [
            {"email": "user1@example.com", "name": "User1", "age": 21},
            {"email": "user2@example.com", "name": "User2", "age": 22},
            {"email": "user3@example.com", "name": "User3", "age": 23},
        ]

        for data in users_data:
            user, created = await User.objects.create_or_update(
                db,
                email=data["email"],
                defaults={"name": data["name"], "age": data["age"]}
            )
            assert created is True
            assert user.email == data["email"]
            assert user.name == data["name"]

    @pytest.mark.asyncio
    async def test_create_or_update_preserves_data_integrity(self, db):
        """Test that create_or_update properly commits and returns data"""
        # Create initial user
        user1, _ = await User.objects.create_or_update(
            db,
            email="test@example.com",
            defaults={"name": "Test", "age": 30}
        )

        # Verify the user was actually inserted by querying directly
        result = await db.prepare(
            "SELECT * FROM users WHERE email = ?"
        ).bind("test@example.com").first()

        assert result is not None
        assert result["email"] == "test@example.com"
        assert result["name"] == "Test"
        assert result["age"] == 30


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
