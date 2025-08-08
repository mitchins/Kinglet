"""
Kinglet - A lightweight routing framework for Python Workers
Single-file version for easy deployment and distribution
"""
import json
import re
import time
from typing import Dict, List, Callable, Any, Optional, Tuple
from urllib.parse import urlparse, parse_qs
from abc import ABC, abstractmethod

__version__ = "0.1.0"
__author__ = "Mitchell Currie"


class Request:
    """Wrapper around Workers request with convenient methods"""
    
    def __init__(self, raw_request, env):
        self.raw_request = raw_request
        self.env = env
        
        # Parse URL components
        self.url = str(raw_request.url)
        parsed_url = urlparse(self.url)
        
        self.method = raw_request.method
        self.path = parsed_url.path
        self.query_string = parsed_url.query
        
        # Parse query parameters
        self._query_params = parse_qs(parsed_url.query)
        
        # Headers (converted to dict for easier access)
        self._headers = {}
        if hasattr(raw_request, 'headers'):
            try:
                # Try dictionary-style access first
                for key, value in raw_request.headers.items():
                    self._headers[key.lower()] = value
            except AttributeError:
                # Headers might be in a different format in Workers
                try:
                    # Try iterating over headers directly
                    for header in raw_request.headers:
                        self._headers[header[0].lower()] = header[1]
                except:
                    # If all else fails, just continue without headers
                    pass
        
        # Path parameters (set by router)
        self.path_params: Dict[str, str] = {}
        
        # Cached request body
        self._body_cache = None
        self._json_cache = None
    
    def query(self, key: str, default: Any = None) -> Optional[str]:
        """Get single query parameter value"""
        values = self._query_params.get(key, [])
        return values[0] if values else default
    
    def path_param(self, key: str, default: Any = None) -> Any:
        """Get path parameter value"""
        return self.path_params.get(key, default)
    
    def header(self, key: str, default: Any = None) -> Optional[str]:
        """Get header value (case-insensitive)"""
        return self._headers.get(key.lower(), default)
    
    async def body(self) -> str:
        """Get request body as string"""
        if self._body_cache is None:
            if hasattr(self.raw_request, 'text'):
                self._body_cache = await self.raw_request.text()
            else:
                self._body_cache = ""
        return self._body_cache
    
    async def json(self) -> Any:
        """Get request body as JSON"""
        if self._json_cache is None:
            body = await self.body()
            if body:
                try:
                    self._json_cache = json.loads(body)
                except json.JSONDecodeError:
                    self._json_cache = None
            else:
                self._json_cache = None
        return self._json_cache


class Response:
    """Response wrapper for Workers with convenient methods"""
    
    def __init__(
        self,
        content: Any = None,
        status: int = 200,
        headers: Optional[Dict[str, str]] = None,
        content_type: Optional[str] = None
    ):
        self.content = content
        self.status = status
        self.headers = headers or {}
        
        # Auto-detect content type
        if content_type:
            self.headers['Content-Type'] = content_type
        elif 'Content-Type' not in self.headers:
            if isinstance(content, (dict, list)):
                self.headers['Content-Type'] = 'application/json'
            elif isinstance(content, str):
                self.headers['Content-Type'] = 'text/plain; charset=utf-8'
    
    def header(self, key: str, value: str) -> 'Response':
        """Set a header (chainable)"""
        self.headers[key] = value
        return self
    
    def cors(
        self,
        origin: str = '*',
        methods: str = 'GET, POST, PUT, DELETE, OPTIONS',
        headers: str = 'Content-Type, Authorization'
    ) -> 'Response':
        """Set CORS headers (chainable)"""
        self.headers['Access-Control-Allow-Origin'] = origin
        self.headers['Access-Control-Allow-Methods'] = methods
        self.headers['Access-Control-Allow-Headers'] = headers
        return self
    
    def to_workers_response(self):
        """Convert to Workers Response object"""
        import json as json_module
        from workers import Response as WorkersResponse
        
        # Handle different content types
        if isinstance(self.content, (dict, list)):
            # Use Response.json for JSON content
            return WorkersResponse.json(self.content, status=self.status, headers=self.headers)
        else:
            # Serialize other content
            if isinstance(self.content, str):
                body = self.content
            elif self.content is None:
                body = ""
            else:
                body = str(self.content)
            
            # Use regular Response for text/other content
            return WorkersResponse(body, status=self.status, headers=self.headers)


