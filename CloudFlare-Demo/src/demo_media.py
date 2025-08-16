"""
Kinglet Media Demo - R2 storage and binary file handling
"""
from kinglet import Kinglet, Response, asset_url
from kinglet import r2_get_metadata, r2_get_content_info, r2_put, r2_delete

app = Kinglet()

@app.get("/")
async def home(request):
    return {
        "demo": "Kinglet Media/R2 Demo",
        "endpoints": [
            "/upload - Upload file to R2",
            "/files - List files in R2",
            "/file/{key} - Get file from R2",
            "/delete/{key} - Delete file from R2",
            "/asset/{type}/{key} - Generate asset URL"
        ]
    }

@app.post("/upload")
async def upload_file(request):
    """Upload file to R2 bucket"""
    try:
        # Get file data from request
        form = await request.formData() if hasattr(request, 'formData') else None
        if not form:
            body = await request.json() or {}
            filename = body.get('filename', 'file.txt')
            content = body.get('content', '')
        else:
            file = form.get('file')
            filename = file.name if hasattr(file, 'name') else 'uploaded_file'
            content = await file.arrayBuffer() if hasattr(file, 'arrayBuffer') else file
        
        # Check if R2 bucket is available
        if hasattr(request.env, 'BUCKET'):
            # Upload to R2
            metadata = {"uploaded_at": str(request.request_id)}
            result = await r2_put(request.env.BUCKET, filename, content, metadata)
            
            return {
                "success": True,
                "key": filename,
                "etag": result.get('etag'),
                "size": len(content) if isinstance(content, (str, bytes)) else 0
            }
        else:
            return {
                "success": False,
                "message": "R2 bucket not configured (mock response)",
                "would_upload": filename
            }
    except Exception as e:
        return Response({"error": str(e)}, status=500)

@app.get("/files")
async def list_files(request):
    """List files in R2 bucket"""
    try:
        if hasattr(request.env, 'BUCKET'):
            # List R2 objects
            result = await request.env.BUCKET.list()
            files = []
            
            for obj in result.objects:
                metadata = r2_get_metadata(obj)
                files.append({
                    "key": obj.key,
                    "size": obj.size,
                    "uploaded": obj.uploaded.isoformat() if hasattr(obj.uploaded, 'isoformat') else str(obj.uploaded),
                    "metadata": metadata
                })
            
            return {"files": files, "count": len(files)}
        else:
            # Mock response
            return {
                "files": [
                    {"key": "demo.jpg", "size": 1024000, "type": "image/jpeg"},
                    {"key": "document.pdf", "size": 512000, "type": "application/pdf"}
                ],
                "count": 2,
                "note": "Mock data - R2 not configured"
            }
    except Exception as e:
        return Response({"error": str(e)}, status=500)

@app.get("/file/{key:path}")
async def get_file(request):
    """Get file from R2 bucket"""
    key = request.path_params.get('key')
    
    try:
        if hasattr(request.env, 'BUCKET'):
            obj = await request.env.BUCKET.get(key)
            
            if not obj:
                return Response({"error": f"File '{key}' not found"}, status=404)
            
            # Get content info
            info = r2_get_content_info(obj)
            
            # For binary files, return stream directly
            if info['type'] and ('image' in info['type'] or 'pdf' in info['type']):
                try:
                    from workers import Response as WorkersResponse
                    return WorkersResponse(obj.body, headers={
                        'Content-Type': info['type'],
                        'Content-Length': str(info['size']),
                        'Cache-Control': 'public, max-age=3600'
                    })
                except ImportError:
                    # Fallback if Workers Response not available
                    content = await obj.arrayBuffer()
                    return Response(content, headers={
                        'Content-Type': info['type'],
                        'Content-Length': str(info['size'])
                    })
            
            # For text files, return content
            content = await obj.text()
            return Response(content, headers={'Content-Type': info['type'] or 'text/plain'})
        else:
            return Response({
                "error": f"File '{key}' not accessible",
                "note": "R2 bucket not configured"
            }, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)

@app.delete("/delete/{key:path}")
async def delete_file(request):
    """Delete file from R2 bucket"""
    key = request.path_params.get('key')
    
    # Require confirmation header for safety
    confirm = request.header('x-confirm-delete')
    if confirm != 'true':
        return Response({
            "error": "Confirmation required",
            "hint": "Add header: X-Confirm-Delete: true"
        }, status=400)
    
    try:
        if hasattr(request.env, 'BUCKET'):
            await r2_delete(request.env.BUCKET, key)
            return {"success": True, "deleted": key}
        else:
            return {
                "success": False,
                "message": "R2 bucket not configured (mock response)",
                "would_delete": key
            }
    except Exception as e:
        return Response({"error": str(e)}, status=500)

@app.get("/asset/{asset_type}/{key:path}")
async def get_asset_url(request):
    """Generate asset URL for different types"""
    asset_type = request.path_params.get('asset_type', 'media')
    key = request.path_params.get('key')
    
    # Generate appropriate URL based on environment
    try:
        url = asset_url(key, asset_type, request)
    except:
        # Fallback if asset_url has issues
        url = f"https://example.com/{asset_type}/{key}"
    
    return {
        "asset_type": asset_type,
        "key": key,
        "url": url,
        "cache_hint": "Use CDN for production assets"
    }

# Cloudflare Workers entry point
async def on_fetch(request, env):
    return await app(request, env)