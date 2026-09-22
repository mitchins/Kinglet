"""
Kinglet ASGI boundary - HTTP and lifespan handling for ASGI servers.

Supported scope: **ASGI 3 HTTP and lifespan on asyncio servers**. This module
does not implement WebSocket handling, generic background tasks, or platform
emulation: unsupported scope types are rejected explicitly.

Response contract on this path:

* Portable handler results (``None``, ``str``, ``bytes``, JSON-serializable
  ``dict``/``list``, and bounded streaming from async iterables or lazy sync
  iterables such as generators) are emitted as ASGI ``http.response`` events
  with status codes and repeated headers (notably separate ``Set-Cookie``
  values) preserved.
* Anything else raises a clear :class:`TypeError`. In particular there are
  no ``bytes -> str(bytes)``, binary-to-base64, ``str(object)``, or
  empty-success fallbacks, and a failed conversion never produces an empty
  ``200 OK``.
* Workers-native responses are **unsupported** on this path and raise
  :class:`TypeError`; they remain supported on the legacy Worker entry point
  (:meth:`kinglet.core.Kinglet.__call__`), which passes them through.
* Once response transmission has started, failures propagate after stream
  cleanup; no second JSON error response is attempted.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from typing import Any

Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Any]
Send = Callable[[Message], Any]


def with_env(
    app: Callable[[Scope, Receive, Send], Any], env: Any
) -> Callable[[Scope, Receive, Send], Any]:
    """Wrap an ASGI app to inject explicitly supplied settings/dependencies.

    Outside Cloudflare there is no ambient ``scope["env"]``; this small
    wrapper sets it (shallow-copied scope, binding object identity preserved)
    so ``request.env`` works the same as on Workers::

        from kinglet.asgi import with_env

        application = with_env(app.asgi, {"JWT_SECRET": "...", "DB": db})

    No dependency-injection framework is involved: ``env`` may be any object
    or mapping.
    """

    async def wrapper(scope: Scope, receive: Receive, send: Send) -> None:
        scope = dict(scope)
        scope["env"] = env
        await app(scope, receive, send)

    return wrapper


def _header_pairs(headers: dict[str, Any]) -> list[tuple[bytes, bytes]]:
    """Expand the response header mapping to ASGI byte pairs."""
    pairs: list[tuple[bytes, bytes]] = []
    for name, value in (headers or {}).items():
        raw_name = str(name).lower().encode("latin-1")
        values = value if isinstance(value, list | tuple) else [value]
        for item in values:
            if isinstance(item, bytes | bytearray):
                raw_value = bytes(item)
            else:
                raw_value = str(item).encode("latin-1")
            pairs.append((raw_name, raw_value))
    return pairs


def _single_body(content: Any) -> bytes:
    """Serialize buffered response content to bytes (strict, no fallbacks)."""
    if content is None:
        return b""
    if isinstance(content, bytes):
        return content
    if isinstance(content, bytearray | memoryview):
        return bytes(content)
    if isinstance(content, str):
        return content.encode("utf-8")
    if isinstance(content, dict | list):
        try:
            return json.dumps(content).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise TypeError(
                f"Unsupported response content: {type(content).__name__} "
                f"is not JSON-serializable ({exc})"
            ) from exc
    from .http import is_workers_native_response

    if is_workers_native_response(content):
        raise TypeError(
            "Workers-native responses are not supported on the ASGI path; "
            "use the legacy Worker entry point await app(request, env), "
            "which passes them through."
        )
    raise TypeError(
        f"Unsupported response content of type {type(content).__name__}: "
        "expected None, str, bytes, a JSON-serializable dict/list, or a "
        "streaming async iterable / lazy sync iterable of str/bytes chunks."
    )


def _is_streaming_content(content: Any) -> bool:
    """Return True for lazy chunk producers streamed without full buffering.

    Async iterables and lazy sync iterables (generators, iterators, custom
    single-pass iterables) stream chunk-by-chunk. Concrete builtin
    collections are not streams: ``dict``/``list`` are JSON bodies, while
    ``tuple``/``set``/``frozenset`` raise as unsupported so an unordered or
    accidental collection is never silently iterated on the wire.
    """
    if content is None or isinstance(content, str | bytes | bytearray | memoryview):
        return False
    if isinstance(content, dict | list | tuple | set | frozenset):
        return False
    from .http import is_workers_native_response

    if is_workers_native_response(content):
        return False
    return hasattr(content, "__aiter__") or hasattr(content, "__iter__")


def _coerce_chunk(chunk: Any) -> bytes:
    """Coerce one stream chunk to bytes (strict, no fallbacks)."""
    if isinstance(chunk, bytes):
        return chunk
    if isinstance(chunk, bytearray | memoryview):
        return bytes(chunk)
    if isinstance(chunk, str):
        return chunk.encode("utf-8")
    raise TypeError(
        f"Unsupported stream chunk of type {type(chunk).__name__}: "
        "stream chunks must be str or bytes."
    )


async def _iterate_chunks(content: Any) -> AsyncIterator[Any]:
    """Yield stream chunks without buffering the entire output."""
    if hasattr(content, "__aiter__"):
        async for chunk in content:
            yield chunk
    else:
        for chunk in content:
            yield chunk


async def _close_stream(content: Any) -> None:
    """Run stream cleanup (async generator ``aclose`` or ``close``)."""
    aclose = getattr(content, "aclose", None)
    if callable(aclose):
        await aclose()
        return
    close = getattr(content, "close", None)
    if callable(close):
        close()


async def send_response(send: Send, response: Any) -> None:
    """Emit a Kinglet response as ASGI ``http.response`` events.

    Raises :class:`TypeError` for anything that is not a Kinglet
    :class:`~kinglet.http.Response` with portable content. Streaming bodies
    await each send, avoid buffering the whole output, and run stream cleanup
    on cancellation or failure.
    """
    from .http import Response

    if not isinstance(response, Response):
        from .http import is_workers_native_response

        if is_workers_native_response(response):
            raise TypeError(
                "Workers-native responses are not supported on the ASGI path; "
                "use the legacy Worker entry point await app(request, env), "
                "which passes them through."
            )
        raise TypeError(
            "ASGI boundary requires a Kinglet Response; got "
            f"{type(response).__name__}. Return a dict, str, bytes, "
            "Response, or streaming iterable from handlers."
        )

    status = int(response.status)
    headers = _header_pairs(response.headers)
    if not any(name == b"content-type" for name, _ in headers) and isinstance(
        response.content, bytes | bytearray | memoryview
    ):
        headers.append((b"content-type", b"application/octet-stream"))

    if not _is_streaming_content(response.content):
        body = _single_body(response.content)
        if status in (204, 304):
            body = b""
        await send(
            {"type": "http.response.start", "status": status, "headers": headers}
        )
        await send({"type": "http.response.body", "body": body, "more_body": False})
        return

    await send({"type": "http.response.start", "status": status, "headers": headers})
    try:
        async for chunk in _iterate_chunks(response.content):
            await send(
                {
                    "type": "http.response.body",
                    "body": _coerce_chunk(chunk),
                    "more_body": True,
                }
            )
        await send({"type": "http.response.body", "body": b"", "more_body": False})
    finally:
        await _close_stream(response.content)
