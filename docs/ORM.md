# Kinglet ORM Guide

A compute-optimized micro-ORM for Cloudflare D1, designed for Workers' 10ms CPU limit.

## The 10ms Problem

Cloudflare Workers have a 10ms CPU time limit per request. Schema operations (CREATE TABLE, indexes) can easily consume 5-10ms, making runtime schema checking impractical.

## Recommended Deployment Strategy

### 🏆 **Production: Pre-deployment SQL Generation**

Generate schema at build time and deploy before your worker:

```bash
# 1. Generate schema from your models
python -m kinglet.orm_deploy generate myapp.models > schema.sql

# 2. Deploy schema to D1
npx wrangler d1 execute DB --file=schema.sql --remote

# 3. Deploy worker
npx wrangler deploy
```

**Why this is best:**
- **Zero runtime overhead** - No CPU time wasted on schema checks
- **Predictable deployments** - Schema ready before first request
- **CI/CD friendly** - Easy to automate in GitHub Actions
- **Version control** - Schema changes tracked in git

### 🛠️ **Development: Migration Endpoint**

For development and staging, use a one-time migration endpoint:

```python
from kinglet import SchemaManager
from myapp.models import Game, User

@app.post("/api/_migrate")
async def migrate(request):
    # Secure with token
    if request.header("X-Migration-Token") != request.env.MIGRATION_TOKEN:
        return {"error": "Unauthorized"}, 401
    
    models = [Game, User]
    results = await SchemaManager.migrate_all(request.env.DB, models)
    return {"migrated": results}
```

```bash
# Call once after deployment
curl -X POST https://your-app.workers.dev/api/_migrate \
     -H "X-Migration-Token: secret-token"
```

### ❌ **Never: Runtime Schema Checking**

```python
# DON'T DO THIS - Too expensive!
@app.on_startup
async def ensure_tables(env):
    # This will consume 5-10ms on EVERY cold start
    await create_tables_if_not_exists(env.DB)  # BAD!
```

## Complete Deployment Pipeline

### GitHub Actions Example

```yaml
name: Deploy Kinglet App

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: |
          pip install kinglet
          npm install wrangler
      
      - name: Generate schema
        run: |
          python -m kinglet.orm_deploy generate app.models > schema.sql
          cat schema.sql  # Log for debugging
      
      - name: Deploy schema to D1
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: |
          npx wrangler d1 execute DB --file=schema.sql --remote
      
      - name: Deploy worker
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: |
          npx wrangler deploy
```

### Local Development Flow

```bash
# 1. Create local D1 database
npx wrangler d1 create my-app-db --local

# 2. Generate and apply schema
python -m kinglet.orm_deploy generate app.models > schema.sql
npx wrangler d1 execute my-app-db --file=schema.sql --local

# 3. Run dev server
npx pywrangler dev
```

## Schema Evolution

### Adding a New Field

```python
# 1. Add field to model
class Game(Model):
    title = StringField(max_length=200)
    high_score = IntegerField(default=0)  # NEW FIELD
```

```sql
-- 2. Generate migration SQL
ALTER TABLE games ADD COLUMN high_score INTEGER DEFAULT 0;
```

```bash
# 3. Apply migration
npx wrangler d1 execute DB --command="ALTER TABLE games ADD COLUMN high_score INTEGER DEFAULT 0" --remote
```

### Complex Migrations

For complex migrations, use D1's batch capabilities:

```python
@app.post("/api/_migrate_v2")
async def migrate_v2(request):
    # Add new column
    await request.env.DB.exec("""
        ALTER TABLE games ADD COLUMN category TEXT;
        CREATE INDEX idx_games_category ON games(category);
    """)
    
    # Backfill data
    await request.env.DB.prepare("""
        UPDATE games 
        SET category = json_extract(metadata, '$.genre')
        WHERE metadata IS NOT NULL
    """).run()
    
    return {"status": "migrated to v2"}
```

## Performance Comparison

| Approach | First Request | Subsequent | Pros | Cons |
|----------|--------------|------------|------|------|
| **Pre-deploy SQL** | 0ms | 0ms | Zero overhead, predictable | Extra deploy step |
| **Migration endpoint** | 0ms* | 0ms | Flexible, convenient | Requires secure endpoint |
| **Runtime checking** | 5-10ms | 5-10ms | "Automatic" | Wastes CPU on every cold start |

