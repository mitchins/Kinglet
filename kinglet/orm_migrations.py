"""
Kinglet ORM Migration Tracking

Lightweight schema versioning for D1 databases.
Tracks applied migrations without complex migration frameworks.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime
from typing import Any

from .constants import SCHEMA_LOCK_FILE
from .sql import quote_ident_sqlite, safe_ident
from .storage import d1_unwrap, d1_unwrap_results


class Migration:
    """Represents a single migration"""

    def __init__(self, version: str, sql: str, description: str = ""):
        self.version = version
        self.sql = sql
        self.description = description
        self.checksum = self._calculate_checksum()

    def _calculate_checksum(self) -> str:
        """Calculate checksum of SQL for integrity checking"""
        return hashlib.sha256(self.sql.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "checksum": self.checksum,
            "description": self.description,
            "sql_length": len(self.sql),
        }


class MigrationTracker:
    """
    Tracks schema migrations in D1

    Uses a simple migrations table to track what's been applied.
    Much lighter than Django/Alembic but sufficient for Workers.
    """

    MIGRATIONS_TABLE = "_kinglet_migrations"

    @classmethod
    async def ensure_migrations_table(cls, db) -> None:
        """Create migrations tracking table if it doesn't exist"""
        await db.exec(f"""
            CREATE TABLE IF NOT EXISTS {cls.MIGRATIONS_TABLE} (
                version TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                description TEXT,
                applied_at INTEGER NOT NULL,
                sql_hash TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_migrations_applied
            ON {cls.MIGRATIONS_TABLE}(applied_at);
        """)

    @classmethod
    async def get_applied_migrations(cls, db) -> list[str]:
        """Get list of applied migration versions"""
        try:
            safe_ident(cls.MIGRATIONS_TABLE)  # Validate table name
            quoted_table = quote_ident_sqlite(cls.MIGRATIONS_TABLE)
            result = await db.prepare(
                f"SELECT version FROM {quoted_table} ORDER BY applied_at"  # nosec B608: identifier validated+quoted
            ).all()

            if hasattr(result, "results"):
                return [row["version"] for row in d1_unwrap_results(result)]
            return []
        except Exception:
            # Table might not exist yet
            return []

    @classmethod
    async def is_applied(cls, db, version: str) -> bool:
        """Check if a specific migration has been applied"""
        safe_ident(cls.MIGRATIONS_TABLE)  # Validate table name
        quoted_table = quote_ident_sqlite(cls.MIGRATIONS_TABLE)
        result = (
            await db.prepare(
                f"SELECT version FROM {quoted_table} WHERE version = ?"  # nosec B608: identifier validated+quoted; values parameterized
            )
            .bind(version)
            .first()
        )
        return result is not None

    @classmethod
    async def record_migration(cls, db, migration: Migration) -> None:
        """Record that a migration has been applied"""
        safe_ident(cls.MIGRATIONS_TABLE)  # Validate table name
        quoted_table = quote_ident_sqlite(cls.MIGRATIONS_TABLE)
        await (
            db.prepare(
                f"""
            INSERT INTO {quoted_table}
            (version, checksum, description, applied_at, sql_hash)
            VALUES (?, ?, ?, ?, ?)
        """  # nosec B608: identifier validated+quoted; values parameterized
            )
            .bind(
                migration.version,
                migration.checksum,
                migration.description,
                int(time.time()),
                hashlib.sha256(migration.sql.encode()).hexdigest(),
            )
            .run()
        )

    @classmethod
    async def apply_migration(cls, db, migration: Migration) -> dict[str, Any]:
        """Apply a single migration"""
        try:
            # Check if already applied
            if await cls.is_applied(db, migration.version):
                return {
                    "version": migration.version,
                    "status": "skipped",
                    "reason": "already applied",
                }

            # Execute migration SQL
            await db.exec(migration.sql)

            # Record migration
            await cls.record_migration(db, migration)

            return {
                "version": migration.version,
                "status": "applied",
                "checksum": migration.checksum,
            }

        except Exception as e:
            return {"version": migration.version, "status": "failed", "error": str(e)}

    @classmethod
    async def apply_migrations(cls, db, migrations: list[Migration]) -> dict[str, Any]:
        """Apply multiple migrations in order"""
        # Ensure migrations table exists
        await cls.ensure_migrations_table(db)

        # Get already applied migrations for logging/state
        applied_migrations = await cls.get_applied_migrations(db)

        results = {
            "applied": [],
            "skipped": [],
            "failed": [],
            "total": len(migrations),
            "previously_applied": len(applied_migrations),
        }

        for migration in migrations:
            result = await cls.apply_migration(db, migration)

            if result["status"] == "applied":
                results["applied"].append(result)
            elif result["status"] == "skipped":
                results["skipped"].append(result)
            else:
                results["failed"].append(result)
                # Stop on first failure
                break

        return results

    @classmethod
    async def get_schema_version(cls, db) -> str | None:
        """Get current schema version (latest applied migration)"""
        try:
            safe_ident(cls.MIGRATIONS_TABLE)  # Validate table name
            quoted_table = quote_ident_sqlite(cls.MIGRATIONS_TABLE)
            result = await db.prepare(
                f"""
                SELECT version, applied_at
                FROM {quoted_table}
                ORDER BY applied_at DESC
                LIMIT 1
            """  # nosec B608: identifier validated+quoted
            ).first()

            if result:
                row = d1_unwrap(result)
                return row.get("version")
            return None
        except Exception:
            return None

    @classmethod
    async def get_migration_status(cls, db) -> dict[str, Any]:
        """Get detailed migration status"""
        try:
            await cls.ensure_migrations_table(db)

            # Get all migrations
            safe_ident(cls.MIGRATIONS_TABLE)  # Validate table name
            quoted_table = quote_ident_sqlite(cls.MIGRATIONS_TABLE)
            result = await db.prepare(
                f"""
                SELECT version, checksum, description, applied_at
                FROM {quoted_table}
                ORDER BY applied_at DESC
            """  # nosec B608: identifier validated+quoted
            ).all()

            migrations = []
            if hasattr(result, "results"):
                for row in d1_unwrap_results(result):
                    migrations.append(
                        {
                            "version": row["version"],
                            "checksum": row["checksum"],
                            "description": row["description"],
                            "applied_at": datetime.fromtimestamp(
                                row["applied_at"]
                            ).isoformat(),
                        }
                    )

            current_version = migrations[0]["version"] if migrations else None

            return {
                "current_version": current_version,
                "migrations_count": len(migrations),
                "migrations": migrations,
                "healthy": True,
            }

        except Exception as e:
            return {
                "current_version": None,
                "migrations_count": 0,
                "migrations": [],
                "healthy": False,
                "error": str(e),
            }


