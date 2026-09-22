"""
R2 media canary - ASGI-native binary upload/download with Kinglet.

Unlike the legacy ``r2_media_example.py`` (which passes a Workers-native
streaming response through), every byte here travels as portable Kinglet
data: ``request.bytes()`` in, ``r2_put`` bytes conversion, ``arrayBuffer()``
back out, exact bytes in a Kinglet ``Response``.
"""

import uuid

from kinglet import Kinglet, Response
from kinglet.storage import arraybuffer_to_bytes, bytes_to_arraybuffer, r2_put

app = Kinglet()


@app.post("/media", public=True)
async def upload_media(request):
    """Store raw request bytes in R2 under a fresh id."""
    data = await request.bytes()
    if not data:
        return Response({"error": "empty body"}, status=400)
    media_id = f"smoke-{uuid.uuid4().hex}"
    content_type = request.header("content-type") or "application/octet-stream"
    # Manual conversion path (httpMetadata preserved for the MIME check).
    await request.env.STORAGE.put(
        media_id,
        bytes_to_arraybuffer(data),
        {"httpMetadata": {"contentType": content_type}},
    )
    # r2_put path (bytes auto-conversion helper) exercised too:
    await r2_put(request.env.STORAGE, f"{media_id}-helper", data)
    return {"id": media_id, "size": len(data), "content_type": content_type}


@app.get("/media/{media_id}", public=True)
async def get_media(request):
    """Serve R2 bytes back exactly, with the stored MIME type."""
    media_id = request.path_param("media_id")
    obj = await request.env.STORAGE.get(media_id)
    if obj is None:
        return Response({"error": "Not found"}, status=404)
    data = arraybuffer_to_bytes(await obj.arrayBuffer())
    content_type = "application/octet-stream"
    try:
        metadata = getattr(obj, "httpMetadata", None)
        if metadata:
            content_type = (
                getattr(metadata, "contentType", content_type) or content_type
            )
    except Exception:
        pass
    return Response(bytes(data), content_type=str(content_type))


# Cloudflare Workers entry point (GA ASGI path).
try:
    from workers import asgi

    Default = asgi.entrypoint(app.asgi)
except ModuleNotFoundError:
    # Local/test context (no Workers runtime): drive `app` directly.
    Default = None