def error_response(message: str, status: int = 400) -> Response:
    """Create an error response"""
    return Response({'error': message, 'status_code': status}, status=status)


class Route:
    """Represents a single route"""
    
    def __init__(self, path: str, handler: Callable, methods: List[str]):
        self.path = path
        self.handler = handler
        self.methods = [m.upper() for m in methods]
        
        # Convert path to regex with parameter extraction
        self.regex, self.param_names = self._compile_path(path)
    
    def _compile_path(self, path: str) -> Tuple[re.Pattern, List[str]]:
        """Convert path pattern to regex with parameter names"""
        param_names = []
        regex_pattern = path
        
        # Find path parameters like {id}, {slug}, etc.
        param_pattern = re.compile(r'\{([^}]+)\}')
        
        for match in param_pattern.finditer(path):
            param_name = match.group(1)
            param_names.append(param_name)
            
            # Support type hints like {id:int} or {slug:str}
            if ':' in param_name:
                param_name, param_type = param_name.split(':', 1)
                param_names[-1] = param_name  # Store clean name
                
                if param_type == 'int':
                    replacement = r'(\d+)'
                else:  # default to string
                    replacement = r'([^/]+)'
            else:
                replacement = r'([^/]+)'
            
            regex_pattern = regex_pattern.replace(match.group(0), replacement)
        
        # Ensure exact match
        if not regex_pattern.endswith('$'):
            regex_pattern += '$'
        if not regex_pattern.startswith('^'):
            regex_pattern = '^' + regex_pattern
        
        return re.compile(regex_pattern), param_names
    
    def matches(self, method: str, path: str) -> Tuple[bool, Dict[str, str]]:
        """Check if route matches method and path, return path params if match"""
        if method.upper() not in self.methods:
            return False, {}
        
        match = self.regex.match(path)
        if not match:
            return False, {}
        
        # Extract path parameters
        path_params = {}
        for i, param_name in enumerate(self.param_names):
            path_params[param_name] = match.group(i + 1)
        
        return True, path_params


class Router:
    """URL router with support for path parameters and sub-routers"""
    
    def __init__(self):
        self.routes: List[Route] = []
        self.sub_routers: List[Tuple[str, Router]] = []
    
    def route(self, path: str, methods: List[str] = None):
        """Decorator for adding routes"""
        if methods is None:
            methods = ["GET"]
        
        def decorator(handler):
            route = Route(path, handler, methods)
            self.routes.append(route)
            return handler
        
        return decorator
    
    def get(self, path: str):
        """Decorator for GET routes"""
        return self.route(path, ["GET"])
    
    def post(self, path: str):
        """Decorator for POST routes"""
        return self.route(path, ["POST"])
    
    def put(self, path: str):
        """Decorator for PUT routes"""
        return self.route(path, ["PUT"])
    
    def delete(self, path: str):
        """Decorator for DELETE routes"""
        return self.route(path, ["DELETE"])
    
    def get_routes(self) -> List[Tuple[str, List[str], Callable]]:
        """Get list of all routes as (path, methods, handler) tuples"""
        routes = []
        for route in self.routes:
            routes.append((route.path, route.methods, route.handler))
        return routes
    
    def include_router(self, prefix: str, router: 'Router'):
        """Include a sub-router with path prefix"""
        # Normalize prefix (remove trailing slash, ensure leading slash)
        prefix = ('/' + prefix.strip('/')).rstrip('/')
        if prefix == '':
            prefix = '/'
        
        self.sub_routers.append((prefix, router))
    
    def resolve(self, method: str, path: str) -> Tuple[Optional[Callable], Dict[str, str]]:
        """Resolve a method and path to a handler and path parameters"""
        
        # Try direct routes first
        for route in self.routes:
            matches, path_params = route.matches(method, path)
            if matches:
                return route.handler, path_params
        
        # Try sub-routers
        for prefix, sub_router in self.sub_routers:
            if path.startswith(prefix):
                # Strip prefix and try sub-router
                sub_path = path[len(prefix):] or '/'
                handler, path_params = sub_router.resolve(method, sub_path)
                if handler:
                    return handler, path_params
        
        return None, {}


class Middleware(ABC):
    """Base middleware class"""
    
    @abstractmethod
    async def process_request(self, request: Request) -> Request:
        """Process incoming request (before routing)"""
        return request
    
    @abstractmethod
    async def process_response(self, request: Request, response: Response) -> Response:
        """Process outgoing response (after handler)"""
        return response


