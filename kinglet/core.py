"""
Kinglet Core - Routing and application framework
"""
import re
from typing import Callable, Dict, List, Optional, Tuple

from .exceptions import HTTPError
from .http import Request, Response
from .middleware import Middleware


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
                elif param_type == 'path':
                    replacement = r'(.*)'  # Match everything including slashes
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
    """HTTP router for organizing routes"""

    def __init__(self):
        self.routes: List[Route] = []
        self.sub_routers: List[Router] = []

    def add_route(self, path: str, handler: Callable, methods: List[str]):
        """Add a route to the router"""
        route = Route(path, handler, methods)
        self.routes.append(route)

    def route(self, path: str, methods: List[str] = None):
        """Decorator for adding routes"""
        if methods is None:
            methods = ["GET"]

        def decorator(handler):
            self.add_route(path, handler, methods)
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

    def patch(self, path: str):
        """Decorator for PATCH routes"""
        return self.route(path, ["PATCH"])

    def head(self, path: str):
        """Decorator for HEAD routes"""
        return self.route(path, ["HEAD"])

    def options(self, path: str):
        """Decorator for OPTIONS routes"""
        return self.route(path, ["OPTIONS"])

    def include_router(self, prefix: str, router: 'Router'):
        """Include another router with a path prefix"""
        # Normalize prefix: ensure it starts with / and doesn't end with /
        if not prefix.startswith('/'):
            prefix = '/' + prefix
        prefix = prefix.rstrip('/')

        for route in router.routes:
            # Combine prefix with route path
            new_path = prefix + route.path
            self.add_route(new_path, route.handler, route.methods)

    def resolve(self, method: str, path: str) -> Tuple[Optional[Callable], Dict[str, str]]:
        """Find matching route and return handler with path params"""
        for route in self.routes:
            matches, path_params = route.matches(method, path)
            if matches:
                return route.handler, path_params
        return None, {}

    def get_routes(self):
        """Get all registered routes as tuples (path, methods, handler)"""
        return [(route.path, route.methods, route.handler) for route in self.routes]


class Kinglet:
    """Main application class"""

    def __init__(self, test_mode=False, root_path="", debug=False, auto_wrap_exceptions=True):
        self.router = Router()
        self.middleware_stack: List[Middleware] = []
        self.error_handlers: Dict[int, Callable] = {}
        self.test_mode = test_mode
        self.root_path = root_path.rstrip('/')  # Remove trailing slash
        self.debug = debug
        self.auto_wrap_exceptions = auto_wrap_exceptions

    def route(self, path: str, methods: List[str] = None):
        """Add route decorator"""
        def decorator(handler):
            # Auto-wrap with exception handling if enabled
            if self.auto_wrap_exceptions:
                from .decorators import wrap_exceptions
                handler = wrap_exceptions(expose_details=self.debug)(handler)

            self.router.add_route(self.root_path + path, handler, methods or ["GET"])
            return handler
        return decorator

    def get(self, path: str):
        """GET route decorator"""
        return self.route(path, ["GET"])

    def post(self, path: str):
        """POST route decorator"""
        return self.route(path, ["POST"])

    def put(self, path: str):
        """PUT route decorator"""
        return self.route(path, ["PUT"])

    def delete(self, path: str):
        """DELETE route decorator"""
        return self.route(path, ["DELETE"])

    def patch(self, path: str):
        """PATCH route decorator"""
        return self.route(path, ["PATCH"])

    def include_router(self, prefix: str, router: Router):
        """Include a sub-router with path prefix"""
        self.router.include_router(self.root_path + prefix, router)

    def exception_handler(self, status_code: int):
        """Decorator for custom error handlers"""
        def decorator(handler):
            self.error_handlers[status_code] = handler
            return handler
        return decorator

    def middleware(self, middleware_class):
        """Decorator for adding middleware classes"""
        middleware_instance = middleware_class()
        self.middleware_stack.append(middleware_instance)
        return middleware_class

    def add_middleware(self, middleware_instance):
        """Add an already instantiated middleware instance"""
        self.middleware_stack.append(middleware_instance)
        return middleware_instance

    async def __call__(self, request, env):
        """ASGI-compatible entry point for Workers"""
        try:
            # Wrap the raw request
            kinglet_request = Request(request, env)

            # Process middleware (request phase)
            for middleware in self.middleware_stack:
                result = await middleware.process_request(kinglet_request)
                if result is not None:
                    # Middleware short-circuited, return response
                    response = result
                    break
            else:
                # Find and call route handler
                handler, path_params = self.router.resolve(
                    kinglet_request.method,
                    kinglet_request.path
                )

                if handler:
                    # Add path parameters to request
                    kinglet_request.path_params = path_params

                    # Call handler
                    response = await handler(kinglet_request)

                    # Check if already a Workers Response - pass through directly
                    try:
                        from workers import Response as WorkersResponse
                        if isinstance(response, WorkersResponse):
                            return response  # Pass through without any processing
                    except ImportError:
                        pass  # workers not available, continue normal processing

                    # Convert dict/string responses to Response objects
                    if not isinstance(response, Response):
                        response = Response(response)
                else:
                    # No route found
                    response = Response({"error": "Not found"}, status=404)

            # Process middleware (response phase)
            for middleware in reversed(self.middleware_stack):
                response = await middleware.process_response(kinglet_request, response)

            # Try to convert to Workers Response if possible
            try:
                return response.to_workers_response()
            except ImportError:
                return response

        except Exception as e:
            # Handle exceptions
            status_code = getattr(e, 'status_code', 500)

            # Check for custom error handler
            if status_code in self.error_handlers:
                try:
                    response = await self.error_handlers[status_code](kinglet_request, e)
                    if not isinstance(response, Response):
                        response = Response(response)

                    # Process middleware (response phase) for error responses too
                    for middleware in reversed(self.middleware_stack):
                        response = await middleware.process_response(kinglet_request, response)

                    try:
                        return response.to_workers_response()
                    except ImportError:
                        return response
                except Exception:
                    pass  # Fall through to default error handler

            # Default error response
            # Security: Only expose specific error messages, not internal details
            if isinstance(e, HTTPError):
                # For HTTPError, use the provided message (it's intentional)
                error_message = e.message
            else:
                # For unexpected exceptions, hide details unless in debug mode
                error_message = str(e) if self.debug else "Internal server error"

            error_resp = Response({
                "error": error_message,
                "status_code": status_code,
                "request_id": getattr(kinglet_request, 'request_id', 'unknown')
            }, status=status_code)

            # Process middleware (response phase) for default error responses too
            for middleware in reversed(self.middleware_stack):
                error_resp = await middleware.process_response(kinglet_request, error_resp)

            try:
                return error_resp.to_workers_response()
            except ImportError:
                return error_resp
