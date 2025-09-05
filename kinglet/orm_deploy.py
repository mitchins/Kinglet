#!/usr/bin/env python
"""
Kinglet ORM Deployment Helper

Generates schema SQL and deployment commands for D1 migrations.
Tracks schema versions and migrations for safe deployments.

Usage:
    python -m kinglet.orm_deploy generate app.models > schema.sql
    python -m kinglet.orm_deploy lock app.models  # Generate schema.lock.json
    python -m kinglet.orm_deploy verify app.models  # Check for schema changes
    python -m kinglet.orm_deploy migrate app.models  # Generate migration SQL
"""

import argparse
import importlib
import json
import os

# Used only for Cloudflare Wrangler CLI deployment with controlled parameters
import subprocess  # nosec B404
import sys
from datetime import datetime

from .constants import MIGRATIONS_FILE, PYTHON_MODULE_HELP, SCHEMA_LOCK_FILE
from .orm import Model, SchemaManager  # noqa: F401 - Used in template generation
from .orm_migrations import (  # noqa: F401 - Used in endpoints
    Migration,
    MigrationGenerator,
    MigrationTracker,
    SchemaLock,
)


def import_models(module_path: str) -> list[type[Model]]:
    """Import all Model classes from a module"""
    module = importlib.import_module(module_path)
    models = []

    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if isinstance(attr, type) and issubclass(attr, Model) and attr is not Model:
            models.append(attr)

    return models


def _collect_tables(models: list[type[Model]]) -> set[str]:
    return {m._meta.table_name for m in models}


def _append_cleanslate(parts: list[str], models: list[type[Model]]) -> None:
    parts.append("-- Clean Slate: Drop all tables first")
    tables = _collect_tables(models)
    dependent_tables = [
        "game_media",
        "game_reviews",
        "game_tags",
        "store_collaborators",
        "publisher_profiles",
        "terms_acceptances",
        "sessions",
        "transactions",
        "game_listings",
        "store_settings",
        "terms_documents",
    ]
    for table in dependent_tables:
        parts.append(f"DROP TABLE IF EXISTS {table};")
    for table in sorted(tables):
        parts.append(f"DROP TABLE IF EXISTS {table};")
    parts.append("")


def _append_create_tables(
    parts: list[str], models: list[type[Model]], cleanslate: bool
) -> None:
    seen: set[str] = set()
    for model in models:
        table_name = model._meta.table_name
        if table_name in seen:
            print(
                f"Warning: Skipping duplicate table '{table_name}' from model {model.__name__}",
                file=sys.stderr,
            )
            continue
        parts.append(f"-- Model: {model.__name__}")
        create_sql = model.get_create_sql()
        if cleanslate:
            create_sql = create_sql.replace(
                "CREATE TABLE IF NOT EXISTS", "CREATE TABLE"
            )
        parts.append(create_sql)
        parts.append("")
        seen.add(table_name)


def _append_indexes(
    parts: list[str], models: list[type[Model]], include_indexes: bool
) -> None:
    if not include_indexes:
        return
    parts.append("-- Performance Indexes")
    seen_tables: set[str] = set()
    for model in models:
        table = model._meta.table_name
        if table in seen_tables:
            continue
        for field_name, field in model._fields.items():
            if field.unique and not field.primary_key:
                parts.append(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table}_{field_name} ON {table}({field_name});"
                )
            elif hasattr(field, "index") and field.index and not field.primary_key:
                parts.append(
                    f"CREATE INDEX IF NOT EXISTS idx_{table}_{field_name} ON {table}({field_name});"
                )
        seen_tables.add(table)
    parts.append("")


def generate_schema(
    module_path: str, include_indexes: bool = True, cleanslate: bool = False
) -> str:
    """Generate SQL schema from models"""
    models = import_models(module_path)

    if not models:
        print(f"Warning: No models found in {module_path}", file=sys.stderr)
        return ""

    sql_parts = [
        "-- Kinglet ORM Schema",
        f"-- Generated from: {module_path}",
        "-- Run with: npx wrangler d1 execute DB --file=schema.sql\n",
    ]

    if cleanslate:
        _append_cleanslate(sql_parts, models)
    _append_create_tables(sql_parts, models, cleanslate)
    _append_indexes(sql_parts, models, include_indexes)

    return "\n".join(sql_parts)