\* *Assuming migration endpoint called separately*

## Best Practices

1. **Always pre-deploy schema for production**
   - Include in your CI/CD pipeline
   - Version control your schema.sql files

2. **Use migration endpoints for development only**
   - Secure with strong tokens
   - Consider IP restrictions for extra security

3. **Never check schema on every request**
   - Workers cold-start frequently
   - 10ms CPU limit is precious

4. **Plan for schema evolution**
   - Keep migration scripts in version control
   - Test migrations on preview deployments first

5. **Monitor schema operations**
   - Log migration attempts
   - Track schema version in KV if needed

## Quick Start Template

```bash
# Create this as setup.sh in your project
#!/bin/bash

# Generate schema
echo "Generating schema..."
python -c "
from app.models import *
from kinglet.orm import SchemaManager
sql = SchemaManager.generate_schema_sql([Game, User, Session])
print(sql)
" > schema.sql

# Deploy based on environment
if [ "$1" == "production" ]; then
    echo "Deploying to production..."
    npx wrangler d1 execute DB --file=schema.sql --remote
    npx wrangler deploy --env production
else
    echo "Deploying to development..."
    npx wrangler d1 execute DB --file=schema.sql --local
    npx pywrangler dev
fi
```

## Quick Start

### 1. Define Models

```python
from kinglet import Model, StringField, IntegerField, BooleanField, DateTimeField

class Game(Model):
    title = StringField(max_length=200, null=False)
    score = IntegerField(default=0)
    is_published = BooleanField(default=False)
    created_at = DateTimeField(auto_now_add=True)
    
    class Meta:
        table_name = "games"
```

### 2. Deploy Schema

```bash
# Generate SQL
python -m kinglet.orm_deploy generate myapp.models > schema.sql

# Deploy to D1
npx wrangler d1 execute DB --file=schema.sql --remote

# Create lock file for tracking
python -m kinglet.orm_deploy lock myapp.models
```

### 3. Use in Worker

```python
@app.post("/games")
async def create_game(request):
    game = await Game.objects.create(
        request.env.DB,
        title="New Game",
        score=100
    )
    return game.to_dict()

@app.get("/games")
async def list_games(request):
    games = await Game.objects.filter(
        request.env.DB,
        is_published=True
    ).order_by("-score").limit(10).all()
    return {"games": [g.to_dict() for g in games]}
```

## Migration Workflow

### Track Changes

```bash
# After model changes
python -m kinglet.orm_deploy verify myapp.models  # Check for changes
python -m kinglet.orm_deploy migrate myapp.models > migration.sql
npx wrangler d1 execute DB --file=migration.sql --remote
python -m kinglet.orm_deploy lock myapp.models  # Update lock
```

### Migration Tracking

The ORM uses:
- `schema.lock.json` - Git-tracked schema version
- `_kinglet_migrations` table - Applied migrations in D1

## Performance

| Operation | SQL Queries | D1 Efficiency |
|-----------|------------|---------------|
| `create()` | 1 INSERT | ✅ Optimal |
| `filter().all()` | 1 SELECT | ✅ Optimal |
| `bulk_create([...])` | 1 BATCH | ✅ Better than raw SQL |
| `filter().update()` | 1 UPDATE | ✅ Optimal |
| `filter().delete()` | 1 DELETE | ✅ Optimal |

## Field Types

- `StringField(max_length=200)`
- `IntegerField(default=0)`
- `BooleanField(default=False)`
- `DateTimeField(auto_now_add=True)`
- `JSONField(default=dict)`

## Query API

```python
# Filtering
.filter(score__gte=90)  # >=
.filter(title__contains="game")  # LIKE
.filter(is_published=True)

# Ordering
.order_by("-created_at")  # DESC
.order_by("score", "-created_at")  # Multiple

# Pagination
.limit(10).offset(20)

# Aggregation
.count()  # Returns count directly
```

## Summary

- **Production:** Pre-deploy SQL with `wrangler d1 execute`
- **Development:** Migration endpoint or local SQL file
- **Never:** Runtime schema checking in Workers

The ORM provides Django-like convenience with zero overhead vs raw SQL, specifically optimized for D1 and Workers constraints.