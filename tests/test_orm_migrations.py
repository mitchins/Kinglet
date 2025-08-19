"""
Tests for Kinglet ORM Migration System

Tests schema tracking, migration generation, and version management.
"""

import pytest
import json
import tempfile
import os
from datetime import datetime
from unittest.mock import patch, MagicMock

from kinglet.orm import Model, StringField, IntegerField, BooleanField
from kinglet.orm_migrations import (
    Migration, MigrationTracker, SchemaLock, MigrationGenerator
)
from .mock_d1 import MockD1Database

# Import the patching modules
import kinglet.orm_migrations


# Test models
class SampleProduct(Model):
    name = StringField(max_length=100, null=False)
    price = IntegerField(default=0)
    in_stock = BooleanField(default=True)
    
    class Meta:
        table_name = "products"


class SampleOrder(Model):
    product_id = IntegerField(null=False)
    quantity = IntegerField(default=1)
    
    class Meta:
        table_name = "orders"


class TestMigration:
    """Test Migration class"""
    
    def test_migration_creation(self):
        migration = Migration(
            version="2024_01_01_120000",
            sql="ALTER TABLE products ADD COLUMN description TEXT;",
            description="Add description field"
        )
        
        assert migration.version == "2024_01_01_120000"
        assert migration.sql == "ALTER TABLE products ADD COLUMN description TEXT;"
        assert migration.description == "Add description field"
        assert len(migration.checksum) == 16  # SHA256 truncated
        
    def test_migration_checksum(self):
        migration1 = Migration(
            version="v1",
            sql="CREATE TABLE test (id INT);",
            description="Test"
        )
        
        migration2 = Migration(
            version="v1",
            sql="CREATE TABLE test (id INT);",  # Same SQL
            description="Test"
        )
        
        migration3 = Migration(
            version="v1",
            sql="CREATE TABLE other (id INT);",  # Different SQL
            description="Test"
        )
        
        assert migration1.checksum == migration2.checksum
        assert migration1.checksum != migration3.checksum
        
    def test_migration_to_dict(self):
        migration = Migration(
            version="v1",
            sql="CREATE TABLE test (id INT);",
            description="Test migration"
        )
        
        data = migration.to_dict()
        assert data["version"] == "v1"
        assert data["description"] == "Test migration"
        assert "checksum" in data
        assert data["sql_length"] == len("CREATE TABLE test (id INT);")


