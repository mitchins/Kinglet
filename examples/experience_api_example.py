#!/usr/bin/env python3
"""
Experience API Example - Demonstrates Kinglet's cache-aside, media URLs, and validation
Based on real-world LibrePlay implementation patterns
"""

import json
import time
import uuid

from kinglet import (
    Kinglet,
    Response,
    TestClient,
    cache_aside,
    media_url,
    require_dev,
    require_field,
    validate_json_body,
)

# Mock data for demo
GAMES_DATA = [
    {
        "id": 1,
        "title": "Epic Adventure",
        "genre": "action",
        "rating": 4.8,
        "cover_uid": "abc-123",
    },
    {
        "id": 2,
        "title": "Puzzle Master",
        "genre": "puzzle",
        "rating": 4.6,
        "cover_uid": "def-456",
    },
    {
        "id": 3,
        "title": "Space Colony",
        "genre": "strategy",
        "rating": 4.9,
        "cover_uid": "ghi-789",
    },
]

MEDIA_STORAGE = {}  # Mock R2 storage


# Create app with debug mode for examples
app = Kinglet(debug=True, root_path="/api")


# === EXPERIENCE API WITH CACHING ===


@app.get("/homepage")
@cache_aside(cache_type="homepage", ttl=3600)  # Cache for 1 hour
async def get_homepage(request):
    """Homepage Experience API - cached R2 response"""
    print("🔄 Generating fresh homepage data...")

    # Simulate database queries
    featured_games = [g for g in GAMES_DATA if g["rating"] > 4.7]
    latest_games = GAMES_DATA[-2:]  # Last 2 games

    # Generate media URLs for covers
    for game in featured_games + latest_games:
        game["cover_url"] = media_url(request, game["cover_uid"])

    return {
        "featured_games": featured_games,
        "latest_games": latest_games,
        "generated_at": time.time(),
        "source": "kinglet_experience_api",
    }


@app.get("/games")
@cache_aside(cache_type="games_list", ttl=1800)  # Cache for 30 minutes
async def list_games(request):
    """Games list with filtering - cached by query parameters"""
    genre_filter = request.query("genre", "").lower()
    limit = request.query_int("limit", 10)

    print(f"🔄 Generating games list: genre={genre_filter}, limit={limit}")

    # Filter games
    games = GAMES_DATA
    if genre_filter:
        games = [g for g in games if g["genre"] == genre_filter]

    games = games[:limit]

    # Add media URLs
    for game in games:
        game["cover_url"] = media_url(request, game["cover_uid"])

    return {
        "games": games,
        "filters": {"genre": genre_filter, "limit": limit},
        "total": len(games),
        "generated_at": time.time(),
    }


# === MEDIA MANAGEMENT ===


@app.post("/media")
async def upload_media(request):
    """Upload media and return UID - demonstrates media_url usage"""
    # Simulate file upload
    media_uid = str(uuid.uuid4())

    # Store in mock storage
    MEDIA_STORAGE[media_uid] = {
        "uploaded_at": time.time(),
        "size": 1024 * 50,  # 50KB
    }

    return {
        "success": True,
        "uid": media_uid,
        "url": media_url(request, media_uid),
        "message": "Upload complete",
    }


@app.get("/media/{uid}")
async def get_media(request):
    """Get media by UID - demonstrates URL generation"""
    uid = request.path_param("uid")

    if uid not in MEDIA_STORAGE:
        return Response.error("Media not found", 404)

    media_info = MEDIA_STORAGE[uid]

    return {"uid": uid, "url": media_url(request, uid), "metadata": media_info}


# === GAME DETAIL WITH DYNAMIC PATH CACHING ===


@app.get("/games/{slug}")
@cache_aside(cache_type="game_detail", ttl=1800)  # Cache each game separately
async def get_game_detail(request):
    """Game detail page - cached per game slug"""
    slug = request.path_param("slug")

    print(f"🔄 Generating game detail for: {slug}")

    # Find game by slug (simulate database lookup)
    game = None
    for g in GAMES_DATA:
        if g["title"].lower().replace(" ", "-") == slug:
            game = g.copy()  # Copy to avoid modifying original
            break

    if not game:
        return Response.error("Game not found", 404)

    # Add detailed info
    game["description"] = f"An amazing {game['genre']} game with epic gameplay!"
    game["screenshots"] = [
        media_url(request, f"{game['cover_uid']}-screenshot1"),
        media_url(request, f"{game['cover_uid']}-screenshot2"),
    ]
    game["cover_url"] = media_url(request, game["cover_uid"])
    game["generated_at"] = time.time()

    return {"game": game, "source": "kinglet_game_detail_cached"}


# === ADMIN ENDPOINTS WITH VALIDATION ===


@app.post("/admin/games")
@require_dev()  # Only in development
@validate_json_body
@require_field("title", str)
@require_field("genre", str)
@require_field("rating", (int, float))
async def create_game(request):
    """Create new game - demonstrates validation decorators"""
    data = await request.json()

    new_game = {
        "id": len(GAMES_DATA) + 1,
        "title": data["title"],
        "genre": data["genre"],
        "rating": data["rating"],
        "cover_uid": str(uuid.uuid4()),
        "created_at": time.time(),
    }

    # Add media URL
    new_game["cover_url"] = media_url(request, new_game["cover_uid"])

    # Add to mock data
    GAMES_DATA.append(new_game)

    return {"success": True, "game": new_game, "message": "Game created successfully"}


