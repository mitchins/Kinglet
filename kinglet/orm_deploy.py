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

import sys
import os
import json
import subprocess
import argparse
import importlib
from typing import List, Type, Optional
from datetime import datetime
from .orm import Model, SchemaManager
from .orm_migrations import Migration, MigrationTracker, SchemaLock, MigrationGenerator


def import_models(module_path: str) -> List[Type[Model]]:
    """Import all Model classes from a module"""
    module = importlib.import_module(module_path)
    models = []
    
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if (isinstance(attr, type) and 
            issubclass(attr, Model) and 
            attr is not Model):
            models.append(attr)
            
    return models


def generate_schema(module_path: str, include_indexes: bool = True, cleanslate: bool = False) -> str:
    """Generate SQL schema from models"""
    models = import_models(module_path)
    
    if not models:
        print(f"Warning: No models found in {module_path}", file=sys.stderr)
        return ""
    
    sql_parts = [
        "-- Kinglet ORM Schema",
        f"-- Generated from: {module_path}",
        "-- Run with: npx wrangler d1 execute DB --file=schema.sql\n"
    ]
    
    if cleanslate:
        # Add DROP statements for clean slate deployment
        sql_parts.append("-- Clean Slate: Drop all tables first")
        
        # Get all unique table names from models
        tables = set()
        for model in models:
            tables.add(model._meta.table_name)
        
        # Add common tables that might have foreign keys to our models
        dependent_tables = [
            'game_media', 'game_reviews', 'game_tags', 'store_collaborators', 
            'publisher_profiles', 'terms_acceptances', 'sessions', 
            'transactions', 'game_listings', 'store_settings', 'terms_documents'
        ]
        
        # Drop dependent tables first
        for table in dependent_tables:
            sql_parts.append(f"DROP TABLE IF EXISTS {table};")
        
        # Drop model tables
        for table in sorted(tables):
            sql_parts.append(f"DROP TABLE IF EXISTS {table};")
        
        sql_parts.append("")
    
    # Generate CREATE TABLE statements
    seen_tables = set()  # Track tables to avoid duplicates
    for model in models:
        table_name = model._meta.table_name
        if table_name not in seen_tables:
            sql_parts.append(f"-- Model: {model.__name__}")
            create_sql = model.get_create_sql()
            if cleanslate:
                # Remove IF NOT EXISTS for clean slate
                create_sql = create_sql.replace("CREATE TABLE IF NOT EXISTS", "CREATE TABLE")
            sql_parts.append(create_sql)
            sql_parts.append("")
            seen_tables.add(table_name)
        else:
            print(f"Warning: Skipping duplicate table '{table_name}' from model {model.__name__}", file=sys.stderr)
    
    if include_indexes:
        # Add common indexes for better query performance
        sql_parts.append("-- Performance Indexes")
        for model in models:
            table = model._meta.table_name
            
            # Index on common filter fields
            for field_name, field in model._fields.items():
                if field.unique and not field.primary_key:
                    sql_parts.append(
                        f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table}_{field_name} "
                        f"ON {table}({field_name});"
                    )
                elif field_name.endswith('_at'):  # Timestamp fields
                    sql_parts.append(
                        f"CREATE INDEX IF NOT EXISTS idx_{table}_{field_name} "
                        f"ON {table}({field_name});"
                    )
        sql_parts.append("")
    
    return "\n".join(sql_parts)


def deploy_schema(module_path: str, database: str = "DB", env: str = "production") -> int:
    """Deploy schema using wrangler"""
    schema = generate_schema(module_path)
    
    if not schema:
        return 1
    
    # Write to temp file
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
        f.write(schema)
        schema_file = f.name
    
    try:
        # Build wrangler command
        cmd = ["npx", "wrangler", "d1", "execute", database, f"--file={schema_file}"]
        
        if env == "production":
            cmd.append("--remote")
        elif env == "local":
            cmd.append("--local")
        
        print(f"Executing: {' '.join(cmd)}", file=sys.stderr)
        result = subprocess.run(cmd, capture_output=True, text=True)
        
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
    return f'''
# Add this endpoint to your Kinglet app for development migrations

from {module_path} import *  # Import your models
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
        {', '.join([m.__name__ for m in import_models(module_path)])}
    ]
    
    # Run migrations
    results = await SchemaManager.migrate_all(request.env.DB, models)
    
    return {{
        "status": "success",
        "migrated": results,
        "models": [m.__name__ for m in models]
    }}
'''


def generate_lock(module_path: str, output: str = "schema.lock.json") -> int:
    """Generate schema lock file"""
    try:
        models = import_models(module_path)
        
        if not models:
            print(f"Warning: No models found in {module_path}", file=sys.stderr)
            return 1
        
        # Check for existing migrations
        migrations = []
        if os.path.exists("migrations.json"):
            with open("migrations.json", 'r') as f:
                migration_data = json.load(f)
                for m in migration_data.get("migrations", []):
                    migrations.append(Migration(
                        version=m["version"],
                        sql=m.get("sql", ""),
                        description=m.get("description", "")
                    ))
        
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


