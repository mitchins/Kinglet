"""
Kinglet HTTP Primitives - Request, Response, and utility functions
"""
import json
import secrets
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from .exceptions import HTTPError


def generate_request_id() -> str:
    """Generate a unique request ID for tracing"""
    return secrets.token_hex(8)

class Request:
    """
    Kinglet Request object that wraps Workers request with convenience methods
    """

    def __init__(self, raw_request, env=None, path_params=None):
        self._raw = raw_request
        self.env = env or type('Env', (), {})()
        self.path_params = path_params or {}
        self.request_id = generate_request_id()

        # Parse URL and method
        if hasattr(raw_request, 'url'):
            url_string = raw_request.url
            self.url = url_string  # Keep as string for compatibility
            self._parsed_url = urlparse(url_string)
            self.method = getattr(raw_request, 'method', 'GET').upper()
        else:
            # Fallback for test cases
            url_string = getattr(raw_request, 'url', 'http://localhost/')
            self.url = url_string
            self._parsed_url = urlparse(url_string)
            self.method = getattr(raw_request, 'method', 'GET').upper()

        # Initialize headers
        self._headers = {}
        self._init_headers(raw_request)

        # Cache for parsed content
        self._json_cache = None
        self._text_cache = None

    @property
    def path(self) -> str:
        """Get the path portion of the URL"""
        return self._parsed_url.path

    @property
    def query_string(self) -> str:
        """Get the query string portion of the URL"""
        return self._parsed_url.query

    def _init_headers(self, raw_request):
        """Initialize headers from raw request"""
        try:
            if hasattr(raw_request, 'headers'):
                headers_obj = raw_request.headers
                if hasattr(headers_obj, 'items'):
                    # Standard headers object with items()
                    for key, value in headers_obj.items():
                        self._headers[key.lower()] = value
                elif hasattr(headers_obj, 'get'):
                    # Headers object with get() method
                    # Try common headers
                    common_headers = ['authorization', 'content-type', 'user-agent', 'cf-ipcountry']
                    for header in common_headers:
                        value = headers_obj.get(header)
                        if value:
                            self._headers[header.lower()] = value
                else:
                    # Try to iterate if it's iterable
                    try:
                        for header in headers_obj:
                            self._headers[header[0].lower()] = header[1]
                    except (TypeError, AttributeError, IndexError):
                        # If all else fails, just continue without headers
                        pass
        except AttributeError:
            # Headers might be in a different format in Workers
            pass

    def header(self, name: str, default: str = None) -> str:
        """Get header value (case-insensitive)"""
        return self._headers.get(name.lower(), default)

    @property
    def query_params(self) -> Dict[str, str]:
        """Get query parameters as dict"""
        return {k: v[0] if v else '' for k, v in parse_qs(self._parsed_url.query).items()}

    def query(self, key: str, default: str = None) -> str:
        """Get query parameter value"""
        return self.query_params.get(key, default)

    def query_int(self, key: str, default: int = None) -> int:
        """Get query parameter as integer"""
        value = self.query(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            raise HTTPError(400, f"Query parameter '{key}' must be an integer")

    def path_param(self, key: str, default: str = None) -> str:
        """Get path parameter value"""
        return self.path_params.get(key, default)

    def path_param_int(self, key: str, default: int = None) -> int:
        """Get path parameter as integer"""
        value = self.path_param(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            raise HTTPError(400, f"Path parameter '{key}' must be an integer")

    def basic_auth(self) -> tuple:
        """Extract basic auth credentials"""
        auth_header = self.header('authorization', '')
        if auth_header.startswith('Basic '):
            try:
                import base64
                encoded = auth_header[6:]  # Remove 'Basic '
                decoded = base64.b64decode(encoded).decode('utf-8')
                if ':' in decoded:
                    username, password = decoded.split(':', 1)
                    return (username, password)
            except Exception:
                pass
        return None

    async def body(self) -> str:
        """Get raw request body"""
        return await self.text()

    async def text(self) -> str:
        """Get request body as text"""
        if self._text_cache is None:
            if hasattr(self._raw, 'text'):
                self._text_cache = await self._raw.text()
            else:
                self._text_cache = ""
        return self._text_cache

    async def bytes(self) -> bytes:
        """Get request body as bytes for binary data"""
        # Check if raw request has arrayBuffer() method (Workers runtime)
        if hasattr(self._raw, 'arrayBuffer'):
            array_buffer = await self._raw.arrayBuffer()
            # Convert ArrayBuffer to Python bytes
            try:
                from js import Uint8Array
                uint8_array = Uint8Array.new(array_buffer)
                return bytes([uint8_array[i] for i in range(uint8_array.length)])
            except ImportError:
                # Not in Workers environment - fallback behavior
                if hasattr(array_buffer, '__iter__'):
                    return bytes(array_buffer)
                else:
                    # Return empty bytes if conversion fails
                    return b""
        
        # Fallback: try to get text and encode to bytes
        try:
            text_data = await self.text()
            return text_data.encode('utf-8')
        except Exception:
            return b""

    async def json(self, convert=True) -> Optional[Dict]:
        """Get request body as parsed JSON
        
        Args:
            convert: If True (default), convert JsProxy objects to Python dict.
                     If False, return raw JsProxy object from Workers runtime.
        
        Returns:
            Parsed JSON as Python dict (default) or raw JsProxy object
        """
        cache_key = f"_json_cache_{convert}"
        cached_value = getattr(self, cache_key, None)

        if cached_value is None:
            # Check if raw request has json() method (like in Workers)
            if hasattr(self._raw, 'json'):
                try:
                    raw_json = await self._raw.json()
                    

                    if convert and raw_json is not None:
                        # Convert JsProxy to Python dict if needed
                        if hasattr(raw_json, 'to_py'):
                            # JsProxy object with to_py() method
                            cached_value = raw_json.to_py()
                        elif hasattr(raw_json, '__iter__') and not isinstance(raw_json, (str, bytes)):
                            # Try to convert object-like JsProxy manually
                            try:
                                # For object-like JsProxy, try to extract as dict
                                if hasattr(raw_json, 'Object') and hasattr(raw_json.Object, 'keys'):
                                    # Extract keys and values from JsProxy object
                                    result = {}
                                    keys = list(raw_json.Object.keys(raw_json))
                                    for key in keys:
                                        result[key] = raw_json[key]
                                    cached_value = result
                                else:
                                    cached_value = raw_json
                            except Exception:
                                cached_value = raw_json
                        else:
                            # Already a Python object
                            cached_value = raw_json
                    else:
                        # No conversion requested or raw_json is None
                        cached_value = raw_json

                except Exception as e:
                    # If Workers JSON fails, immediately try text fallback
                    try:
                        body = await self.text()
                        if body:
                            import json as json_module
                            cached_value = json_module.loads(body)
                        else:
                            cached_value = None
                    except Exception as text_e:
                        cached_value = None
            else:
                # Fallback to parsing text
                body = await self.text()
                if body:
                    try:
                        cached_value = json.loads(body)
                    except json.JSONDecodeError:
                        cached_value = None
                else:
                    cached_value = None

            setattr(self, cache_key, cached_value)

        return cached_value


class Response:
    """
    Kinglet Response object with automatic content type detection
    """

    def __init__(self, content: Any = None, status: int = 200, headers: Dict[str, str] = None, content_type: str = None):
        self.content = content
        self.status = status
        self.headers = headers or {}

        # Handle explicit content_type parameter
        if content_type:
            self.headers['Content-Type'] = content_type
        # Auto-detect content type like Cloudflare Workers
        elif 'content-type' not in {k.lower() for k in self.headers.keys()}:
            if isinstance(content, (dict, list)):
                self.headers['Content-Type'] = 'application/json'
            elif isinstance(content, str):
                self.headers['Content-Type'] = 'text/plain; charset=utf-8'

    def header(self, name: str, value: str):
        """Add header (chainable)"""
        self.headers[name] = value
        return self

    def cors(self, origin: str = "*", methods: str = "GET,POST,PUT,DELETE",
             headers: str = "Content-Type,Authorization"):
        """Add CORS headers (chainable)"""
        self.headers.update({
            'Access-Control-Allow-Origin': origin,
            'Access-Control-Allow-Methods': methods,
            'Access-Control-Allow-Headers': headers
        })
        return self

    def to_workers_response(self):
        """Convert to Workers Response object"""
        from workers import Response as WorkersResponse

        # Handle different content types
        if isinstance(self.content, (dict, list)):
            # Use Response.json for JSON content
            return WorkersResponse.json(self.content, status=self.status, headers=self.headers)
        else:
            # Use regular Response for text/binary content
            return WorkersResponse(self.content, status=self.status, headers=self.headers)

    @staticmethod
    def error(message: str, status: int = 500, request_id: str = None):
        """Create error response"""
        content = {"error": message, "status_code": status}
        if request_id:
            content["request_id"] = request_id
        return Response(content, status)


def error_response(message: str, status: int = 400, request_id: str = None):
    """Create standardized error response (defaults to 400 Bad Request)"""
    return Response.error(message, status, request_id)
