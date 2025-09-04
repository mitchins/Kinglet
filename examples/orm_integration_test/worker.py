"""
Kinglet ORM Integration Test & Demo

This is a complete integration test that demonstrates the micro-ORM
running in a real Cloudflare Workers environment with D1 database.

Run with:
  cd examples/orm_integration_test
  uv sync
  npx pywrangler dev
"""

from kinglet import (
    BooleanField,
    CorsMiddleware,
    DateTimeField,
    IntegerField,
    JSONField,
    Kinglet,
    Model,
    SchemaManager,
    StringField,
)

app = Kinglet()
app.add_middleware(CorsMiddleware(allow_origin="*"))


# Test models
class Game(Model):
    title = StringField(max_length=200, null=False)
    description = StringField()
    score = IntegerField(default=0)
    is_published = BooleanField(default=False)
    created_at = DateTimeField(auto_now_add=True)
    metadata = JSONField(default=dict)

    class Meta:
        table_name = "games"


class User(Model):
    email = StringField(max_length=255, unique=True, null=False)
    username = StringField(max_length=50, null=False)
    is_active = BooleanField(default=True)
    joined_at = DateTimeField(auto_now_add=True)
    profile = JSONField(default=dict)

    class Meta:
        table_name = "users"


# Migration endpoint (secured with token)
@app.post("/migrate")
async def migrate_database(request):
    """Initialize database schema"""
    # Simple security - in production use proper auth
    auth_header = request.header("Authorization", "")
    expected_token = request.env.get("MIGRATION_TOKEN", "dev-secret-123")

    if auth_header != f"Bearer {expected_token}":
        return {"error": "Unauthorized"}, 401

    models = [Game, User]
    results = await SchemaManager.migrate_all(request.env.DB, models)

    return {
        "status": "migration_complete",
        "results": results,
        "models": [model.__name__ for model in models],
    }


@app.get("/schema")
async def get_schema_sql(request):
    """Get schema SQL for manual setup"""
    models = [Game, User]
    sql = SchemaManager.generate_schema_sql(models)

    return {
        "schema_sql": sql,
        "instructions": {
            "wrangler": 'npx wrangler d1 execute TEST_DB --command="'
            + sql.replace('"', '\\"')
            + '"',
            "curl": f"curl -X POST http://localhost:8787/migrate -H 'Authorization: Bearer {request.env.get('MIGRATION_TOKEN', 'dev-secret-123')}'",
        },
    }


# Demo CRUD endpoints
@app.post("/games")
async def create_game(request):
    """Create a game - validates fields automatically"""
    try:
        data = await request.json()

        game = await Game.objects.create(
            request.env.DB,
            title=data["title"],
            description=data.get("description", ""),
            score=data.get("score", 0),
            is_published=data.get("is_published", False),
            metadata=data.get("metadata", {}),
        )

        return {"success": True, "game": game.to_dict()}
    except ValueError as e:
        return {"error": f"Validation error: {e}"}, 400
    except Exception as e:
        return {"error": f"Database error: {e}"}, 500