def deploy_schema(
    module_path: str, database: str = "DB", env: str = "production"
) -> int:
    """Deploy schema using wrangler"""
    schema = generate_schema(module_path)

    if not schema:
        return 1

    # Write to temp file
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
        f.write(schema)
        schema_file = f.name

    try:
        # Validate inputs and build command safely (no shell)
        import re

        if not re.match(r"^[A-Za-z0-9_-]+$", database or ""):
            print("Invalid database binding name", file=sys.stderr)
            return 1
        # Build wrangler command
        cmd = ["npx", "wrangler", "d1", "execute", database, f"--file={schema_file}"]

        if env == "production":
            cmd.append("--remote")
        elif env == "local":
            cmd.append("--local")

        print(f"Executing: {' '.join(cmd)}", file=sys.stderr)
        # Fixed command structure, no shell=True, controlled parameters
        result = subprocess.run(  # nosec B603
            cmd, capture_output=True, text=True
        )

        if result.returncode != 0:
            print(f"Error: {result.stderr}", file=sys.stderr)
            return result.returncode

        print(f"Schema deployed successfully to {env}", file=sys.stderr)
        return 0

    finally:
        import os

        os.unlink(schema_file)


def generate_migration_endpoint(module_path: str) -> str:
    """Generate migration endpoint code"""
    from string import Template

    models_list = ", ".join([m.__name__ for m in import_models(module_path)])
    template = Template('''
# Add this endpoint to your Kinglet app for development migrations

from ${module_path} import *  # Import your models
from kinglet import SchemaManager

@app.post("/api/_migrate")
async def migrate_database(request):
    """
    Migration endpoint for development/staging

    Usage:
        curl -X POST https://your-app.workers.dev/api/_migrate \\
             -H "X-Migration-Token: your-secret-token"
    """
    # Security check
    token = request.header("X-Migration-Token", "")
    expected = request.env.get("MIGRATION_TOKEN", "")

    if not token or token != expected:
        return {{"error": "Unauthorized"}}, 401

    # Get all models
    models = [
        ${models_list}
    ]

    # Run migrations
    results = await SchemaManager.migrate_all(request.env.DB, models)

    return {{
        "status": "success",
        "migrated": results,
        "models": [m.__name__ for m in models]
    }}
''')
    return template.substitute(module_path=module_path, models_list=models_list)


def generate_lock(module_path: str, output: str = SCHEMA_LOCK_FILE) -> int:
    """Generate schema lock file"""
    try:
        models = import_models(module_path)

        if not models:
            print(f"Warning: No models found in {module_path}", file=sys.stderr)
            return 1

        # Check for existing migrations
        migrations = []
        if os.path.exists(MIGRATIONS_FILE):
            with open(MIGRATIONS_FILE) as f:
                migration_data = json.load(f)
                for m in migration_data.get("migrations", []):
                    migrations.append(
                        Migration(
                            version=m["version"],
                            sql=m.get("sql", ""),
                            description=m.get("description", ""),
                        )
                    )

        # Generate lock
        lock_data = SchemaLock.generate_lock(models, migrations)

        # Write lock file
        SchemaLock.write_lock_file(lock_data, output)

        print(f"✅ Schema lock generated: {output}", file=sys.stderr)
        print(f"   Models: {len(models)}", file=sys.stderr)
        print(f"   Schema hash: {lock_data['schema_hash']}", file=sys.stderr)

        return 0

    except Exception as e:
        print(f"Error generating lock: {e}", file=sys.stderr)
        return 1


def verify_schema(module_path: str, lock_file: str = SCHEMA_LOCK_FILE) -> int:
    """Verify schema against lock file"""
    try:
        models = import_models(module_path)
        result = SchemaLock.verify_schema(models, lock_file)

        if result["valid"]:
            print("✅ Schema matches lock file", file=sys.stderr)
            print(f"   Hash: {result['schema_hash']}", file=sys.stderr)
            print(f"   Models: {result['models_count']}", file=sys.stderr)
            return 0
        else:
            print("❌ Schema has changed!", file=sys.stderr)
            print(f"   Reason: {result['reason']}", file=sys.stderr)

            if "changes" in result:
                changes = result["changes"]
                if changes["added_models"]:
                    print(
                        f"   Added models: {', '.join(changes['added_models'])}",
                        file=sys.stderr,
                    )
                if changes["removed_models"]:
                    print(
                        f"   Removed models: {', '.join(changes['removed_models'])}",
                        file=sys.stderr,
                    )
                if changes["modified_models"]:
                    print(
                        f"   Modified models: {', '.join(changes['modified_models'])}",
                        file=sys.stderr,
                    )

            print(f"\n   Action: {result['action']}", file=sys.stderr)
            return 1

    except Exception as e:
        print(f"Error verifying schema: {e}", file=sys.stderr)
        return 1


