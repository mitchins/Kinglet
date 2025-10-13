"""
Kinglet Core - Routing and application framework
"""

from __future__ import annotations

import re
from collections.abc import Callable

from .exceptions import HTTPError
from .http import Request, Response
from .middleware import Middleware


class Route:
    """Represents a single route"""

    def __init__(self, path: str, handler: Callable, methods: list[str]):
        self.path = path
        self.handler = handler
        self.methods = [m.upper() for m in methods]

        # Convert path to regex with parameter extraction
        self.regex, self.param_names = self._compile_path(path)

    def _compile_path(self, path: str) -> tuple[re.Pattern, list[str]]:
        """Convert path pattern to regex with parameter names"""
        param_names = []
        regex_pattern = path

        # Find path parameters like {id}, {slug}, etc.
        param_pattern = re.compile(r"\{([^}]+)\}")

        for match in param_pattern.finditer(path):
            param_name = match.group(1)
            param_names.append(param_name)

            # Support type hints like {id:int} or {slug:str}
            if ":" in param_name:
                param_name, param_type = param_name.split(":", 1)
                param_names[-1] = param_name  # Store clean name

                if param_type == "int":
                    replacement = r"(\d+)"
                elif param_type == "path":
                    replacement = r"(.*)"  # Match everything including slashes
                else:  # default to string
                    replacement = r"([^/]+)"
            else:
                replacement = r"([^/]+)"

            regex_pattern = regex_pattern.replace(match.group(0), replacement)

        # Ensure exact match
        if not regex_pattern.endswith("$"):
            regex_pattern += "$"
        if not regex_pattern.startswith("^"):
            regex_pattern = "^" + regex_pattern

        return re.compile(regex_pattern), param_names

    def matches(self, method: str, path: str) -> tuple[bool, dict[str, str]]:
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
        self.routes: list[Route] = []
        self.sub_routers: list[Router] = []

    def add_route(self, path: str, handler: Callable, methods: list[str]):
        """Add a route to the router"""
        route = Route(path, handler, methods)
        self.routes.append(route)

    def route(self, path: str, methods: list[str] = None):
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

    def include_router(self, prefix: str, router: Router):
        """Include another router with a path prefix"""
        # Normalize prefix: ensure it starts with / and doesn't end with /
        if not prefix.startswith("/"):
            prefix = "/" + prefix
        prefix = prefix.rstrip("/")

        for route in router.routes:
            # Combine prefix with route path
            new_path = prefix + route.path
            self.add_route(new_path, route.handler, route.methods)

    def resolve(self, method: str, path: str) -> tuple[Callable | None, dict[str, str]]:
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

    def __init__(
        self, test_mode=False, root_path="", debug=False, auto_wrap_exceptions=True
    ):
        self.router = Router()
        self.middleware_stack: list[Middleware] = []
        self.error_handlers: dict[int, Callable] = {}
        self.test_mode = test_mode
        self.root_path = root_path.rstrip("/")  # Remove trailing slash
        self.debug = debug
        self.auto_wrap_exceptions = auto_wrap_exceptions

    def route(self, path: str, methods: list[str] = None):
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

    async def _process_request_middleware(self, request: Request):
        """Process request through middleware stack, return response if short-circuited"""
        for middleware in self.middleware_stack:
            result = await middleware.process_request(request)
            if result is not None:
                return result
        return None

    async def _handle_route(self, request: Request):
        """Handle route resolution and execution"""
        handler, path_params = self.router.resolve(request.method, request.path)

        if not handler:
            return Response({"error": "Not found"}, status=404)

        # Add path parameters and call handler
        request.path_params = path_params
        response = await handler(request)

        # Check if already a Workers Response - pass through directly
        try:
            from workers import Response as WorkersResponse

            if isinstance(response, WorkersResponse):
                return response
        except ImportError:
            pass

        # Convert dict/string responses to Response objects
        if not isinstance(response, Response):
            response = Response(response)
        return response

    async def _process_response_middleware(
        self, request: Request, response: Response
    ) -> Response:
        """Process response through middleware stack"""
        for middleware in reversed(self.middleware_stack):
            response = await middleware.process_response(request, response)
        return response

    def _convert_to_workers_response(self, response: Response):
        """Convert response to Workers format if available"""
        # Check if already a Workers Response - pass through directly
        try:
            from workers import Response as WorkersResponse

            if isinstance(response, WorkersResponse):
                return response
        except ImportError:
            pass

        # Also check by type name in case import paths differ
        if (
            hasattr(response, "__class__")
            and "workers" in str(type(response)).lower()
            and "response" in str(type(response)).lower()
        ):
            return response

        try:
            return response.to_workers_response()
        except ImportError:
            return response

    async def _handle_custom_error(
        self, request: Request, exception: Exception, status_code: int
    ):
        """Handle exception with custom error handler if available"""
        if status_code not in self.error_handlers:
            return None

        try:
            response = await self.error_handlers[status_code](request, exception)
            if not isinstance(response, Response):
                response = Response(response)

            response = await self._process_response_middleware(request, response)
            return self._convert_to_workers_response(response)
        except Exception:
            return None  # Fall through to default handler

    def _create_default_error_response(
        self, request: Request, exception: Exception, status_code: int
    ) -> Response:
        """Create default error response"""
        if isinstance(exception, HTTPError):
            error_message = exception.message
        else:
            error_message = str(exception) if self.debug else "Internal server error"

        return Response(
            {
                "error": error_message,
                "status_code": status_code,
                "request_id": getattr(request, "request_id", "unknown"),
            },
            status=status_code,
        )

    async def __call__(self, request, env):
        """ASGI-compatible entry point for Workers"""
        try:
            # Wrap the raw request
            kinglet_request = Request(request, env)

            # Process middleware (request phase)
            middleware_response = await self._process_request_middleware(
                kinglet_request
            )
            if middleware_response:
                response = middleware_response
            else:
                # Handle route
                response = await self._handle_route(kinglet_request)

            # Process response middleware and convert to Workers format
            response = await self._process_response_middleware(
                kinglet_request, response
            )
            return self._convert_to_workers_response(response)

        except Exception as e:
            status_code = getattr(e, "status_code", 500)

            # Try custom error handler first
            custom_response = await self._handle_custom_error(
                kinglet_request, e, status_code
            )
            if custom_response:
                return custom_response

            # Default error response
            error_resp = self._create_default_error_response(
                kinglet_request, e, status_code
            )
            error_resp = await self._process_response_middleware(
                kinglet_request, error_resp
            )
            return self._convert_to_workers_response(error_resp)