class SchemaLock:
    """
    Generate and verify schema lock files

    Similar to package-lock.json but for database schemas.
    Helps detect schema drift between deployments.
    """

    @staticmethod
    def generate_lock(
        models: list, migrations: list[Migration] = None
    ) -> dict[str, Any]:
        """Generate schema lock data"""
        from .orm import Model

        lock_data = {
            "version": "1.0.0",
            "generated_at": datetime.now().isoformat(),
            "models": {},
            "migrations": [],
            "schema_hash": "",
        }

        # Record model schemas
        for model in models:
            if issubclass(model, Model):
                model_schema = {"table": model._meta.table_name, "fields": {}}

                for field_name, field in model._fields.items():
                    model_schema["fields"][field_name] = {
                        "type": field.__class__.__name__,
                        "sql_type": field.get_sql_type(),
                        "null": field.null,
                        "unique": field.unique,
                        "primary_key": field.primary_key,
                    }

                lock_data["models"][model.__name__] = model_schema

        # Record migrations
        if migrations:
            for migration in migrations:
                lock_data["migrations"].append(
                    {
                        "version": migration.version,
                        "checksum": migration.checksum,
                        "description": migration.description,
                    }
                )

        # Calculate overall schema hash
        schema_str = json.dumps(lock_data["models"], sort_keys=True)
        lock_data["schema_hash"] = hashlib.sha256(schema_str.encode()).hexdigest()[:16]

        return lock_data

    @staticmethod
    def write_lock_file(
        lock_data: dict[str, Any], filename: str = SCHEMA_LOCK_FILE
    ) -> None:
        """Write schema lock to file"""
        with open(filename, "w") as f:
            json.dump(lock_data, f, indent=2)

    @staticmethod
    def read_lock_file(filename: str = SCHEMA_LOCK_FILE) -> dict[str, Any] | None:
        """Read schema lock from file"""
        try:
            with open(filename) as f:
                return json.load(f)
        except FileNotFoundError:
            return None

    @staticmethod
    def verify_schema(
        current_models: list, lock_file: str = SCHEMA_LOCK_FILE
    ) -> dict[str, Any]:
        """Verify current schema matches lock file"""

        # Read existing lock
        existing_lock = SchemaLock.read_lock_file(lock_file)
        if not existing_lock:
            return {
                "valid": False,
                "reason": "No lock file found",
                "action": "Generate with: python -m kinglet.orm_deploy lock",
            }

        # Generate current schema
        current_lock = SchemaLock.generate_lock(current_models)

        # Compare schema hashes
        if existing_lock["schema_hash"] == current_lock["schema_hash"]:
            return {
                "valid": True,
                "schema_hash": existing_lock["schema_hash"],
                "models_count": len(existing_lock["models"]),
            }

        # Find differences
        changes = {"added_models": [], "removed_models": [], "modified_models": []}

        existing_models = set(existing_lock["models"].keys())
        current_models_names = set(current_lock["models"].keys())

        changes["added_models"] = list(current_models_names - existing_models)
        changes["removed_models"] = list(existing_models - current_models_names)

        for model_name in existing_models & current_models_names:
            if (
                existing_lock["models"][model_name]
                != current_lock["models"][model_name]
            ):
                changes["modified_models"].append(model_name)

        return {
            "valid": False,
            "reason": "Schema has changed",
            "changes": changes,
            "action": "Generate migrations or update lock file",
        }