@app.get("/games")
async def list_games(request):
    """List games with optional filtering"""
    try:
        # Build query with field validation
        queryset = Game.objects.all(request.env.DB)

        # Optional filters (demonstrates field validation)
        if request.query("published"):
            published = request.query_bool("published")
            queryset = queryset.filter(is_published=published)

        if request.query("min_score"):
            min_score = request.query_int("min_score")
            queryset = queryset.filter(score__gte=min_score)

        if request.query("search"):
            search = request.query("search")
            queryset = queryset.filter(title__icontains=search)

        # Pagination
        limit = request.query_int("limit", 10)
        offset = request.query_int("offset", 0)

        # Execute query
        games = await queryset.order_by("-created_at").limit(limit).offset(offset).all()
        total = await Game.objects.all(request.env.DB).count()

        return {
            "games": [game.to_dict() for game in games],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except ValueError as e:
        return {"error": f"Query error: {e}"}, 400


@app.get("/games/{game_id}")
async def get_game(request):
    """Get specific game"""
    try:
        game_id = request.path_param_int("game_id")
        game = await Game.objects.get(request.env.DB, id=game_id)

        if not game:
            return {"error": "Game not found"}, 404

        return {"game": game.to_dict()}
    except ValueError as e:
        return {"error": f"Invalid game ID: {e}"}, 400


@app.put("/games/{game_id}")
async def update_game(request):
    """Update game"""
    try:
        game_id = request.path_param_int("game_id")
        data = await request.json()

        game = await Game.objects.get(request.env.DB, id=game_id)
        if not game:
            return {"error": "Game not found"}, 404

        # Update with field validation
        for field in ["title", "description", "score", "is_published", "metadata"]:
            if field in data:
                setattr(game, field, data[field])

        await game.save(request.env.DB)

        return {"game": game.to_dict()}
    except ValueError as e:
        return {"error": f"Validation error: {e}"}, 400


@app.delete("/games/{game_id}")
async def delete_game(request):
    """Delete game"""
    try:
        game_id = request.path_param_int("game_id")
        game = await Game.objects.get(request.env.DB, id=game_id)

        if not game:
            return {"error": "Game not found"}, 404

        await game.delete(request.env.DB)
        return {"success": True}
    except ValueError as e:
        return {"error": f"Invalid game ID: {e}"}, 400


@app.post("/users")
async def create_user(request):
    """Create user with uniqueness validation"""
    try:
        data = await request.json()

        # Check uniqueness manually (ORM doesn't enforce DB constraints yet)
        existing = await User.objects.get(request.env.DB, email=data["email"])
        if existing:
            return {"error": "Email already exists"}, 400

        user = await User.objects.create(
            request.env.DB,
            email=data["email"],
            username=data["username"],
            profile=data.get("profile", {}),
        )

        return {"success": True, "user": user.to_dict()}
    except ValueError as e:
        return {"error": f"Validation error: {e}"}, 400


@app.get("/users")
async def list_users(request):
    """List users"""
    try:
        active_only = request.query_bool("active", True)

        queryset = User.objects.all(request.env.DB)
        if active_only:
            queryset = queryset.filter(is_active=True)

        users = await queryset.order_by("-joined_at").limit(50).all()

        return {"users": [user.to_dict() for user in users], "count": len(users)}
    except Exception as e:
        return {"error": str(e)}, 500


@app.get("/stats")
async def get_stats(request):
    """Get database statistics - demonstrates count queries"""
    try:
        stats = {
            "games": {
                "total": await Game.objects.all(request.env.DB).count(),
                "published": await Game.objects.filter(
                    request.env.DB, is_published=True
                ).count(),
            },
            "users": {
                "total": await User.objects.all(request.env.DB).count(),
                "active": await User.objects.filter(
                    request.env.DB, is_active=True
                ).count(),
            },
        }

        return {"stats": stats}
    except Exception as e:
        return {"error": str(e)}, 500


# Demo data endpoints
@app.post("/demo/seed")
async def seed_demo_data(request):
    """Seed database with demo data - demonstrates bulk operations"""
    try:
        # D1 Optimization: Use bulk_create for efficient batch INSERTs
        games_data = [
            {
                "title": "Space Adventure",
                "description": "Explore the galaxy",
                "score": 95,
                "is_published": True,
                "metadata": {"genre": "adventure", "platform": "web"},
            },
            {
                "title": "Puzzle Master",
                "description": "Mind-bending puzzles",
                "score": 88,
                "is_published": True,
                "metadata": {"genre": "puzzle", "difficulty": "hard"},
            },
            {
                "title": "Racing Thunder",
                "description": "High-speed racing",
                "score": 92,
                "is_published": False,
                "metadata": {"genre": "racing", "multiplayer": True},
            },
            {
                "title": "Strategy Empire",
                "description": "Build your empire",
                "score": 90,
                "is_published": True,
                "metadata": {"genre": "strategy", "turns": "unlimited"},
            },
            {
                "title": "Retro Arcade",
                "description": "Classic arcade games",
                "score": 85,
                "is_published": True,
                "metadata": {"genre": "arcade", "difficulty": "medium"},
            },
            {
                "title": "Mystery Quest",
                "description": "Solve the mystery",
                "score": 93,
                "is_published": True,
                "metadata": {"genre": "mystery", "chapters": 12},
            },
        ]

        # Create game instances (not saved yet)
        game_instances = [Game(**game_data) for game_data in games_data]

        # Bulk create - single batch operation instead of multiple INSERTs
        created_games = await Game.objects.bulk_create(request.env.DB, game_instances)

        # Create demo users (check uniqueness first)
        users_data = [
            {
                "email": "alice@example.com",
                "username": "alice_gamer",
                "profile": {
                    "level": 15,
                    "achievements": ["first_win", "puzzle_master"],
                },
            },
            {
                "email": "bob@example.com",
                "username": "bob_racer",
                "profile": {"level": 8, "achievements": ["speed_demon"]},
            },
            {
                "email": "carol@example.com",
                "username": "carol_strategist",
                "profile": {
                    "level": 22,
                    "achievements": ["empire_builder", "master_tactician"],
                },
            },
            {
                "email": "dave@example.com",
                "username": "dave_puzzler",
                "profile": {"level": 12, "achievements": ["brain_teaser"]},
            },
        ]

        # Check existing users first, then bulk create new ones
        user_instances = []
        for user_data in users_data:
            existing = await User.objects.get(request.env.DB, email=user_data["email"])
            if not existing:
                user_instances.append(User(**user_data))

        created_users = []
        if user_instances:
            created_users = await User.objects.bulk_create(
                request.env.DB, user_instances
            )

        return {
            "success": True,
            "created": {"games": len(created_games), "users": len(created_users)},
            "games": [g.to_dict() for g in created_games],
            "users": [u.to_dict() for u in created_users],
            "optimization": "Used bulk_create for efficient D1 batch operations",
        }
    except Exception as e:
        return {"error": str(e)}, 500


@app.get("/demo/test-queries")
async def test_queries(request):
    """Demonstrate various query capabilities and D1 optimizations"""
    try:
        results = {}

        # D1 Optimization: Use count() instead of len(all()) - single COUNT(*) query
        results["published_games"] = await Game.objects.filter(
            request.env.DB, is_published=True
        ).count()
        results["high_score_games"] = await Game.objects.filter(
            request.env.DB, score__gte=90
        ).count()
        results["adventure_games"] = await Game.objects.filter(
            request.env.DB, title__icontains="adventure"
        ).count()
        results["active_users"] = await User.objects.filter(
            request.env.DB, is_active=True
        ).count()

        # Test efficient ordering and limiting
        top_games = (
            await Game.objects.all(request.env.DB).order_by("-score").limit(3).all()
        )
        results["top_games"] = [{"title": g.title, "score": g.score} for g in top_games]

        return {
            "test_results": results,
            "optimization": "Used count() queries instead of len(all()) for efficiency",
        }
    except Exception as e:
        return {"error": str(e)}, 500


@app.post("/demo/bulk-update")
async def demo_bulk_update(request):
    """Demonstrate bulk update operations"""
    try:
        data = await request.json()
        score_boost = data.get("score_boost", 10)

        # D1 Optimization: Single UPDATE query instead of multiple individual updates
        updated_count = await Game.objects.filter(
            request.env.DB, is_published=True, score__lt=95
        ).update(score=score_boost)

        return {
            "success": True,
            "updated_count": updated_count,
            "optimization": "Single UPDATE query with WHERE clause - much more efficient than individual updates",
        }
    except Exception as e:
        return {"error": str(e)}, 500


@app.post("/demo/bulk-delete")
async def demo_bulk_delete(request):
    """Demonstrate bulk delete operations"""
    try:
        # D1 Optimization: Single DELETE query with WHERE clause
        deleted_count = await Game.objects.filter(
            request.env.DB, is_published=False, score__lt=80
        ).delete()

        return {
            "success": True,
            "deleted_count": deleted_count,
            "optimization": "Single DELETE query with WHERE clause - much more efficient than individual deletes",
        }
    except Exception as e:
        return {"error": str(e)}, 500


# Health check endpoint
@app.get("/")
async def health_check(request):
    """Health check and API info"""
    return {
        "service": "Kinglet ORM Integration Test",
        "status": "healthy",
        "endpoints": {
            "POST /migrate": "Initialize database schema",
            "GET /schema": "Get schema SQL",
            "POST /games": "Create game",
            "GET /games": "List games (supports ?published, ?min_score, ?search, ?limit, ?offset)",
            "GET /games/{id}": "Get specific game",
            "PUT /games/{id}": "Update game",
            "DELETE /games/{id}": "Delete game",
            "POST /users": "Create user",
            "GET /users": "List users (supports ?active)",
            "GET /stats": "Database statistics",
            "POST /demo/seed": "Seed demo data (uses bulk_create)",
            "GET /demo/test-queries": "Test query capabilities (optimized for D1)",
            "POST /demo/bulk-update": "Bulk update demo (single UPDATE query)",
            "POST /demo/bulk-delete": "Bulk delete demo (single DELETE query)",
        },
        "setup": {
            "1": "POST /migrate with Authorization: Bearer dev-secret-123",
            "2": "POST /demo/seed to create sample data",
            "3": "GET /games to see results",
        },
    }


# Workers entry point
async def on_fetch(request, env):
    return await app(request, env)
