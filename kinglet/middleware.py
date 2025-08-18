"""
Kinglet Middleware - Base classes and common middleware implementations
"""
import time
from abc import ABC, abstractmethod

from .http import Response


class Middleware(ABC):
    """Abstract base class for middleware"""

    @abstractmethod
    async def process_request(self, request):
        """Process incoming request, return Response to short-circuit or None to continue"""
        pass

    @abstractmethod
    async def process_response(self, request, response):
        """Process outgoing response, return modified Response"""
        pass


class CorsMiddleware(Middleware):
    """CORS middleware for handling cross-origin requests"""

    def __init__(self, allow_origin="*", allow_methods="GET,POST,PUT,DELETE,OPTIONS",
                 allow_headers="Content-Type,Authorization"):
        self.allow_origin = allow_origin
        self.allow_methods = allow_methods
        self.allow_headers = allow_headers

    async def process_request(self, request):
        """Handle OPTIONS preflight requests"""
        if request.method == "OPTIONS":
            return Response("", status=200).cors(
                origin=self.allow_origin,
                methods=self.allow_methods,
                headers=self.allow_headers
            )
        return None

    async def process_response(self, request, response):
        """Add CORS headers to all responses"""
        if not hasattr(response, 'cors'):
            # Handle non-Response objects
            if isinstance(response, dict):
                response = Response(response)
            else:
                return response

        return response.cors(
            origin=self.allow_origin,
            methods=self.allow_methods,
            headers=self.allow_headers
        )


class TimingMiddleware(Middleware):
    """Middleware to add timing information to responses"""

    async def process_request(self, request):
        """Record start time"""
        request._start_time = time.time()
        return None

    async def process_response(self, request, response):
        """Add timing header"""
        if hasattr(request, '_start_time'):
            duration = time.time() - request._start_time
            if hasattr(response, 'header'):
                response.header('X-Response-Time', f"{duration:.3f}s")
        return response