class CorsMiddleware(Middleware):
    """CORS middleware for handling cross-origin requests"""
    
    def __init__(
        self,
        allow_origins: str = "*",
        allow_methods: str = "GET, POST, PUT, DELETE, OPTIONS",
        allow_headers: str = "Content-Type, Authorization"
    ):
        self.allow_origins = allow_origins
        self.allow_methods = allow_methods
        self.allow_headers = allow_headers
    
    async def process_request(self, request: Request) -> Request:
        """Handle preflight OPTIONS requests"""
        return request
    
    async def process_response(self, request: Request, response: Response) -> Response:
        """Add CORS headers to all responses"""
        response.cors(
            origin=self.allow_origins,
            methods=self.allow_methods,
            headers=self.allow_headers
        )
        
        if request.method == "OPTIONS":
            response.status = 200
            response.content = ""
        
        return response


class TimingMiddleware(Middleware):
    """Middleware to add response time headers"""
    
    async def process_request(self, request: Request) -> Request:
        """Record start time"""
        request._start_time = time.time()
        return request
    
    async def process_response(self, request: Request, response: Response) -> Response:
        """Add timing header"""
        if hasattr(request, '_start_time'):
            duration = time.time() - request._start_time
            response.header("X-Response-Time", f"{duration:.3f}s")
        return response


class Kinglet:
    """Lightweight ASGI-style application for Python Workers"""
    
    def __init__(self):
        self.router = Router()
        self.middleware_stack: List[Middleware] = []
        self.error_handlers: Dict[int, Callable] = {}
        
    def route(self, path: str, methods: List[str] = None):
        """Decorator for adding routes"""
        if methods is None:
            methods = ["GET"]
        return self.router.route(path, methods)
    
    def get(self, path: str):
        """Decorator for GET routes"""
        return self.route(path, ["GET"])
    
    def post(self, path: str):
        """Decorator for POST routes"""
        return self.route(path, ["POST"])
    
    def include_router(self, prefix: str, router: Router):
        """Include a sub-router with path prefix"""
        self.router.include_router(prefix, router)
    
    def exception_handler(self, status_code: int):
        """Decorator for custom error handlers"""
        def decorator(handler):
            self.error_handlers[status_code] = handler
            return handler
        return decorator
    
    async def __call__(self, request, env):
        """ASGI-compatible entry point for Workers"""
        try:
            # Wrap the raw request
            kinglet_request = Request(request, env)
            
            # Apply middleware (pre-processing)
            for middleware in self.middleware_stack:
                kinglet_request = await middleware.process_request(kinglet_request)
            
            # Route the request
            handler, path_params = self.router.resolve(
                kinglet_request.method, 
                kinglet_request.path
            )
            
            if handler is None:
                response = Response({"error": "Not found"}, status=404)
            else:
                # Inject path parameters into request
                kinglet_request.path_params = path_params
                
                # Call the handler
                response = await handler(kinglet_request)
                
                # Check if handler returned a workers.Response directly
                from workers import Response as WorkersResponse
                if isinstance(response, WorkersResponse):
                    # Skip middleware processing for direct Workers responses
                    return response
                
                # Ensure response is a Kinglet Response object
                if not isinstance(response, Response):
                    if isinstance(response, dict):
                        response = Response(response)
                    elif isinstance(response, str):
                        response = Response({"message": response})
                    else:
                        response = Response(response)
            
            # Apply middleware (post-processing) - only for Kinglet Response objects
            from workers import Response as WorkersResponse
            if not isinstance(response, WorkersResponse):
                for middleware in reversed(self.middleware_stack):
                    response = await middleware.process_response(kinglet_request, response)
                
                # Convert Kinglet Response to Workers Response
                return response.to_workers_response()
            else:
                # Already a Workers Response, return as-is
                return response
            
        except Exception as e:
            # Handle exceptions
            status_code = getattr(e, 'status_code', 500)
            
            if status_code in self.error_handlers:
                try:
                    response = await self.error_handlers[status_code](kinglet_request, e)
                    if not isinstance(response, Response):
                        response = Response(response)
                    return response.to_workers_response()
                except:
                    pass  # Fall through to default error handler
            
            # Default error response
            error_resp = Response({
                "error": str(e),
                "status_code": status_code
            }, status=status_code)
            
            return error_resp.to_workers_response()


# Export main classes for convenience
__all__ = ["Kinglet", "Router", "Route", "Response", "Request", "Middleware", "CorsMiddleware", "TimingMiddleware", "error_response"]