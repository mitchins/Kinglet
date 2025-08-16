"""
Test Response class behavior in Cloudflare Workers
"""
from kinglet import Kinglet, Response

app = Kinglet()

@app.get("/")
async def home(request):
    return {
        "message": "Response Class Tests",
        "endpoints": [
            "/text - Plain text response",
            "/dict - Dict response (auto JSON)",
            "/response-obj - Explicit Response object",
            "/custom-headers - Response with custom headers", 
            "/error-static - Static error method",
            "/content-type - Content-type handling"
        ]
    }

@app.get("/text")
async def handle_text_response(request):
    """Test plain text response - what content-type does it get?"""
    return "This is plain text"

@app.get("/dict") 
async def handle_dict_response(request):
    """Test dict response - should auto-convert to JSON"""
    return {"type": "dict", "auto_json": True}

@app.get("/response-obj")
async def handle_response_object(request):
    """Test explicit Response object"""
    return Response("Explicit response content", status=201)

@app.get("/custom-headers")
async def handle_custom_headers(request):
    """Test Response with custom headers"""
    response = Response({"data": "with headers"}, status=200)
    response.headers["X-Custom"] = "test-value"
    response.headers["Cache-Control"] = "no-cache"
    return response

@app.get("/error-static")
async def handle_error_static(request):
    """Test Response.error() static method"""
    return Response.error("Something went wrong", 400, request.request_id)

@app.get("/content-type")
async def handle_content_type(request):
    """Test explicit content-type setting"""
    response = Response("Custom content", status=200)
    response.headers["Content-Type"] = "text/custom"
    return response

@app.get("/json-method")
async def handle_json_method(request):
    """Test if Response has json() method"""
    try:
        # Try to use Response.json() if it exists
        return Response.json({"json_method": True}, status=200)
    except AttributeError:
        return {"error": "Response.json() method not available"}

# Cloudflare Workers entry point
async def on_fetch(request, env):
    return await app(request, env)