class TestMigrationTracker:
    """Test MigrationTracker functionality"""
    
    @pytest.mark.asyncio
    async def test_ensure_migrations_table(self):
        db = MockD1Database()
        
        await MigrationTracker.ensure_migrations_table(db)
        
        # Check table was created
        cursor = db.conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='_kinglet_migrations'
        """)
        result = cursor.fetchone()
        assert result is not None
        
    @pytest.mark.asyncio
    async def test_record_and_check_migration(self):
        db = MockD1Database()
        await MigrationTracker.ensure_migrations_table(db)
        
        migration = Migration(
            version="2024_01_01_120000",
            sql="CREATE TABLE test (id INT);",
            description="Initial migration"
        )
        
        # Initially not applied
        assert await MigrationTracker.is_applied(db, migration.version) is False
        
        # Record migration
        await MigrationTracker.record_migration(db, migration)
        
        # Now it should be applied
        assert await MigrationTracker.is_applied(db, migration.version) is True
        
    @pytest.mark.asyncio
    async def test_get_applied_migrations(self):
        with patch('kinglet.orm_migrations.d1_unwrap_results') as mock_unwrap:
            db = MockD1Database()
            await MigrationTracker.ensure_migrations_table(db)
            
            # Apply multiple migrations
            migrations = [
                Migration("v1", "SQL1", "First"),
                Migration("v2", "SQL2", "Second"),
                Migration("v3", "SQL3", "Third"),
            ]
            
            for migration in migrations:
                await MigrationTracker.record_migration(db, migration)
                
            # Mock the unwrap function to return proper format
            mock_unwrap.return_value = [
                {'version': 'v1'}, 
                {'version': 'v2'}, 
                {'version': 'v3'}
            ]
            
            # Get applied migrations
            applied = await MigrationTracker.get_applied_migrations(db)
            
            assert len(applied) == 3
            assert applied == ["v1", "v2", "v3"]
        
    @pytest.mark.asyncio
    async def test_apply_migration(self):
        db = MockD1Database()
        await MigrationTracker.ensure_migrations_table(db)
        
        # Create test table
        migration = Migration(
            version="v1",
            sql="CREATE TABLE test_table (id INTEGER PRIMARY KEY, name TEXT);",
            description="Create test table"
        )
        
        result = await MigrationTracker.apply_migration(db, migration)
        
        assert result["version"] == "v1"
        assert result["status"] == "applied"
        assert "checksum" in result
        
        # Try to apply again - should skip
        result2 = await MigrationTracker.apply_migration(db, migration)
        assert result2["status"] == "skipped"
        assert result2["reason"] == "already applied"
        
    @pytest.mark.asyncio
    async def test_apply_migrations_batch(self):
        db = MockD1Database()
        
        migrations = [
            Migration("v1", "CREATE TABLE t1 (id INT);", "Create t1"),
            Migration("v2", "CREATE TABLE t2 (id INT);", "Create t2"),
            Migration("v3", "CREATE TABLE t3 (id INT);", "Create t3"),
        ]
        
        results = await MigrationTracker.apply_migrations(db, migrations)
        
        assert len(results["applied"]) == 3
        assert len(results["skipped"]) == 0
        assert len(results["failed"]) == 0
        assert results["total"] == 3
        
        # Apply again - should all be skipped
        results2 = await MigrationTracker.apply_migrations(db, migrations)
        assert len(results2["applied"]) == 0
        assert len(results2["skipped"]) == 3
        
    @pytest.mark.asyncio
    async def test_get_schema_version(self):
        with patch('kinglet.orm_migrations.d1_unwrap') as mock_unwrap:
            db = MockD1Database()
            await MigrationTracker.ensure_migrations_table(db)
            
            # No migrations yet
            mock_unwrap.return_value = None
            version = await MigrationTracker.get_schema_version(db)
            assert version is None
            
            # Apply migrations
            await MigrationTracker.record_migration(db, Migration("v1", "SQL", ""))
            await MigrationTracker.record_migration(db, Migration("v2", "SQL", ""))
            
            # Mock returning latest version
            mock_unwrap.return_value = {'version': 'v2', 'applied_at': 1234567890}
            
            # Should return latest
            version = await MigrationTracker.get_schema_version(db)
            assert version == "v2"
        
    @pytest.mark.asyncio
    async def test_get_migration_status(self):
        db = MockD1Database()
        
        # Get status with no migrations
        status = await MigrationTracker.get_migration_status(db)
        assert status["current_version"] is None
        assert status["migrations_count"] == 0
        assert status["healthy"] is True
        
        # Apply some migrations
        await MigrationTracker.ensure_migrations_table(db)
        await MigrationTracker.record_migration(db, Migration("v1", "SQL", "First"))
        await MigrationTracker.record_migration(db, Migration("v2", "SQL", "Second"))
        
        # Get status again
        status = await MigrationTracker.get_migration_status(db)
        assert status["current_version"] == "v2"
        assert status["migrations_count"] == 2
        assert len(status["migrations"]) == 2
        assert status["healthy"] is True


class TestSchemaLock:
    """Test SchemaLock functionality"""
    
    def test_generate_lock(self):
        models = [SampleProduct, SampleOrder]
        lock_data = SchemaLock.generate_lock(models)
        
        assert lock_data["version"] == "1.0.0"
        assert "generated_at" in lock_data
        assert len(lock_data["models"]) == 2
        assert "SampleProduct" in lock_data["models"]
        assert "SampleOrder" in lock_data["models"]
        
        # Check product model schema
        product_schema = lock_data["models"]["SampleProduct"]
        assert product_schema["table"] == "products"
        assert "name" in product_schema["fields"]
        assert product_schema["fields"]["name"]["type"] == "StringField"
        assert product_schema["fields"]["name"]["null"] is False
        
        # Check schema hash
        assert len(lock_data["schema_hash"]) == 16
        
    def test_generate_lock_with_migrations(self):
        models = [SampleProduct]
        migrations = [
            Migration("v1", "SQL1", "First"),
            Migration("v2", "SQL2", "Second"),
        ]
        
        lock_data = SchemaLock.generate_lock(models, migrations)
        
        assert len(lock_data["migrations"]) == 2
        assert lock_data["migrations"][0]["version"] == "v1"
        assert lock_data["migrations"][1]["version"] == "v2"
        
    def test_write_and_read_lock_file(self):
        models = [SampleProduct]
        lock_data = SchemaLock.generate_lock(models)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            filename = f.name
            
        try:
            # Write lock file
            SchemaLock.write_lock_file(lock_data, filename)
            
            # Read it back
            read_data = SchemaLock.read_lock_file(filename)
            
            assert read_data["schema_hash"] == lock_data["schema_hash"]
            assert read_data["models"] == lock_data["models"]
            
        finally:
            os.unlink(filename)
            
    def test_verify_schema_no_changes(self):
        models = [SampleProduct, SampleOrder]
        
        # Create lock file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            filename = f.name
            
        try:
            lock_data = SchemaLock.generate_lock(models)
            SchemaLock.write_lock_file(lock_data, filename)
            
            # Verify with same models
            result = SchemaLock.verify_schema(models, filename)
            
            assert result["valid"] is True
            assert result["schema_hash"] == lock_data["schema_hash"]
            
        finally:
            os.unlink(filename)
            
    def test_verify_schema_with_changes(self):
        # Create lock with original model
        original_models = [SampleProduct]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            filename = f.name
            
        try:
            lock_data = SchemaLock.generate_lock(original_models)
            SchemaLock.write_lock_file(lock_data, filename)
            
            # Add a new model
            new_models = [SampleProduct, SampleOrder]
            
            # Verify should detect changes
            result = SchemaLock.verify_schema(new_models, filename)
            
            assert result["valid"] is False
            assert result["reason"] == "Schema has changed"
            assert "SampleOrder" in result["changes"]["added_models"]
            
        finally:
            os.unlink(filename)
            
    def test_verify_schema_no_lock_file(self):
        models = [SampleProduct]
        result = SchemaLock.verify_schema(models, "nonexistent.json")
        
        assert result["valid"] is False
        assert "No lock file found" in result["reason"]


class TestMigrationGenerator:
    """Test MigrationGenerator functionality"""
    
    def test_generate_add_column(self):
        from kinglet.orm import StringField
        
        field = StringField(max_length=100, null=True)
        sql = MigrationGenerator.generate_add_column(
            "products", "description", field
        )
        
        assert "ALTER TABLE products ADD COLUMN description" in sql
        assert "VARCHAR(100)" in sql
        
    def test_generate_add_column_not_null_with_default(self):
        from kinglet.orm import IntegerField
        
        field = IntegerField(null=False, default=0)
        sql = MigrationGenerator.generate_add_column(
            "products", "quantity", field
        )
        
        assert "ALTER TABLE products ADD COLUMN quantity" in sql
        assert "INTEGER" in sql
        assert "DEFAULT 0" in sql
        
    def test_detect_changes_new_model(self):
        # Old lock has only Product
        old_lock = SchemaLock.generate_lock([SampleProduct])
        
        # New lock has Product and Order
        new_lock = SchemaLock.generate_lock([SampleProduct, SampleOrder])
        
        migrations = MigrationGenerator.detect_changes(old_lock, new_lock)
        
        assert len(migrations) == 1
        assert "create_orders" in migrations[0].version
        assert migrations[0].description == "Create table orders"
        
    def test_detect_changes_new_field(self):
        # Simulate adding a field
        old_lock = {
            "models": {
                "SampleProduct": {
                    "table": "products",
                    "fields": {
                        "id": {"type": "IntegerField", "sql_type": "INTEGER", "null": True},
                        "name": {"type": "StringField", "sql_type": "VARCHAR(100)", "null": False}
                    }
                }
            }
        }
        
        new_lock = {
            "models": {
                "SampleProduct": {
                    "table": "products",
                    "fields": {
                        "id": {"type": "IntegerField", "sql_type": "INTEGER", "null": True},
                        "name": {"type": "StringField", "sql_type": "VARCHAR(100)", "null": False},
                        "description": {"type": "StringField", "sql_type": "TEXT", "null": True}
                    }
                }
            }
        }
        
        migrations = MigrationGenerator.detect_changes(old_lock, new_lock)
        
        assert len(migrations) == 1
        assert "add_products_description" in migrations[0].version
        assert "ALTER TABLE products ADD COLUMN description" in migrations[0].sql


class TestEndToEndMigration:
    """Test complete migration workflow"""
    
    @pytest.mark.asyncio
    async def test_full_migration_workflow(self):
        """Test the complete migration lifecycle"""
        with patch('kinglet.orm_migrations.d1_unwrap') as mock_unwrap, \
             patch('kinglet.orm_migrations.d1_unwrap_results') as mock_unwrap_results:
                
            db = MockD1Database()
            
            # 1. Initial schema creation
            await SampleProduct.create_table(db)
            
            # 2. Ensure migrations table exists (required before tracking)
            await MigrationTracker.ensure_migrations_table(db)
            
            # 3. Track initial migration
            initial_migration = Migration(
                version="2024_01_01_000000_initial",
                sql=SampleProduct.get_create_sql(),
                description="Initial schema"
            )
            
            await MigrationTracker.apply_migration(db, initial_migration)
            
            # 4. Verify migration was applied (mock the response)
            mock_unwrap.return_value = {'version': initial_migration.version}
            assert await MigrationTracker.is_applied(db, initial_migration.version)
            
            # 5. Generate lock file
            models = [SampleProduct]
            lock_data = SchemaLock.generate_lock(models, [initial_migration])
            
            # 6. Simulate adding a new field (would be done manually)
            add_field_migration = Migration(
                version="2024_01_02_000000_add_description",
                sql="ALTER TABLE products ADD COLUMN description TEXT;",
                description="Add description field"
            )
            
            # 7. Apply the new migration
            # Mock that first migration is already applied, second is not
            mock_unwrap.side_effect = [
                {'version': initial_migration.version},  # is_applied check
                None,  # Second migration not found
            ]
            
            result = await MigrationTracker.apply_migration(db, add_field_migration)
            assert result["status"] == "applied"
            
            # 8. Check final migration status - mock the status response
            mock_unwrap_results.return_value = [
                {'version': initial_migration.version, 'applied_at': 1234567890, 'checksum': 'abc', 'description': 'Initial'},
                {'version': add_field_migration.version, 'applied_at': 1234567891, 'checksum': 'def', 'description': 'Add field'},
            ]
            mock_unwrap.return_value = {'version': add_field_migration.version, 'applied_at': 1234567891}
            
            status = await MigrationTracker.get_migration_status(db)
            assert status["current_version"] == "2024_01_02_000000_add_description"
            assert status["migrations_count"] == 2
            assert status["healthy"] is True
            
            # 9. Verify both migrations are tracked
            mock_unwrap_results.return_value = [
                {'version': initial_migration.version},
                {'version': add_field_migration.version},
            ]
            
            applied = await MigrationTracker.get_applied_migrations(db)
            assert len(applied) == 2
            assert initial_migration.version in applied
            assert add_field_migration.version in applied


if __name__ == "__main__":
    pytest.main([__file__, "-v"])