def generate_migrations(module_path: str, lock_file: str = SCHEMA_LOCK_FILE) -> int:
    """Generate migrations from schema changes"""
    try:
        models = import_models(module_path)

        # Read old lock
        old_lock = SchemaLock.read_lock_file(lock_file)
        if not old_lock:
            print("No existing lock file. Run 'lock' command first.", file=sys.stderr)
            return 1

        # Generate new lock
        new_lock = SchemaLock.generate_lock(models)

        # Check if schemas match
        if old_lock["schema_hash"] == new_lock["schema_hash"]:
            print("✅ No schema changes detected", file=sys.stderr)
            return 0

        # Generate migrations
        migrations = MigrationGenerator.detect_changes(old_lock, new_lock)

        if not migrations:
            print(
                "Schema changed but no migrations generated (manual migration may be needed)",
                file=sys.stderr,
            )
            return 1

        # Output migrations
        print(f"-- Generated {len(migrations)} migration(s)", file=sys.stderr)
        print(
            "-- Run with: npx wrangler d1 execute DB --file=migrations.sql --remote\n",
            file=sys.stderr,
        )

        for migration in migrations:
            print(f"-- Migration: {migration.version}")
            print(f"-- {migration.description}")
            print(migration.sql)
            print()

        # Save migration metadata
        migration_data = {
            "generated_at": datetime.now().isoformat(),
            "from_hash": old_lock["schema_hash"],
            "to_hash": new_lock["schema_hash"],
            "migrations": [m.to_dict() for m in migrations],
        }

        with open(MIGRATIONS_FILE, "w") as f:
            json.dump(migration_data, f, indent=2)

        print("\n-- Migration metadata saved to migrations.json", file=sys.stderr)
        print(
            f"-- After applying migrations, run: python -m kinglet.orm_deploy lock {module_path}",
            file=sys.stderr,
        )

        return 0

    except Exception as e:
        print(f"Error generating migrations: {e}", file=sys.stderr)
        return 1


def generate_status_endpoint(module_path: str) -> str:
    """Generate status endpoint code"""
    from string import Template

    template = Template('''
# Add this endpoint to check migration status

from ${module_path} import *  # Import your models
from kinglet.orm_migrations import MigrationTracker, SchemaLock

@app.get("/api/_status")
async def migration_status(request):
    """
    Check migration status

    Usage:
        curl https://your-app.workers.dev/api/_status
    """
    # Get migration status from database
    status = await MigrationTracker.get_migration_status(request.env.DB)

    # Get expected schema version from lock file (if available)
    expected_version = None
    try:
        import json
        # This would need to be bundled with your worker
        with open(SCHEMA_LOCK_FILE, 'r') as f:
            lock_data = json.load(f)
            if lock_data.get("migrations"):
                expected_version = lock_data["migrations"][-1]["version"]
    except Exception:
        pass

    return {{
        "database": {{
            "current_version": status["current_version"],
            "migrations_applied": status["migrations_count"],
            "healthy": status["healthy"]
        }},
        "expected_version": expected_version,
        "up_to_date": status["current_version"] == expected_version if expected_version else None,
        "migrations": status["migrations"][:5]  # Last 5 migrations
    }}

@app.post("/api/_migrate")
async def apply_migrations(request):
    """
    Apply pending migrations

    Usage:
        curl -X POST https://your-app.workers.dev/api/_migrate \\
             -H "X-Migration-Token: your-secret-token"
    """
    # Security check
    token = request.header("X-Migration-Token", "")
    expected = request.env.get("MIGRATION_TOKEN", "")

    if not token or token != expected:
        return {{"error": "Unauthorized"}}, 401

    # Define your migrations
    migrations = [
        # Add your migrations here in order
        # Migration("2024_01_01_initial", "CREATE TABLE ...", "Initial schema"),
    ]

    # Apply migrations
    results = await MigrationTracker.apply_migrations(request.env.DB, migrations)

    return {{
        "status": "complete",
        "results": results,
        "current_version": await MigrationTracker.get_schema_version(request.env.DB)
    }}
''')
    return template.substitute(module_path=module_path)


