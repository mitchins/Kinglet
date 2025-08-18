"""
Kinglet 1.3.0 D1 and R2 Helpers Example

Demonstrates the new database and storage helpers that eliminate 
common boilerplate when working with Cloudflare D1 and R2.
"""

from kinglet import (
    Kinglet,
    asset_url,
    d1_unwrap,
    d1_unwrap_results,
    r2_delete,
    r2_get_content_info,
    r2_list,
    r2_put,
)

app = Kinglet()

@app.get("/api/games")
async def list_games(request):
    """Example using D1 helpers to safely unwrap database results"""

    # Before 1.3.0: Manual unwrapping with _to_py() everywhere
    # def _to_py(x):
    #     return x.to_py() if hasattr(x, "to_py") else x
    #
    # rows = []
    # for row in result.results:
    #     row_dict = _to_py(row)
    #     if not isinstance(row_dict, dict):
    #         # ... lots of defensive conversion code
    #     rows.append(row_dict)

    # After 1.3.0: Clean and simple with lazy iteration
    result = await request.env.DB.prepare("SELECT * FROM games LIMIT 10").all()
    games = list(d1_unwrap_results(result))  # Generator -> list for JSON

    return {"games": games, "count": len(games)}


@app.get("/api/games/{game_id}")
async def get_game(request):
    """Example using d1_unwrap for single results"""
    game_id = request.path_param("game_id")

    # Clean D1 result unwrapping
    result = await request.env.DB.prepare("SELECT * FROM games WHERE id = ?").bind(game_id).first()

    if not result:
        return {"error": "Game not found"}, 404

    # No more defensive _to_py() conversion needed
    game = d1_unwrap(result)

    return {"game": game}


@app.post("/api/media")
async def upload_media(request):
    """Example using R2 helpers for file upload"""

    # Get file data
    body_bytes = await request.body_bytes()
    content_type = request.header("content-type", "application/octet-stream")

    # Generate unique filename
    import uuid
    file_id = str(uuid.uuid4())

    # Before 1.3.0: Manual JS ArrayBuffer conversion
    # import js
    # ab = js.ArrayBuffer.new(len(body_bytes))
    # u8 = js.Uint8Array.new(ab)
    # u8.set(bytearray(body_bytes))
    # await request.env.STORAGE.put(file_id, ab, {
    #     "httpMetadata": {"contentType": content_type}
    # })

    # After 1.3.0: Simple one-liner
    await r2_put(request.env.STORAGE, file_id, body_bytes, content_type)

    # Generate environment-aware URL
    file_url = asset_url(request, file_id, "media")

    return {
        "success": True,
        "file_id": file_id,
        "url": file_url,
        "size": len(body_bytes)
    }


@app.get("/api/media/{file_id}")
async def get_media(request):
    """Example using R2 helpers for file metadata"""
    file_id = request.path_param("file_id")

    # Get R2 object
    obj = await request.env.STORAGE.get(file_id)
    if not obj:
        return {"error": "File not found"}, 404

    # Before 1.3.0: Defensive property access everywhere
    # content_type = "application/octet-stream"
    # try:
    #     meta = getattr(obj, "httpMetadata", None)
    #     if meta and isinstance(meta, dict):
    #         content_type = meta.get("contentType") or content_type
    #     elif meta:
    #         content_type = getattr(meta, "contentType", content_type)
    # except Exception:
    #     pass

    # After 1.3.0: Clean metadata extraction
    info = r2_get_content_info(obj)

    return {
        "file_id": file_id,
        "content_type": info["content_type"],
        "size": info["size"],
        "etag": info["etag"],
        "last_modified": info["last_modified"],
        "url": asset_url(request, file_id, "media")
    }


@app.delete("/api/media/{file_id}")
async def delete_media(request):
    """Example using R2 delete helper"""
    file_id = request.path_param("file_id")

    # Clean R2 deletion
    await r2_delete(request.env.STORAGE, file_id)

    return {"success": True, "message": f"File {file_id} deleted"}


@app.get("/api/media")
async def list_media(request):
    """Example using R2 list helper"""
    prefix = request.query("prefix", "")
    limit = request.query_int("limit", 100)

    # List R2 objects with optional prefix
    result = await r2_list(request.env.STORAGE, prefix, limit)

    # Extract file list (actual implementation depends on R2 list response format)
    files = []
    if hasattr(result, 'objects'):
        for obj in result.objects:
            files.append({
                "key": obj.key,
                "size": obj.size,
                "last_modified": obj.uploaded
            })

    return {"files": files, "prefix": prefix}


@app.get("/api/export/games")
async def export_games(request):
    """Example showing lazy iteration for large datasets"""

    # For large exports, use lazy iteration to avoid memory issues
    result = await request.env.DB.prepare("SELECT * FROM games").all()

    # Process in batches without materializing everything
    export_data = []
    batch_size = 100
    current_batch = []

    for game in d1_unwrap_results(result):  # Lazy generator
        current_batch.append({
            "id": game.get("id"),
            "title": game.get("title"),
            "export_url": asset_url(request, game.get("slug", ""), "game")
        })

        # Process in batches
        if len(current_batch) >= batch_size:
            export_data.extend(current_batch)
            current_batch = []

    # Add remaining items
    if current_batch:
        export_data.extend(current_batch)

    return {"exported_games": len(export_data), "sample": export_data[:5]}


@app.get("/api/admin/stats")
async def get_stats(request):
    """Example for small datasets - use list version"""

    # Small admin queries - OK to materialize
    tables = ["games", "users", "media"]
    stats = {}

    for table in tables:
        try:
            result = await request.env.DB.prepare(f"SELECT COUNT(*) as count FROM {table}").first()
            if result:
                data = d1_unwrap(result)  # Safe unwrapping
                stats[table] = data.get("count", 0)
        except Exception:
            stats[table] = 0

    return {
        "database_stats": stats,
        "api_base": asset_url(request, "", "api").rstrip("/"),
        "media_base": asset_url(request, "", "media").rstrip("/media/")
    }


# Workers entry point
async def on_fetch(request, env):
    return await app(request, env)


if __name__ == "__main__":
    print("Kinglet 1.3.0 D1/R2 Helpers Example")
    print("===================================")
    print()
    print("New helpers eliminate boilerplate:")
    print("• d1_unwrap() - Safe D1 proxy unwrapping")
    print("• d1_unwrap_results() - Unwrap D1 .all() results")
    print("• r2_put() - Upload with JS interop handling")
    print("• r2_get_content_info() - Extract R2 metadata")
    print("• asset_url() - Environment-aware URLs")
    print()
    print("Before: 15+ lines of defensive proxy conversion")
    print("After:  1 line with d1_unwrap(result)")
