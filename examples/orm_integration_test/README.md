# ORM Integration Test

Live demo of Kinglet ORM with D1 database. Tests all ORM features including migrations, bulk operations, and field validation.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [pywrangler](https://github.com/cloudflare/pywrangler) (Cloudflare Workers Python runtime)
- Cloudflare account with D1 access

## Setup

1. **Install dependencies:**
   ```bash
   cd examples/orm_integration_test
   uv sync
   ```

2. **Create D1 database:**
   ```bash
   npx wrangler d1 create kinglet-orm-test
   ```

3. **Update wrangler.toml:**
   - Replace `database_id` and `preview_database_id` with values from step 2

4. **Start development server:**
   ```bash
   npx pywrangler dev
   ```

5. **Initialize database schema:**
   ```bash
   curl -X POST http://localhost:8787/migrate \
     -H "Authorization: Bearer dev-secret-123"
   ```

6. **Seed demo data:**
   ```bash
   curl -X POST http://localhost:8787/demo/seed
   ```

## Test the ORM

### Basic Operations

```bash
# Get health check and API info
curl http://localhost:8787/

# List games (empty initially)
curl http://localhost:8787/games

# Create a game
curl -X POST http://localhost:8787/games \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Game",
    "description": "A test game",
    "score": 85,
    "is_published": true,
    "metadata": {"genre": "action", "platform": "web"}
  }'

# List games again (should show the new game)
curl http://localhost:8787/games

# Filter published games only
curl "http://localhost:8787/games?published=true"

# Filter by minimum score
curl "http://localhost:8787/games?min_score=90"

# Search games
curl "http://localhost:8787/games?search=adventure"

# Get specific game
curl http://localhost:8787/games/1

# Update a game
curl -X PUT http://localhost:8787/games/1 \
  -H "Content-Type: application/json" \
  -d '{"score": 95, "is_published": true}'

# Create a user
curl -X POST http://localhost:8787/users \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "username": "test_user",
    "profile": {"level": 5, "achievements": ["first_game"]}
  }'

# List users
curl http://localhost:8787/users

# Get statistics
curl http://localhost:8787/stats
```

### Advanced Query Testing

```bash
# Test various query capabilities
curl http://localhost:8787/demo/test-queries

# Pagination
curl "http://localhost:8787/games?limit=2&offset=0"
curl "http://localhost:8787/games?limit=2&offset=2"
```

### Error Handling

```bash
# Try invalid field (should return validation error)
curl -X POST http://localhost:8787/games \
  -H "Content-Type: application/json" \
  -d '{"title": "", "invalid_field": "test"}'

# Try duplicate user email
curl -X POST http://localhost:8787/users \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "username": "duplicate"}'
```

## ORM Features Demonstrated

### 1. **Field Validation**
- String length validation
- Required field validation
- Type conversion and validation
- Prevents SQL errors through early validation

### 2. **Query Building**
- Field existence validation
- Lookup operators (`__gt`, `__gte`, `__lt`, `__lte`, `__contains`, `__icontains`, etc.)
- Ordering with validation
- Pagination with LIMIT/OFFSET

### 3. **Schema Management**
- Automatic table creation
- SQL generation for wrangler deployment
- Migration endpoint for development

### 4. **D1 Optimizations**
- Prepared statement usage
- Efficient result unwrapping
- Minimal CPU overhead during requests

### 5. **Compute Constraints**
- Pre-validated queries to prevent runtime errors
- Cached field metadata for fast validation
- Minimal reflection/introspection

## Performance Testing

The ORM is optimized for Cloudflare Workers' compute constraints:

```bash
# Create multiple games to test performance
for i in {1..10}; do
  curl -X POST http://localhost:8787/games \
    -H "Content-Type: application/json" \
    -d "{\"title\": \"Perf Test Game $i\", \"score\": $((RANDOM % 100))}"
done

# Test query performance
time curl "http://localhost:8787/games?limit=50"
time curl http://localhost:8787/stats
```

## Cleanup

```bash
# Delete the D1 database
npx wrangler d1 delete kinglet-orm-test
```

## Key Differences from Traditional ORMs

1. **Compute Optimized:** Minimal CPU usage during request processing
2. **Field Validation:** Prevents SQL errors through early validation
3. **D1 Specific:** Built for Cloudflare D1's unique characteristics
4. **Simple Migrations:** Schema generation without complex migration framework
5. **Workers Ready:** Designed for serverless constraints and cold starts