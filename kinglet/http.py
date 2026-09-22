"""
Kinglet HTTP Primitives - Request, Response, and utility functions
"""

from __future__ import annotations

import json
import secrets
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlparse

from .exceptions import HTTPError


def generate_request_id() -> str:
    """Generate a unique request ID for tracing"""
    return secrets.token_hex(8)


class _DictEnvAdapter:
    """Adapter to support attribute-style env access for dict inputs."""

    def __init__(self, data: dict[str, Any]):
        self._data = dict(data)

    def __getattr__(self, key: str) -> Any:
        if key in self._data:
            return self._data[key]
        raise AttributeError(key)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)


def is_workers_native_response(obj: Any) -> bool:
    """Detect a Cloudflare Workers-native Response object.

    Legacy Worker-boundary helper. A Kinglet :class:`Response` is never
    considered foreign, even when it wraps foreign content. Outside the
    Workers runtime this falls back to a type-name heuristic so platform
    shims used in tests are still recognized.
    """
    if obj is None or isinstance(obj, Response):
        return False
    try:
        from workers import Response as WorkersResponse

        if isinstance(obj, WorkersResponse):
            return True
    except ImportError:
        pass
    type_name = str(type(obj)).lower()
    return "workers" in type_name and "response" in type_name


def _strip_mount_path(path: str, root_path: str) -> str:
    """Strip an ASGI mount prefix on path-segment boundaries.

    Kinglet's configured route prefix and ASGI's ``scope["root_path"]`` are
    separate concepts: the former is baked into registered routes at
    registration time, while the latter is supplied per-request by the
    hosting/mounting layer and removed here before routing. Stripping applies
    only on segment boundaries, so a mount of ``/api`` never strips ``/apix``.
    """
    if not root_path or root_path == "/":
        return path
    if path == root_path:
        return "/"
    if path.startswith(root_path + "/"):
        return path[len(root_path) :]
    return path


def _scope_host(scope: dict[str, Any], headers: dict[str, str]) -> str:
    """Resolve the request host from headers, falling back to the server."""
    host = headers.get("host")
    if host:
        return host
    server = scope.get("server")
    if isinstance(server, list | tuple) and len(server) == 2 and server[0]:
        return f"{server[0]}:{server[1]}" if server[1] else str(server[0])
    return "localhost"


async def _read_asgi_body(receive: Any) -> tuple[bytes, bool]:
    """Read all ASGI ``http.request`` events until ``more_body`` is false.

    Returns ``(body, disconnected)``. Binary data is preserved exactly.
    Transport failures raised by ``receive`` propagate to the caller; an
    ``http.disconnect`` stops the read without hanging and reports the
    partial body with ``disconnected=True``.
    """
    chunks: list[bytes] = []
    while True:
        message = await receive()
        message_type = message.get("type") if isinstance(message, dict) else None
        if message_type == "http.request":
            chunk = message.get("body", b"") or b""
            chunks.append(bytes(chunk))
            if not message.get("more_body", False):
                return b"".join(chunks), False
        elif message_type == "http.disconnect":
            return b"".join(chunks), True
        else:
            raise RuntimeError(
                f"Unexpected ASGI message {message_type!r} while reading request body"
            )