class MigrationGenerator:
    """Generate migrations from model changes"""

    @staticmethod
    def _safe_ident(name: str) -> str:
        """Validate SQL identifier via shared helper"""
        from .sql import safe_ident

        return safe_ident(name)

    @staticmethod
    def generate_add_column(table: str, field_name: str, field) -> str:
        """Generate ALTER TABLE ADD COLUMN statement

        For NOT NULL columns without defaults, generates a multi-step migration.
        """
        sql_type = field.get_sql_type()

        table = MigrationGenerator._safe_ident(table)
        field_name = MigrationGenerator._safe_ident(field_name)

        # Check if we need a multi-step migration for NOT NULL without default
        if not field.null and field.default is None:
            return MigrationGenerator._generate_not_null_migration(
                table, field_name, sql_type, field
            )

        # Normal case: has default or is nullable
        return MigrationGenerator._generate_simple_migration(
            table, field_name, sql_type, field
        )

    @staticmethod
    def _generate_not_null_migration(
        table: str, field_name: str, sql_type: str, field
    ) -> str:
        """Generate multi-step migration for NOT NULL columns without defaults"""
        # Step 1: Add column as nullable
        sql = f"-- Adding NOT NULL column {field_name} requires multi-step migration\n"
        sql += f"ALTER TABLE {table} ADD COLUMN {field_name} {sql_type};\n"  # nosec B608

        # Step 2: Get appropriate default value for backfill
        default_value = MigrationGenerator._get_field_default_value(field)

        sql += "-- Backfill with appropriate values\n"
        sql += f"UPDATE {table} SET {field_name} = {default_value} WHERE {field_name} IS NULL;\n"  # nosec B608

        # Step 3: Add NOT NULL constraint note
        sql += "-- Note: In SQLite/D1, you may need to recreate the table to add NOT NULL constraint"

        return sql

    @staticmethod
    def _generate_simple_migration(
        table: str, field_name: str, sql_type: str, field
    ) -> str:
        """Generate simple ADD COLUMN migration for nullable or columns with defaults"""
        sql = f"ALTER TABLE {table} ADD COLUMN {field_name} {sql_type}"  # nosec B608

        if field.default is not None:
            default_val = MigrationGenerator._get_default_sql_value(
                field.default, field
            )
            if default_val is not None:
                sql += f" DEFAULT {default_val}"

        return sql + ";"

    @staticmethod
    def _get_field_default_value(field) -> str:
        """Get appropriate default value for field type during backfill"""
        field_type = field.__class__.__name__
        if field_type == "StringField":
            return "''"
        elif field_type in ["IntegerField", "FloatField"]:
            return "0"
        elif field_type == "BooleanField":
            return "FALSE"
        elif field_type == "JSONField":
            return "'{}'"
        else:
            return "''"  # Safe fallback

    @staticmethod
    def _get_default_sql_value(default, field):
        """Convert Python default value to SQL representation"""
        if callable(default):
            # For callables like dict or list
            if field.__class__.__name__ == "JSONField":
                return "'{}'"  # Empty JSON object
            else:
                # Skip default for other callables
                return None
        elif isinstance(default, bool):
            return "1" if default else "0"
        elif isinstance(default, str):
            return f"'{default}'"
        else:
            return str(default)

    @staticmethod
    def detect_changes(old_lock: dict, new_lock: dict) -> list[Migration]:
        """Detect changes and generate migrations"""
        migrations = []
        version_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        old_models = old_lock.get("models", {})
        new_models = new_lock.get("models", {})

        # Check for new models (create tables)
        for model_name, model_schema in new_models.items():
            if model_name not in old_models:
                # Generate CREATE TABLE
                # This would need the actual Model class for full SQL
                migrations.append(
                    Migration(
                        version=f"{version_timestamp}_create_{model_schema['table']}",
                        sql=f"-- CREATE TABLE {model_schema['table']} (generated separately)",
                        description=f"Create table {model_schema['table']}",
                    )
                )

        # Check for new fields (add columns)
        for model_name in set(old_models.keys()) & set(new_models.keys()):
            old_fields = old_models[model_name]["fields"]
            new_fields = new_models[model_name]["fields"]
            table = MigrationGenerator._safe_ident(new_models[model_name]["table"])

            for field_name, field_schema in new_fields.items():
                if field_name not in old_fields:
                    field_name_safe = MigrationGenerator._safe_ident(field_name)
                    sql = f"ALTER TABLE {table} ADD COLUMN {field_name_safe} {field_schema['sql_type']}"

                    if not field_schema["null"]:
                        sql += " DEFAULT NULL"  # Temporary default

                    migrations.append(
                        Migration(
                            version=f"{version_timestamp}_add_{table}_{field_name}",
                            sql=sql + ";",
                            description=f"Add column {field_name} to {table}",
                        )
                    )

        return migrations