def verify_schema(module_path: str, lock_file: str = "schema.lock.json") -> int:
    """Verify schema against lock file"""
    try:
        models = import_models(module_path)
        result = SchemaLock.verify_schema(models, lock_file)
        
        if result["valid"]:
            print(f"✅ Schema matches lock file", file=sys.stderr)
            print(f"   Hash: {result['schema_hash']}", file=sys.stderr)
            print(f"   Models: {result['models_count']}", file=sys.stderr)
            return 0
        else:
            print(f"❌ Schema has changed!", file=sys.stderr)
            print(f"   Reason: {result['reason']}", file=sys.stderr)
            
            if "changes" in result:
                changes = result["changes"]
                if changes["added_models"]:
                    print(f"   Added models: {', '.join(changes['added_models'])}", file=sys.stderr)
                if changes["removed_models"]:
                    print(f"   Removed models: {', '.join(changes['removed_models'])}", file=sys.stderr)
                if changes["modified_models"]:
                    print(f"   Modified models: {', '.join(changes['modified_models'])}", file=sys.stderr)
            
            print(f"\n   Action: {result['action']}", file=sys.stderr)
            return 1
            
    except Exception as e:
        print(f"Error verifying schema: {e}", file=sys.stderr)
        return 1


def generate_migrations(module_path: str, lock_file: str = "schema.lock.json") -> int:
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
            print("Schema changed but no migrations generated (manual migration may be needed)", file=sys.stderr)
            return 1
        
        # Output migrations
        print(f"-- Generated {len(migrations)} migration(s)", file=sys.stderr)
        print(f"-- Run with: npx wrangler d1 execute DB --file=migrations.sql --remote\n", file=sys.stderr)
        
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
            "migrations": [m.to_dict() for m in migrations]
        }
        
        with open("migrations.json", 'w') as f:
            json.dump(migration_data, f, indent=2)
        
        print(f"\n-- Migration metadata saved to migrations.json", file=sys.stderr)
        print(f"-- After applying migrations, run: python -m kinglet.orm_deploy lock {module_path}", file=sys.stderr)
        
        return 0
        
    except Exception as e:
        print(f"Error generating migrations: {e}", file=sys.stderr)
        return 1


def generate_status_endpoint(module_path: str) -> str:
    """Generate status endpoint code"""
    return f'''
# Add this endpoint to check migration status

from {module_path} import *  # Import your models
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
        with open("schema.lock.json", 'r') as f:
            lock_data = json.load(f)
            if lock_data.get("migrations"):
                expected_version = lock_data["migrations"][-1]["version"]
    except:
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
'''


def main():
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
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Generate command
    gen_parser = subparsers.add_parser('generate', help='Generate initial SQL schema')
    gen_parser.add_argument('module', help='Python module containing models')
    gen_parser.add_argument('--no-indexes', action='store_true', 
                           help='Skip index generation')
    gen_parser.add_argument('--cleanslate', action='store_true',
                           help='Include DROP statements for clean deployment')
    
    # Lock command
    lock_parser = subparsers.add_parser('lock', help='Generate schema lock file')
    lock_parser.add_argument('module', help='Python module containing models')
    lock_parser.add_argument('--output', default='schema.lock.json',
                            help='Output lock file (default: schema.lock.json)')
    
    # Verify command
    verify_parser = subparsers.add_parser('verify', help='Verify schema against lock')
    verify_parser.add_argument('module', help='Python module containing models')
    verify_parser.add_argument('--lock', default='schema.lock.json',
                              help='Lock file to verify against')
    
    # Migrate command
    migrate_parser = subparsers.add_parser('migrate', help='Generate migration SQL')
    migrate_parser.add_argument('module', help='Python module containing models')
    migrate_parser.add_argument('--lock', default='schema.lock.json',
                               help='Lock file to compare against')
    
    # Deploy command
    deploy_parser = subparsers.add_parser('deploy', help='Deploy schema via wrangler')
    deploy_parser.add_argument('module', help='Python module containing models')
    deploy_parser.add_argument('--database', default='DB', 
                              help='D1 database binding name (default: DB)')
    deploy_parser.add_argument('--env', choices=['local', 'preview', 'production'],
                              default='production', help='Deployment environment')
    
    # Status endpoint command
    status_parser = subparsers.add_parser('status', help='Generate status endpoint code')
    status_parser.add_argument('module', help='Python module containing models')
    
    # Endpoint command (legacy)
    ep_parser = subparsers.add_parser('endpoint', help='Generate migration endpoint code')
    ep_parser.add_argument('module', help='Python module containing models')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    try:
        if args.command == 'generate':
            schema = generate_schema(args.module, not args.no_indexes, args.cleanslate)
            print(schema)
            return 0
            
        elif args.command == 'lock':
            return generate_lock(args.module, args.output)
            
        elif args.command == 'verify':
            return verify_schema(args.module, args.lock)
            
        elif args.command == 'migrate':
            return generate_migrations(args.module, args.lock)
            
        elif args.command == 'deploy':
            return deploy_schema(args.module, args.database, args.env)
            
        elif args.command == 'status':
            code = generate_status_endpoint(args.module)
            print(code)
            return 0
            
        elif args.command == 'endpoint':
            code = generate_migration_endpoint(args.module)
            print(code)
            return 0
            
    except ImportError as e:
        print(f"Error importing module: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())