def _create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser with all subcommands"""
    parser = argparse.ArgumentParser(
        description="Kinglet ORM deployment helper with migration tracking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Migration Workflow:
  # Initial setup
  python -m kinglet.orm_deploy generate myapp.models > schema.sql
  npx wrangler d1 execute DB --file=schema.sql --remote
  python -m kinglet.orm_deploy lock myapp.models  # Create schema.lock.json

  # After model changes
  python -m kinglet.orm_deploy verify myapp.models  # Check for changes
  python -m kinglet.orm_deploy migrate myapp.models > migrations.sql
  npx wrangler d1 execute DB --file=migrations.sql --remote
  python -m kinglet.orm_deploy lock myapp.models  # Update lock file

  # Check status
  curl https://your-app.workers.dev/api/_status
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")
    _add_generate_parser(subparsers)
    _add_lock_parser(subparsers)
    _add_verify_parser(subparsers)
    _add_migrate_parser(subparsers)
    _add_deploy_parser(subparsers)
    _add_status_parser(subparsers)
    _add_endpoint_parser(subparsers)

    return parser


def _add_generate_parser(subparsers):
    """Add generate subcommand parser"""
    gen_parser = subparsers.add_parser("generate", help="Generate initial SQL schema")
    gen_parser.add_argument("module", help=PYTHON_MODULE_HELP)
    gen_parser.add_argument(
        "--no-indexes", action="store_true", help="Skip index generation"
    )
    gen_parser.add_argument(
        "--cleanslate",
        action="store_true",
        help="Include DROP statements for clean deployment",
    )


def _add_lock_parser(subparsers):
    """Add lock subcommand parser"""
    lock_parser = subparsers.add_parser("lock", help="Generate schema lock file")
    lock_parser.add_argument("module", help=PYTHON_MODULE_HELP)
    lock_parser.add_argument(
        "--output",
        default=SCHEMA_LOCK_FILE,
        help="Output lock file (default: schema.lock.json)",
    )


def _add_verify_parser(subparsers):
    """Add verify subcommand parser"""
    verify_parser = subparsers.add_parser("verify", help="Verify schema against lock")
    verify_parser.add_argument("module", help=PYTHON_MODULE_HELP)
    verify_parser.add_argument(
        "--lock", default=SCHEMA_LOCK_FILE, help="Lock file to verify against"
    )


def _add_migrate_parser(subparsers):
    """Add migrate subcommand parser"""
    migrate_parser = subparsers.add_parser("migrate", help="Generate migration SQL")
    migrate_parser.add_argument("module", help=PYTHON_MODULE_HELP)
    migrate_parser.add_argument(
        "--lock", default=SCHEMA_LOCK_FILE, help="Lock file to compare against"
    )


def _add_deploy_parser(subparsers):
    """Add deploy subcommand parser"""
    deploy_parser = subparsers.add_parser("deploy", help="Deploy schema via wrangler")
    deploy_parser.add_argument("module", help=PYTHON_MODULE_HELP)
    deploy_parser.add_argument(
        "--database", default="DB", help="D1 database binding name (default: DB)"
    )
    deploy_parser.add_argument(
        "--env",
        choices=["local", "preview", "production"],
        default="production",
        help="Deployment environment",
    )


def _add_status_parser(subparsers):
    """Add status subcommand parser"""
    status_parser = subparsers.add_parser(
        "status", help="Generate status endpoint code"
    )
    status_parser.add_argument("module", help=PYTHON_MODULE_HELP)


def _add_endpoint_parser(subparsers):
    """Add endpoint subcommand parser (legacy)"""
    ep_parser = subparsers.add_parser(
        "endpoint", help="Generate migration endpoint code"
    )
    ep_parser.add_argument("module", help=PYTHON_MODULE_HELP)


def _execute_command(args) -> int:
    """Execute the selected command with error handling"""
    try:
        if args.command == "generate":
            schema = generate_schema(args.module, not args.no_indexes, args.cleanslate)
            print(schema)
            return 0
        elif args.command == "lock":
            return generate_lock(args.module, args.output)
        elif args.command == "verify":
            return verify_schema(args.module, args.lock)
        elif args.command == "migrate":
            return generate_migrations(args.module, args.lock)
        elif args.command == "deploy":
            return deploy_schema(args.module, args.database, args.env)
        elif args.command == "status":
            code = generate_status_endpoint(args.module)
            print(code)
            return 0
        elif args.command == "endpoint":
            code = generate_migration_endpoint(args.module)
            print(code)
            return 0
    except ImportError as e:
        print(f"Error importing module: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


def main():
    parser = _create_argument_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    return _execute_command(args)


if __name__ == "__main__":
    sys.exit(main())
