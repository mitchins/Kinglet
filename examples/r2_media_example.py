"""
R2 Media Example - Binary file serving with Kinglet

This example shows how to serve binary files from Cloudflare R2 storage,
demonstrating the key technique of returning WorkersResponse with streams.

Key Points:
1. Import WorkersResponse from workers package
2. Return obj.body (R2 stream) directly - NOT bytes or ArrayBuffer
3. Kinglet automatically passes WorkersResponse through without processing
"""

from kinglet import Kinglet, Router
from workers import Response as WorkersResponse

app = Kinglet()
router = Router()

@router.post("/media")
async def upload_media(request):
    """Upload binary content to R2"""
    import uuid
    
    # Get raw binary data
    raw_req = getattr(request, "_raw", None)
    if raw_req and hasattr(raw_req, "arrayBuffer"):
        from js import Uint8Array, ArrayBuffer
        buf = await raw_req.arrayBuffer()
        # Convert to ArrayBuffer for R2 upload
        size = buf.byteLength
        
        # Generate unique ID
        media_id = str(uuid.uuid4())
        
        # Upload to R2 (assumes R2 binding named STORAGE)
        await request.env.STORAGE.put(media_id, buf, {
            "httpMetadata": {"contentType": "application/octet-stream"}
        })
        
        return {"success": True, "id": media_id, "size": size}
    
    return {"error": "No binary data provided"}

@router.get("/media/{media_id}")
async def get_media(request):
    """Serve binary content from R2 - The key technique"""
    media_id = request.path_param("media_id")
    
    # Fetch from R2
    obj = await request.env.STORAGE.get(media_id)
    if not obj:
        return {"error": "Not found"}, 404
    
    # Extract content type
    content_type = "application/octet-stream"
    try:
        if hasattr(obj, 'httpMetadata') and obj.httpMetadata:
            content_type = getattr(obj.httpMetadata, 'contentType', content_type)
    except:
        pass
    
    headers = {
        "Content-Type": content_type,
        "Cache-Control": "public, max-age=3600"
    }
    
    # KEY: Return obj.body (R2 stream) to WorkersResponse
    # - obj.body is a ReadableStream that Workers can pipe directly
    # - Do NOT convert to bytes (causes TypeError)
    # - Kinglet detects WorkersResponse and passes through without processing
    return WorkersResponse(obj.body, status=200, headers=headers)

app.include_router("/api", router)

# Workers entry point
async def on_fetch(request, env):
    return await app(request, env)