class Request:
    """
    Kinglet Request object that wraps Workers request with convenience methods.

    Two construction paths produce the same application surface (``method``,
    ``path``, query/path helpers, ``header()``, ``body()``/``text()``/
    ``bytes()``/``json()``, ``env``, ``state`` and ``scope``):

    * Direct construction ``Request(raw_request, env)`` for the Workers-style
      raw request (and existing applications/tests).
    * :meth:`from_asgi` for ASGI ``(scope, receive)`` pairs.

    Compatibility notes (pinned behavior):

    * ``body()`` is a text-returning alias of ``text()``; binary access is
      provided by ``bytes()``.
    * ``json()`` returns ``None`` for empty or malformed JSON bodies. This is
      a documented parse result, not a transport report: failures raised by
      the transport itself propagate instead.
    """

    def __init__(
        self,
        raw_request: Any,
        env: Any = None,
        path_params: dict[str, str] | None = None,
        *,
        scope: dict[str, Any] | None = None,
        state: Any = None,
    ):
        self._raw = raw_request
        # Underlying ASGI scope on the ASGI path; None on the legacy path.
        self.scope = scope
        if env is None:
            self.env: Any = type("Env", (), {})()
        elif isinstance(env, dict):
            self.env = _DictEnvAdapter(env)
        else:
            # Preserve binding object identity: no copy or serialization.
            self.env = env
        self.path_params = path_params or {}
        self.request_id = generate_request_id()
        # Fresh per-request application state. On the ASGI path it is seeded
        # with a shallow copy of lifespan ``scope["state"]`` when present, so
        # referenced application resources may be shared while the namespace
        # itself stays request-local.
        self.state: Any = state if state is not None else self._fresh_state(scope)

        # Compatibility header dict (lowercased name -> value, last wins) plus
        # the complete raw header list so repeated headers are never lost.
        self._headers: dict[str, str] = {}
        self._raw_headers: list[tuple[bytes, bytes]] = []
        # Single cached body for repeated buffered reads.
        self._body_bytes: bytes | None = None
        self._disconnected = False
        self.raw_path: bytes | None = None
        self.query_bytes: bytes = b""
        self.root_path: str = ""
        self._external_path: str = "/"
        self._path: str = "/"

        # Cache for parsed content
        self._json_cache: Any = None
        self._text_cache: str | None = None

        if raw_request is None and scope is not None:
            self._init_from_scope(scope)
        else:
            self._init_from_raw(raw_request)

    @staticmethod
    def _fresh_state(scope: dict[str, Any] | None) -> SimpleNamespace:
        """Create a fresh request-state namespace, seeded from lifespan state."""
        seeded: dict[str, Any] = {}
        if isinstance(scope, dict):
            scope_state = scope.get("state")
            if isinstance(scope_state, dict):
                seeded = {
                    key: value
                    for key, value in scope_state.items()
                    if isinstance(key, str)
                }
        return SimpleNamespace(**seeded)

    @classmethod
    async def from_asgi(
        cls, scope: dict[str, Any], receive: Any, env: Any = None
    ) -> Request:
        """Build a Request from an ASGI HTTP scope and receive channel.

        ASGI distinctions are preserved, not flattened: the decoded
        ``scope["path"]`` drives routing while the encoded ``raw_path``,
        raw query bytes and raw header pairs are retained separately.

        * The full request body is read until ``more_body`` is false. Binary
          data is preserved exactly; empty bodies and multiple chunks are
          supported. One cached body backs repeated buffered reads.
        * ``env`` explicitly passed here wins; otherwise ``scope["env"]``
          (supplied by Cloudflare's SDK, or by :func:`kinglet.asgi.with_env`
          outside Workers) is used with object identity preserved. There is
          no ``scope["ctx"]`` dependency and no discovery of secrets from
          process environment variables.
        * ``http.disconnect`` during the body read stops without hanging and
          marks the request (see :meth:`is_disconnected`); transport errors
          raised by ``receive`` propagate instead of producing empty content.
        """
        if not isinstance(scope, dict) or scope.get("type", "http") != "http":
            raise TypeError(
                "Request.from_asgi requires an ASGI HTTP scope "
                f"(got type {scope.get('type')!r} on "
                f"{type(scope).__name__})"
                if isinstance(scope, dict)
                else "Request.from_asgi requires an ASGI HTTP scope dict"
            )
        resolved_env = env if env is not None else scope.get("env")
        request = cls(None, resolved_env, scope=scope)
        body, disconnected = await _read_asgi_body(receive)
        request._body_bytes = body
        request._disconnected = disconnected
        return request

    def _init_from_raw(self, raw_request: Any) -> None:
        """Initialize URL, method and headers from a Workers-style request."""
        # Parse URL and method
        if hasattr(raw_request, "url"):
            url_string = raw_request.url
            self.url = url_string  # Keep as string for compatibility
            self._parsed_url = urlparse(url_string)
            self.method = getattr(raw_request, "method", "GET").upper()
        else:
            # Fallback for test cases
            url_string = getattr(raw_request, "url", "https://testserver/")
            self.url = url_string
            self._parsed_url = urlparse(url_string)
            self.method = getattr(raw_request, "method", "GET").upper()

        self._external_path = self._parsed_url.path
        self._path = self._external_path
        self.query_bytes = self._parsed_url.query.encode("latin-1")

        # Initialize headers
        self._init_headers(raw_request)

    def _init_from_scope(self, scope: dict[str, Any]) -> None:
        """Initialize URL, method and headers from an ASGI HTTP scope."""
        raw_headers = [
            (bytes(name), bytes(value)) for name, value in scope.get("headers", [])
        ]
        self._raw_headers = raw_headers
        for name, value in raw_headers:
            self._headers[name.decode("latin-1").lower()] = value.decode("latin-1")

        self.method = str(scope.get("method", "GET")).upper()

        external_path = scope.get("path", "/") or "/"
        if not isinstance(external_path, str):
            external_path = str(external_path)
        mount = scope.get("root_path", "") or ""
        if not isinstance(mount, str):
            mount = str(mount)
        self.root_path = mount
        self._external_path = external_path
        self._path = _strip_mount_path(external_path, mount)

        raw_path = scope.get("raw_path", None)
        if isinstance(raw_path, bytes | bytearray):
            self.raw_path = bytes(raw_path)
            path_for_url = self.raw_path.decode("latin-1")
        else:
            self.raw_path = None
            path_for_url = external_path

        query = scope.get("query_string", b"") or b""
        self.query_bytes = bytes(query)
        query_text = self.query_bytes.decode("latin-1")

        scheme = str(scope.get("scheme", "http") or "http")
        host = _scope_host(scope, self._headers)
        self.url = f"{scheme}://{host}{path_for_url}"
        if query_text:
            self.url += f"?{query_text}"
        self._parsed_url = urlparse(self.url)

    @property
    def path(self) -> str:
        """Get the router-relative path portion of the URL.

        On the ASGI path this excludes the ``scope["root_path"]`` mount
        prefix; see :attr:`full_path` for the externally visible path.
        """
        return self._path

    @property
    def full_path(self) -> str:
        """Get the externally visible path, including any mount prefix."""
        return self._external_path

    @property
    def query_string(self) -> str:
        """Get the query string portion of the URL"""
        return self._parsed_url.query

    def is_disconnected(self) -> bool:
        """Return True if the client disconnected while the body was read."""
        return self._disconnected

    @property
    def raw_headers(self) -> tuple[tuple[bytes, bytes], ...]:
        """Complete header list as ``(name, value)`` byte pairs in order."""
        return tuple(self._raw_headers)

    def getlist(self, name: str) -> list[str]:
        """Get all values for a header (case-insensitive), preserving repeats."""
        want = name.lower()
        values = [
            value.decode("latin-1")
            for key, value in self._raw_headers
            if key.decode("latin-1").lower() == want
        ]
        if values:
            return values
        single = self._headers.get(want)
        return [single] if single is not None else []

    def _extract_headers_with_items(self, headers_obj: Any) -> None:
        """Extract headers using items() method"""
        for key, value in headers_obj.items():
            self._headers[key.lower()] = value

    def _extract_headers_with_get(self, headers_obj: Any) -> None:
        """Extract headers using get() method for common headers"""
        common_headers = ["authorization", "content-type", "user-agent", "cf-ipcountry"]
        for header in common_headers:
            value = headers_obj.get(header)
            if value:
                self._headers[header.lower()] = value

    def _extract_headers_iterable(self, headers_obj: Any) -> None:
        """Extract headers from iterable format"""
        try:
            for header in headers_obj:
                self._headers[header[0].lower()] = header[1]
        except (TypeError, AttributeError, IndexError):
            # Unable to iterate headers; leave headers as-is
            return

    def _init_headers(self, raw_request: Any) -> None:
        """Initialize headers from raw request"""
        try:
            if not hasattr(raw_request, "headers"):
                return

            headers_obj = raw_request.headers
            if hasattr(headers_obj, "items"):
                self._extract_headers_with_items(headers_obj)
            elif hasattr(headers_obj, "get"):
                self._extract_headers_with_get(headers_obj)
            else:
                self._extract_headers_iterable(headers_obj)
        except AttributeError:
            # Raw request has no usable headers
            return

    def header(self, name: str, default: str | None = None) -> str | None:
        """Get header value (case-insensitive)"""
        header_name = name.lower()
        value = self._headers.get(header_name)
        if value is not None:
            return value

        # Fallback: in Workers-style runtimes headers may only expose .get()
        headers_obj = getattr(self._raw, "headers", None)
        if headers_obj is not None and hasattr(headers_obj, "get"):
            try:
                fallback = headers_obj.get(name)
                if fallback is not None:
                    return fallback
            except (AttributeError, TypeError):
                pass

        return default

    @property
    def query_params(self) -> dict[str, str]:
        """Get query parameters as dict"""
        return {
            k: v[0] if v else "" for k, v in parse_qs(self._parsed_url.query).items()
        }

    def query(self, key: str, default: str | None = None) -> str | None:
        """Get query parameter value"""
        return self.query_params.get(key, default)

    def query_all(self, key: str) -> list[str]:
        """Get all values for a repeated query parameter, in order."""
        return parse_qs(self._parsed_url.query, keep_blank_values=True).get(key, [])

    def query_int(self, key: str, default: int | None = None) -> int | None:
        """Get query parameter as integer"""
        value = self.query(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError as e:
            raise HTTPError(400, f"Query parameter '{key}' must be an integer") from e

    def path_param(self, key: str, default: str | None = None) -> str | None:
        """Get path parameter value"""
        return self.path_params.get(key, default)

    def path_param_int(self, key: str, default: int | None = None) -> int | None:
        """Get path parameter as integer"""
        value = self.path_param(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError as e:
            raise HTTPError(400, f"Path parameter '{key}' must be an integer") from e

    def basic_auth(self) -> tuple[str, str] | None:
        """Extract basic auth credentials"""
        auth_header = self.header("authorization", "")
        if auth_header.startswith("Basic "):
            try:
                import base64

                encoded = auth_header[6:]  # Remove 'Basic '
                decoded = base64.b64decode(encoded).decode("utf-8")
                if ":" in decoded:
                    username, password = decoded.split(":", 1)
                    return (username, password)
            except Exception:
                return None
        return None

    async def body(self) -> str:
        """Get raw request body as text (alias of :meth:`text`)."""
        return await self.text()

    async def text(self) -> str:
        """Get request body as text.

        On the ASGI path the cached body bytes are decoded as UTF-8, so
        non-UTF-8 binary bodies raise :class:`UnicodeDecodeError` instead of
        producing fabricated empty content.
        """
        if self._text_cache is None:
            if self._body_bytes is not None:
                self._text_cache = self._body_bytes.decode("utf-8")
            elif self._raw is not None and hasattr(self._raw, "text"):
                self._text_cache = await self._raw.text()
            else:
                self._text_cache = ""
        return self._text_cache

    def _uint8_array_to_bytes(self, uint8_array: Any) -> bytes:
        if hasattr(uint8_array, "to_bytes"):
            return uint8_array.to_bytes()

        try:
            return bytes(uint8_array)
        except (TypeError, ValueError):
            if hasattr(uint8_array, "__iter__"):
                try:
                    return bytes(list(uint8_array))
                except (TypeError, ValueError):
                    return b""
            return b""

    def _array_buffer_fallback_to_bytes(self, array_buffer: Any) -> bytes:
        if hasattr(array_buffer, "__iter__"):
            try:
                return bytes(array_buffer)
            except (TypeError, ValueError):
                return b""
        return b""

    def _workers_array_buffer_to_bytes(self, array_buffer: Any) -> bytes:
        try:
            from js import Uint8Array  # type: ignore[import-not-found]

            uint8_array = Uint8Array.new(array_buffer)
            return self._uint8_array_to_bytes(uint8_array)
        except (ImportError, TypeError, ValueError):
            return self._array_buffer_fallback_to_bytes(array_buffer)

    async def bytes(self) -> bytes:
        """Get request body as bytes for binary data.

        The result is cached, so repeated calls return the same bytes without
        consuming the transport again. Transport failures propagate instead
        of producing fabricated empty content.
        """
        if self._body_bytes is not None:
            return self._body_bytes

        # Check if raw request has arrayBuffer() method (Workers runtime)
        if self._raw is not None and hasattr(self._raw, "arrayBuffer"):
            array_buffer = await self._raw.arrayBuffer()
            self._body_bytes = self._workers_array_buffer_to_bytes(array_buffer)
            return self._body_bytes

        # Fallback: try to get text and encode to bytes
        text_data = await self.text()
        self._body_bytes = text_data.encode("utf-8")
        return self._body_bytes

    def _convert_jsproxy_to_dict(self, raw_json: Any) -> Any:
        """Convert JsProxy object to Python dict"""
        if hasattr(raw_json, "to_py"):
            return raw_json.to_py()

        if not (
            hasattr(raw_json, "__iter__") and not isinstance(raw_json, str | bytes)
        ):
            return raw_json

        try:
            if hasattr(raw_json, "Object") and hasattr(raw_json.Object, "keys"):
                result = {}
                keys = list(raw_json.Object.keys(raw_json))
                for key in keys:
                    result[key] = raw_json[key]
                return result
            return raw_json
        except Exception:
            return raw_json

    async def _parse_workers_json(self, convert: bool) -> Any:
        """Parse JSON using Workers request.json() method"""
        try:
            raw_json = await self._raw.json()
            if convert and raw_json is not None:
                return self._convert_jsproxy_to_dict(raw_json)
            return raw_json
        except Exception:
            return await self._parse_text_fallback_json()

    async def _parse_text_fallback_json(self) -> Any:
        """Fallback JSON parsing from text body"""
        try:
            body = await self.text()
            if body:
                import json as json_module

                return json_module.loads(body)
            return None
        except Exception:
            return None

    async def _parse_text_json(self) -> Any:
        """Parse JSON from text body (non-Workers)"""
        body = await self.text()
        if not body:
            return None
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return None

    async def json(self, convert: bool = True) -> dict | None:
        """Get request body as parsed JSON

        Args:
            convert: If True (default), convert JsProxy objects to Python dict.
                     If False, return raw JsProxy object from Workers runtime.

        Returns:
            Parsed JSON as Python dict (default) or raw JsProxy object.
            Empty or malformed JSON bodies yield ``None`` (pinned behavior);
            transport failures and undecodable binary bodies raise instead.
        """
        cache_key = f"_json_cache_{convert}"
        cache_set_key = f"_json_cache_set_{convert}"

        if not getattr(self, cache_set_key, False):
            if self._raw is not None and hasattr(self._raw, "json"):
                cached_value = await self._parse_workers_json(convert)
            else:
                cached_value = await self._parse_text_json()

            setattr(self, cache_key, cached_value)
            setattr(self, cache_set_key, True)

        return getattr(self, cache_key)


class Response:
    """
    Kinglet Response object with automatic content type detection
    """

    def __init__(
        self,
        content: Any = None,
        status: int = 200,
        headers: dict[str, Any] | None = None,
        content_type: str | None = None,
    ):
        self.content = content
        self.status = status
        # Header values may be a single value or a list/tuple of values for
        # repeated headers (notably multiple ``Set-Cookie`` values, which a
        # plain dict cannot otherwise represent).
        self.headers: dict[str, Any] = dict(headers) if headers else {}

        # Handle explicit content_type parameter
        if content_type:
            self.headers["Content-Type"] = content_type
        # Auto-detect content type like Cloudflare Workers
        elif "content-type" not in {k.lower() for k in self.headers.keys()}:
            if isinstance(content, dict | list):
                self.headers["Content-Type"] = "application/json"
            elif isinstance(content, str):
                self.headers["Content-Type"] = "text/plain; charset=utf-8"

    def header(self, name: str, value: str) -> Response:
        """Add header (chainable)"""
        self.headers[name] = value
        return self

    def append_header(self, name: str, value: str) -> Response:
        """Append a header value, preserving repeated headers (chainable).

        A second value for the same header name (case-insensitive) converts
        the entry to a list so separate ``Set-Cookie`` values survive.
        """
        lowered = name.lower()
        for existing in self.headers:
            if existing.lower() == lowered:
                current = self.headers[existing]
                if isinstance(current, list):
                    current.append(value)
                else:
                    self.headers[existing] = [current, value]
                return self
        self.headers[name] = value
        return self

    def cors(
        self,
        origin: str = "*",
        methods: str = "GET,POST,PUT,DELETE",
        headers: str = "Content-Type,Authorization",
    ) -> Response:
        """Add CORS headers (chainable)"""
        self.headers.update(
            {
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Methods": methods,
                "Access-Control-Allow-Headers": headers,
            }
        )
        return self

    def to_workers_response(self) -> Any:
        """Convert to Workers Response object.

        Header values that are lists (repeated headers) are passed through
        unchanged; the Workers runtime accepts them, whereas flattening
        (e.g. comma-joining ``Set-Cookie``) would corrupt them.
        """
        from workers import Response as WorkersResponse

        # Handle different content types
        if isinstance(self.content, dict | list):
            # Use Response.json for JSON content
            return WorkersResponse.json(
                self.content, status=self.status, headers=self.headers
            )
        else:
            # Use regular Response for text/binary content
            return WorkersResponse(
                self.content, status=self.status, headers=self.headers
            )

    @staticmethod
    def error(
        message: str, status: int = 500, request_id: str | None = None
    ) -> Response:
        """Create error response"""
        content = {"error": message, "status_code": status}
        if request_id:
            content["request_id"] = request_id
        return Response(content, status)


def error_response(
    message: str, status: int = 400, request_id: str | None = None
) -> Response:
    """Create standardized error response (defaults to 400 Bad Request)"""
    return Response.error(message, status, request_id)