@app.put("/admin/games/{game_id}")
@require_dev()
@validate_json_body
async def update_game(request):
    """Update game - demonstrates path parameters with validation"""
    game_id = request.path_param_int("game_id")
    data = await request.json()

    # Find game
    game = None
    for g in GAMES_DATA:
        if g["id"] == game_id:
            game = g
            break

    if not game:
        return Response.error("Game not found", 404)

    # Update fields
    if "title" in data:
        game["title"] = data["title"]
    if "rating" in data:
        game["rating"] = data["rating"]

    game["updated_at"] = time.time()
    game["cover_url"] = media_url(request, game["cover_uid"])

    return {"success": True, "game": game, "message": "Game updated successfully"}


# === CACHE MANAGEMENT ===


@app.delete("/admin/cache/{cache_type}")
@require_dev()
async def clear_cache(request):
    """Clear specific cache type - demonstrates cache management"""
    cache_type = request.path_param("cache_type")

    # In real implementation, this would clear from R2
    return {
        "success": True,
        "cache_type": cache_type,
        "message": f"Cache '{cache_type}' cleared",
        "timestamp": time.time(),
    }


# === EXAMPLE USAGE ===

if __name__ == "__main__":
    # Create test environment with R2 storage binding
    mock_storage = {}

    class MockR2:
        async def get(self, key):
            return mock_storage.get(key)

        async def put(self, key, content, metadata=None):
            mock_storage[key] = content

    test_env = {
        "STORAGE": MockR2(),
        "ENVIRONMENT": "development",
        "CDN_BASE_URL": None,  # Will use auto-detected URLs
    }

    client = TestClient(app, env=test_env)

    print("🧪 Testing Experience API with Caching...\n")

    # Test homepage (cache miss)
    print("1️⃣ Homepage - First Request (Cache Miss)")
    status, headers, body = client.request("GET", "/api/homepage")
    data = json.loads(body)
    print(f"Status: {status}")
    print(f"Cache Hit: {data.get('_cache_hit', 'N/A')}")
    print(f"Featured Games: {len(data.get('featured_games', []))}")
    print()

    # Test homepage again (cache hit)
    print("2️⃣ Homepage - Second Request (Cache Hit)")
    status, headers, body = client.request("GET", "/api/homepage")
    data = json.loads(body)
    print(f"Status: {status}")
    print(f"Cache Hit: {data.get('_cache_hit', 'N/A')}")
    print()

    # Test games list with filters
    print("3️⃣ Games List with Genre Filter")
    status, headers, body = client.request("GET", "/api/games?genre=action&limit=5")
    data = json.loads(body)
    print(f"Status: {status}")
    print(f"Games Found: {data.get('total', 0)}")
    print(f"Cache Hit: {data.get('_cache_hit', 'N/A')}")
    if data.get("games"):
        print(f"First Game URL: {data['games'][0].get('cover_url', 'N/A')}")
    print()

    # Test media upload
    print("4️⃣ Media Upload")
    status, headers, body = client.request("POST", "/api/media")
    data = json.loads(body)
    print(f"Status: {status}")
    print(f"Media UID: {data.get('uid', 'N/A')}")
    print(f"Media URL: {data.get('url', 'N/A')}")
    print()

    # Test game creation with validation
    print("5️⃣ Game Creation (With Validation)")
    game_data = {"title": "New Racing Game", "genre": "racing", "rating": 4.7}
    status, headers, body = client.request("POST", "/api/admin/games", json=game_data)
    data = json.loads(body)
    print(f"Status: {status}")
    if status == 200:
        print(f"Created: {data.get('game', {}).get('title', 'N/A')}")
        print(f"Cover URL: {data.get('game', {}).get('cover_url', 'N/A')}")
    print()

    # Test validation error
    print("6️⃣ Validation Error Test")
    bad_data = {"title": "Missing Genre"}  # Missing required 'genre' field
    status, headers, body = client.request("POST", "/api/admin/games", json=bad_data)
    data = json.loads(body)
    print(f"Status: {status}")
    print(f"Error: {data.get('error', 'N/A')}")
    print()

    # Test dynamic path caching
    print("7️⃣ Dynamic Path Caching - Game Detail")
    status, headers, body = client.request("GET", "/api/games/epic-adventure")
    data = json.loads(body)
    print(f"Status: {status}")
    print(f"Game: {data.get('game', {}).get('title', 'N/A')}")
    print(f"Cache Hit: {data.get('_cache_hit', 'N/A')}")
    print()

    # Same game should hit cache
    print("8️⃣ Same Game Detail (Cache Hit)")
    status, headers, body = client.request("GET", "/api/games/epic-adventure")
    data = json.loads(body)
    print(f"Status: {status}")
    print(f"Cache Hit: {data.get('_cache_hit', 'N/A')}")
    print()

    # Different game should be cache miss
    print("9️⃣ Different Game Detail (Cache Miss)")
    status, headers, body = client.request("GET", "/api/games/puzzle-master")
    data = json.loads(body)
    print(f"Status: {status}")
    print(f"Game: {data.get('game', {}).get('title', 'N/A')}")
    print(f"Cache Hit: {data.get('_cache_hit', 'N/A')}")
    print()

    print("✅ All tests completed! Check the output above.")
    print("\n💡 Key Features Demonstrated:")
    print("   • @cache_aside decorator with R2 storage")
    print("   • Dynamic path caching (/games/{slug} cached per slug)")
    print("   • Environment-aware media_url() generation")
    print("   • @validate_json_body for request validation")
    print("   • @require_field() for typed field validation")
    print("   • @require_dev() for development-only endpoints")
