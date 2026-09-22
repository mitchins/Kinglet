"""
Kinglet ASGI alignment tests: protocol, HTTPX, lifespan, env/state, security.

Uses the in-process harness in ``tests/asgi_harness.py`` so emitted events
and received events are fully controlled. Real-server coverage lives in
``tests/test_asgi_servers.py``; deployed Cloudflare proof is recorded
separately.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

import httpx
import pytest

from kinglet import Kinglet, Response, Router, TestClient
from kinglet.asgi import with_env
from kinglet.authz import require_auth, require_claim
from kinglet.http import Request

from .asgi_harness import (
    Harness,
    body_messages,
    build_fixture_app,
    build_smoke_scope_env,
    fixed_exp,
    http_scope,
    mint_jwt,
    response_body,
    response_start,
    run_asgi,
    sent_headers,
)

SECRET = "asgi-test-secret"


def auth_headers(claims: dict[str, Any]) -> dict[str, str]:
    token = mint_jwt(SECRET, {"sub": "user-1", "exp": fixed_exp(), **claims})
    return {"authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# A. Protocol-level request handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRequestBoundary:
    async def test_chunked_body_preserved_exactly(self):
        app = build_fixture_app()
        body = b"\x00\x01binary-\xff-chunks-\xfe" * 64
        sent = await run_asgi(
            app,
            http_scope(path="/echo-bytes", method="POST"),
            body_messages(body, chunk_size=7),
        )
        assert response_start(sent)["status"] == 200
        assert response_body(sent) == body

    async def test_empty_body(self):
        app = build_fixture_app()
        sent = await run_asgi(
            app,
            http_scope(path="/echo-bytes", method="POST"),
            body_messages(b""),
        )
        assert response_start(sent)["status"] == 200
        assert response_body(sent) == b""

    async def test_all_byte_values_round_trip(self):
        app = build_fixture_app()
        body = bytes(range(256))
        sent = await run_asgi(
            app,
            http_scope(path="/echo-bytes", method="POST"),
            body_messages(body, chunk_size=13),
        )
        out = response_body(sent)
        assert len(out) == 256
        assert hashlib.sha256(out).hexdigest() == hashlib.sha256(body).hexdigest()
        assert out == body

    async def test_large_binary_fixture_integrity(self):
        app = build_fixture_app()
        body = bytes(i % 256 for i in range(512 * 1024))
        digest = hashlib.sha256(body).hexdigest()
        sent = await run_asgi(
            app,
            http_scope(path="/echo-bytes", method="POST"),
            body_messages(body, chunk_size=65536),
        )
        out = response_body(sent)
        assert len(out) == len(body)
        assert hashlib.sha256(out).hexdigest() == digest

    async def test_repeated_buffered_reads_use_cached_body(self):
        reads: dict[str, Any] = {}

        app = Kinglet()

        @app.post("/reads", public=True)
        async def reads_handler(request):
            first = await request.bytes()
            reads["bytes_first"] = first
            reads["bytes_second"] = await request.bytes()
            reads["text"] = await request.text()
            reads["body"] = await request.body()
            reads["json"] = await request.json()
            return {"ok": True}

        body = b'{"a": 1}'.replace(b"1", b"1")
        sent = await run_asgi(
            app, http_scope(path="/reads", method="POST"), body_messages(body)
        )
        assert response_start(sent)["status"] == 200
        assert reads["bytes_first"] == body
        assert reads["bytes_second"] == body
        assert reads["text"] == body.decode()
        assert reads["body"] == body.decode()
        assert reads["json"] == {"a": 1}

    async def test_body_returns_str_malformed_json_returns_none(self):
        """Pin: body() is text; malformed JSON parses to None (not a raise)."""
        app = build_fixture_app()
        sent = await run_asgi(
            app,
            http_scope(path="/echo-text", method="POST"),
            body_messages(b"{ invalid json"),
        )
        payload = json.loads(response_body(sent))
        assert payload["body_type"] == "str"
        assert payload["text"] == "{ invalid json"

        sent = await run_asgi(
            app,
            http_scope(path="/echo-json", method="POST"),
            body_messages(b"{ invalid json"),
        )
        assert json.loads(response_body(sent)) == {"received": None}

    async def test_path_raw_path_query_and_header_distinctions(self):
        seen: dict[str, Any] = {}
        app = Kinglet()

        @app.get("/items", public=True)
        async def items(request):
            seen["path"] = request.path
            seen["full_path"] = request.full_path
            seen["root_path"] = request.root_path
            seen["raw_path"] = request.raw_path
            seen["query_bytes"] = request.query_bytes
            seen["query"] = request.query_params
            seen["repeated"] = request.getlist("x-multi")
            seen["compat"] = request.header("x-multi")
            seen["raw_headers"] = request.raw_headers
            return {"ok": True}

        scope = http_scope(
            path="/api/items",
            headers=[("X-Multi", "one"), ("X-Multi", "two")],
            query=b"a=1&a=2",
            root_path="/api",
            raw_path=b"/api/%69tems",
        )
        sent = await run_asgi(app, scope, body_messages(b""))
        assert response_start(sent)["status"] == 200
        assert seen["path"] == "/items"
        assert seen["full_path"] == "/api/items"
        assert seen["root_path"] == "/api"
        assert seen["raw_path"] == b"/api/%69tems"
        assert seen["query_bytes"] == b"a=1&a=2"
        assert seen["repeated"] == ["one", "two"]
        assert seen["compat"] in ("one", "two")
        assert (b"x-multi", b"one") in seen["raw_headers"]
        assert (b"x-multi", b"two") in seen["raw_headers"]

    async def test_disconnect_does_not_hang_and_marks_request(self):
        scope = http_scope(path="/x", method="POST")
        incoming = [
            {"type": "http.request", "body": b"partial", "more_body": True},
            {"type": "http.disconnect"},
        ]
        harness = Harness(scope, incoming)
        request = await Request.from_asgi(scope, harness.receive)
        assert request.is_disconnected() is True
        assert await request.bytes() == b"partial"

    async def test_transport_failure_propagates_from_constructor(self):
        scope = http_scope(path="/x", method="POST")

        async def failing_receive():
            raise RuntimeError("boom-transport")

        with pytest.raises(RuntimeError, match="boom-transport"):
            await Request.from_asgi(scope, failing_receive)

    async def test_transport_failure_surfaces_as_500_not_empty_success(self):
        app = build_fixture_app()
        scope = http_scope(path="/echo-bytes", method="POST")

        async def failing_receive():
            raise RuntimeError("boom-transport")

        harness = Harness(scope, [])
        # At the application boundary the failure must surface as an error,
        # never as a fabricated empty 200.
        await app.asgi(scope, failing_receive, harness.send)
        assert response_start(harness.sent)["status"] == 500
        payload = json.loads(response_body(harness.sent))
        assert payload["error"] == "Internal server error"

    async def test_unexpected_message_type_is_an_error(self):
        app = build_fixture_app()
        sent = await run_asgi(
            app,
            http_scope(path="/echo-bytes", method="POST"),
            [{"type": "websocket.connect"}],
        )
        assert response_start(sent)["status"] == 500

    async def test_non_utf8_body_text_raises_bytes_preserved(self):
        seen: dict[str, Any] = {}
        app = Kinglet()

        @app.post("/bin", public=True)
        async def binary(request):
            seen["bytes"] = await request.bytes()
            try:
                await request.text()
            except UnicodeDecodeError:
                seen["text_raised"] = True
            return {"ok": True}

        sent = await run_asgi(
            app,
            http_scope(path="/bin", method="POST"),
            body_messages(b"\xff\xfe-binary"),
        )
        assert response_start(sent)["status"] == 200
        assert seen["bytes"] == b"\xff\xfe-binary"
        assert seen.get("text_raised") is True


def request_like():
    """Minimal request stand-in for direct error-pipeline checks."""

    class _Stub:
        request_id = "test-stub"

    return _Stub()


# ---------------------------------------------------------------------------
# B. Response emission
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestResponseEmission:
    async def test_event_ordering_and_status(self):
        app = build_fixture_app()
        sent = await run_asgi(app, http_scope(path="/health"), body_messages(b""))
        start = response_start(sent)
        assert start["status"] == 200
        assert sent[0]["type"] == "http.response.start"
        assert sent[1]["type"] == "http.response.body"
        assert sent[1]["more_body"] is False
        assert json.loads(response_body(sent)) == {"ok": True}

    async def test_repeated_set_cookie_preserved(self):
        app = build_fixture_app()
        sent = await run_asgi(app, http_scope(path="/cookies"), body_messages(b""))
        cookies = [v for k, v in sent_headers(sent) if k == b"set-cookie"]
        assert cookies == [b"a=1; Path=/", b"b=2; Path=/"]

    async def test_bodyless_204_has_no_body(self):
        app = build_fixture_app()
        sent = await run_asgi(app, http_scope(path="/empty"), body_messages(b""))
        assert response_start(sent)["status"] == 204
        assert response_body(sent) == b""

    async def test_unsupported_content_types_raise(self):
        from kinglet.asgi import send_response

        for bad in (object(), 42, ("a", "b"), {"a", "b"}):
            sent: list[dict[str, Any]] = []
            with pytest.raises(TypeError):
                await send_response(_append_send(sent), Response(bad))

    async def test_workers_native_response_rejected_not_stringified(self):
        from kinglet.asgi import send_response

        fake = _fake_workers_response()
        sent: list[dict[str, Any]] = []
        with pytest.raises(TypeError, match="Workers-native"):
            await send_response(_append_send(sent), Response(fake))
        with pytest.raises(TypeError, match="Workers-native"):
            await send_response(_append_send(sent), fake)

    async def test_streaming_order_and_no_full_buffering(self):
        release = asyncio.Event()
        produced: list[bytes] = []

        async def producer():
            produced.append(b"one")
            yield b"one"
            await release.wait()
            produced.append(b"two")
            yield b"two"

        app = Kinglet()

        @app.get("/s", public=True)
        async def streamed(request):
            return Response(producer(), content_type="text/plain")

        sent: list[dict[str, Any]] = []

        async def send(message):
            sent.append(message)
            if (
                message.get("type") == "http.response.body"
                and message.get("body") == b"one"
            ):
                release.set()

        harness = Harness(http_scope(path="/s"), body_messages(b""), on_send=None)
        await app.asgi(harness.scope, harness.receive, send)
        bodies = [
            m.get("body", b"") for m in sent if m.get("type") == "http.response.body"
        ]
        assert bodies[0] == b"one"
        assert produced == [b"one", b"two"]
        assert b"".join(bodies) == b"onetwo"
        assert sent[-1]["more_body"] is False

    async def test_streaming_sync_iterable(self):
        from kinglet.asgi import send_response

        sent: list[dict[str, Any]] = []
        await send_response(_append_send(sent), Response(iter([b"a", "b", b"c"])))
        assert response_body(sent) == b"abc"

    async def test_bad_chunk_type_raises_after_start(self):
        from kinglet.asgi import send_response

        async def producer():
            yield b"ok"
            yield 42

        sent: list[dict[str, Any]] = []
        with pytest.raises(TypeError, match="chunk"):
            await send_response(_append_send(sent), Response(producer()))
        assert response_start(sent)["status"] == 200
        assert len([m for m in sent if m["type"] == "http.response.start"]) == 1

    async def test_cancellation_runs_stream_cleanup_no_second_response(self):
        closed: list[bool] = []

        async def producer():
            try:
                yield b"x"
                yield b"y"
            finally:
                closed.append(True)

        app = Kinglet()

        @app.get("/c", public=True)
        async def cancellable(request):
            return Response(producer())

        sent: list[dict[str, Any]] = []

        async def send(message):
            sent.append(message)
            if message.get("type") == "http.response.body" and message.get("more_body"):
                raise asyncio.CancelledError()

        harness = Harness(http_scope(path="/c"), body_messages(b""))
        with pytest.raises(asyncio.CancelledError):
            await app.asgi(harness.scope, harness.receive, send)
        assert closed == [True]
        assert len([m for m in sent if m["type"] == "http.response.start"]) == 1


def _append_send(sent):
    async def send(message):
        sent.append(message)

    return send


def _fake_workers_response():
    cls = type("Response", (), {})
    cls.__module__ = "workers"
    return cls()


# ---------------------------------------------------------------------------
# I. Boundary-branch coverage (new adapter code, no threshold changes)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestBoundaryBranches:
    async def test_str_and_bytearray_bodies(self):
        from kinglet.asgi import send_response

        sent: list[dict[str, Any]] = []
        await send_response(_append_send(sent), Response("hello"))
        assert response_body(sent) == b"hello"

        sent = []
        await send_response(_append_send(sent), Response(bytearray(b"ab")))
        assert response_body(sent) == b"ab"

    async def test_bare_bytes_default_octet_stream(self):
        from kinglet.asgi import send_response

        sent: list[dict[str, Any]] = []
        await send_response(_append_send(sent), Response(b"\x00\x01"))
        assert (b"content-type", b"application/octet-stream") in sent_headers(sent)

    async def test_bytes_and_tuple_header_values(self):
        from kinglet.asgi import send_response

        sent: list[dict[str, Any]] = []
        await send_response(
            _append_send(sent),
            Response(
                "x",
                headers={"X-Raw": b"raw", "X-Multi": ("one", "two")},
            ),
        )
        headers = sent_headers(sent)
        assert (b"x-raw", b"raw") in headers
        assert (b"x-multi", b"one") in headers
        assert (b"x-multi", b"two") in headers

    async def test_non_serializable_dict_raises(self):
        from kinglet.asgi import send_response

        sent: list[dict[str, Any]] = []
        with pytest.raises(TypeError, match="not JSON-serializable"):
            await send_response(_append_send(sent), Response({"x": object()}))

    async def test_non_response_non_foreign_raises(self):
        from kinglet.asgi import send_response

        with pytest.raises(TypeError, match="requires a Kinglet Response"):
            await send_response(_append_send([]), 42)

    async def test_sync_iterable_close_runs_on_completion(self):
        from kinglet.asgi import send_response

        closed: list[bool] = []

        class SyncStream:
            def __iter__(self):
                yield b"a"
                yield b"b"

            def close(self):
                closed.append(True)

        sent: list[dict[str, Any]] = []
        await send_response(_append_send(sent), Response(SyncStream()))
        assert response_body(sent) == b"ab"
        assert closed == [True]

    async def test_bytearray_chunks(self):
        from kinglet.asgi import send_response

        sent: list[dict[str, Any]] = []
        await send_response(_append_send(sent), Response(iter([bytearray(b"a"), "b"])))
        assert response_body(sent) == b"ab"

    async def test_scope_coercions_and_host_fallbacks(self):
        scope = http_scope(path="/items")
        scope["path"] = 123  # type: ignore[dict-item]
        scope["root_path"] = 45  # type: ignore[dict-item]
        del scope["server"]
        request = await Request.from_asgi(scope, _receive_all(body_messages(b"")))
        assert request.path == "123"
        assert request.root_path == "45"
        assert "localhost" in request.url

    async def test_legacy_bytes_text_fallback(self):
        from unittest.mock import AsyncMock, Mock

        raw = Mock()
        raw.method = "POST"
        raw.url = "http://localhost/up"
        raw.headers = {}
        del raw.arrayBuffer  # no binary accessor: falls back to text()
        raw.text = AsyncMock(return_value="hi")
        request = Request(raw, {})
        assert await request.bytes() == b"hi"
        # Cached: the transport is not consumed twice.
        raw.text.assert_awaited_once()
        assert await request.bytes() == b"hi"

    async def test_getlist_legacy_fallback_and_query_all(self):
        from unittest.mock import Mock

        raw = Mock()
        raw.method = "GET"
        raw.url = "http://localhost/s?a=1&a=2&b="
        raw.headers = {"X-Solo": "solo"}
        request = Request(raw, {})
        assert request.getlist("x-solo") == ["solo"]
        assert request.getlist("missing") == []
        assert request.query_all("a") == ["1", "2"]

    async def test_append_header_list_branch(self):
        response = Response({"ok": True})
        response.append_header("Set-Cookie", "a=1")
        response.append_header("set-cookie", "b=2")
        response.append_header("Set-Cookie", "c=3")
        values = [v for k, v in response.headers.items() if k.lower() == "set-cookie"]
        assert values == [["a=1", "b=2", "c=3"]]

    async def test_legacy_custom_handler_returning_dict_and_raising(self):
        class RawRequest:
            method = "GET"
            url = "http://localhost/boom"

            class headers:
                @staticmethod
                def items():
                    return []

        app = Kinglet()

        @app.get("/boom", public=True)
        async def boom(request):
            from kinglet import HTTPError

            raise HTTPError(500, "nope")

        @app.exception_handler(500)
        async def handler(request, exc):
            return {"custom": True}

        result = await app(RawRequest(), {})
        assert isinstance(result, Response)
        assert result.content == {"custom": True}

        app2 = Kinglet()

        @app2.get("/boom", public=True)
        async def boom2(request):
            from kinglet import HTTPError

            raise HTTPError(500, "nope")

        @app2.exception_handler(500)
        async def bad_handler(request, exc):
            raise RuntimeError("handler-failed")

        result2 = await app2(RawRequest(), {})
        assert isinstance(result2, Response)
        assert result2.status == 500

    async def test_legacy_wrapped_foreign_content_passes_through(self):
        fake = _fake_workers_response()

        class RawRequest:
            method = "GET"
            url = "http://localhost/boom"

            class headers:
                @staticmethod
                def items():
                    return []

        app = Kinglet()

        @app.get("/boom", public=True)
        async def boom(request):
            from kinglet import HTTPError

            raise HTTPError(500, "nope")

        @app.exception_handler(500)
        async def handler(request, exc):
            return Response(fake)

        assert await app(RawRequest(), {}) is fake

    async def test_legacy_request_construction_failure_uses_custom_handler(self):
        app = Kinglet()

        @app.exception_handler(500)
        async def handler(request, exc):
            return {"custom": True}

        class BadRaw:
            @property
            def url(self):
                raise RuntimeError("unparsable")

        result = await app(BadRaw(), {})
        assert isinstance(result, Response)
        assert result.content == {"custom": True}

    async def test_lifespan_send_failure_does_not_raise(self):
        app = build_fixture_app()

        async def failing_receive():
            raise RuntimeError("nope")

        async def failing_send(message):
            raise RuntimeError("send-gone")

        await app.asgi({"type": "lifespan"}, failing_receive, failing_send)

    @pytest.mark.parametrize("status", [204, 304])
    async def test_bodyless_streaming_status_closes_stream_uniterated(
        self, status: int
    ):
        from kinglet.asgi import send_response

        iterated: list[bool] = []

        async def producer():
            iterated.append(True)
            yield b"x"

        sent: list[dict[str, Any]] = []
        await send_response(_append_send(sent), Response(producer(), status=status))
        assert response_start(sent)["status"] == status
        assert response_body(sent) == b""
        assert iterated == []

    async def test_bodyless_buffered_status_discards_before_serializing(self):
        from kinglet.asgi import send_response

        sent: list[dict[str, Any]] = []
        await send_response(_append_send(sent), Response(object(), status=204))
        assert response_start(sent)["status"] == 204
        assert response_body(sent) == b""

    async def test_start_cancellation_still_closes_owned_stream(self):
        from kinglet.asgi import send_response

        closed: list[bool] = []

        class EagerStream:
            def __aiter__(self):
                return self._gen()

            async def _gen(self):
                yield b"x"

            async def aclose(self):
                closed.append(True)

        async def send(message):
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await send_response(send, Response(EagerStream()))
        assert closed == [True]

    async def test_distinct_stream_iterator_closed_on_failure(self):
        from kinglet.asgi import send_response

        closed: list[bool] = []

        class DistinctStream:
            def __aiter__(self):
                return self._gen()

            async def _gen(self):
                try:
                    yield b"x"
                    yield b"y"
                finally:
                    closed.append(True)

        sent: list[dict[str, Any]] = []

        async def send(message):
            sent.append(message)
            if message.get("type") == "http.response.body" and message.get("more_body"):
                raise RuntimeError("send-gone")

        with pytest.raises(RuntimeError, match="send-gone"):
            await send_response(send, Response(DistinctStream()))
        assert closed == [True]
        assert len([m for m in sent if m["type"] == "http.response.start"]) == 1

    async def test_start_send_failure_closes_owned_stream(self):
        from kinglet.asgi import send_response

        closed: list[bool] = []

        class EagerStream:
            def __aiter__(self):
                return self._gen()

            async def _gen(self):
                yield b"x"

            async def aclose(self):
                closed.append(True)

        async def send(message):
            raise RuntimeError("start-gone")

        with pytest.raises(RuntimeError, match="start-gone"):
            await send_response(send, Response(EagerStream()))
        assert closed == [True]

    async def test_decoded_delimiter_not_reparsed_as_query(self):
        # No raw_path: the server already decoded %3F before handing us
        # the scope, so the literal "?" must not become query data.
        scope = http_scope(path="/items/foo?admin=1", query=b"")
        assert "raw_path" not in scope
        request = await Request.from_asgi(scope, _receive_all(body_messages(b"")))
        assert request.query_params == {}
        assert request.query_string == ""
        assert request.query_all("admin") == []
        assert "%3F" in request.url

    async def test_fallback_request_has_isolated_state(self):
        from kinglet.core import _FallbackRequest

        first, second = _FallbackRequest(), _FallbackRequest()
        assert first.scope is None
        assert first.path_params == {}
        first.headers["x"] = "1"
        first.query_params["q"] = "1"
        first.state.marker = "a"
        assert second.headers == {}
        assert second.query_params == {}
        assert not hasattr(second.state, "marker")


# ---------------------------------------------------------------------------
# C. Prefixes and mounting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPrefixesAndMounting:
    def _prefixed(self, prefix: str) -> Kinglet:
        app = Kinglet(root_path=prefix)

        @app.get("/items", public=True)
        async def items(request):
            return {"route": "items", "path": request.path}

        return app

    def _plain(self) -> Kinglet:
        app = Kinglet()

        @app.get("/items", public=True)
        async def items(request):
            return {"route": "items", "path": request.path}

        return app

    async def _get(self, app, incoming_path, mount=""):
        scope = http_scope(path=incoming_path, root_path=mount)
        sent = await run_asgi(app, scope, body_messages(b""))
        return response_start(sent)["status"], json.loads(response_body(sent) or b"{}")

    async def test_prefix_mount_matrix(self):
        cases = [
            (self._plain(), "", "/items", 200),
            (self._prefixed("/api"), "", "/api/items", 200),
            (self._plain(), "/api", "/api/items", 200),
            (self._prefixed("/v1"), "/api", "/api/v1/items", 200),
        ]
        for app, mount, incoming, expected in cases:
            status, payload = await self._get(app, incoming, mount)
            assert status == expected, (mount, incoming)
            assert payload["route"] == "items"

    async def test_mount_applies_on_segment_boundaries(self):
        app = self._plain()
        status, _ = await self._get(app, "/apix", mount="/api")
        assert status == 404
        status, _ = await self._get(app, "/api/items", mount="/api")
        assert status == 200

    async def test_trailing_slash_behavior_unchanged(self):
        app = self._plain()
        status, _ = await self._get(app, "/items/")
        assert status == 404


# ---------------------------------------------------------------------------
# D. Lifespan and unsupported scopes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLifespan:
    async def test_startup_shutdown_ack(self):
        app = build_fixture_app()
        harness = Harness(
            {"type": "lifespan", "asgi": {"version": "3.0"}},
            [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}],
        )
        await app.asgi(harness.scope, harness.receive, harness.send)
        assert harness.sent == [
            {"type": "lifespan.startup.complete"},
            {"type": "lifespan.shutdown.complete"},
        ]

    async def test_repeated_lifespans_are_independent(self):
        app = build_fixture_app()
        for _ in range(2):
            harness = Harness(
                {"type": "lifespan"},
                [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}],
            )
            await app.asgi(harness.scope, harness.receive, harness.send)
            assert harness.sent == [
                {"type": "lifespan.startup.complete"},
                {"type": "lifespan.shutdown.complete"},
            ]
        # No global "already started" flag gates later HTTP traffic.
        sent = await run_asgi(app, http_scope(path="/health"), body_messages(b""))
        assert response_start(sent)["status"] == 200

    async def test_unknown_lifespan_messages_ignored(self):
        app = build_fixture_app()
        harness = Harness(
            {"type": "lifespan"},
            [
                {"type": "lifespan.startup"},
                {"type": "lifespan.something-else"},
                {"type": "lifespan.shutdown"},
            ],
        )
        await app.asgi(harness.scope, harness.receive, harness.send)
        assert harness.sent == [
            {"type": "lifespan.startup.complete"},
            {"type": "lifespan.shutdown.complete"},
        ]

    async def test_lifespan_failure_reported_explicitly(self):
        app = build_fixture_app()
        sent: list[dict[str, Any]] = []

        async def failing_receive():
            raise RuntimeError("nope")

        async def send(message):
            sent.append(message)

        await app.asgi({"type": "lifespan"}, failing_receive, send)
        assert sent == [{"type": "lifespan.startup.failed", "message": "nope"}]

    async def test_websocket_scope_rejected(self):
        app = build_fixture_app()
        harness = Harness({"type": "websocket", "path": "/"}, [])
        with pytest.raises(RuntimeError, match="Unsupported ASGI scope type"):
            await app.asgi(harness.scope, harness.receive, harness.send)

    async def test_from_asgi_rejects_non_http_scope(self):
        async def noop_receive():
            raise AssertionError("must not be called")

        with pytest.raises(TypeError):
            await Request.from_asgi({"type": "websocket"}, noop_receive)


# ---------------------------------------------------------------------------
# E. Environment and request state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEnvironmentAndState:
    async def test_scope_env_used_with_identity_preserved(self):
        seen: dict[str, Any] = {}
        db = object()
        app = Kinglet()

        @app.get("/db", public=True)
        async def db_route(request):
            seen["db"] = request.env.DB
            return {"ok": True}

        scope = http_scope(path="/db", env={"DB": db, "NAME": "x"})
        sent = await run_asgi(app, scope, body_messages(b""))
        assert response_start(sent)["status"] == 200
        assert seen["db"] is db

    async def test_explicit_env_wins_over_scope_env(self):
        app = Kinglet()

        @app.get("/n", public=True)
        async def name(request):
            return {"name": request.env.NAME}

        scope = http_scope(path="/n", env={"NAME": "scope"})
        request = await Request.from_asgi(
            scope, _receive_all(body_messages(b"")), env={"NAME": "explicit"}
        )
        assert request.env.NAME == "explicit"

    async def test_with_env_wrapper_injects_settings(self):
        app = build_fixture_app()
        wrapped = with_env(app.asgi, build_smoke_scope_env())
        scope = http_scope(path="/env-name")
        harness = Harness(scope, body_messages(b""))
        await wrapped(scope, harness.receive, harness.send)
        assert json.loads(response_body(harness.sent)) == {"name": "smoke"}

    async def test_public_route_needs_no_bindings(self):
        app = build_fixture_app()
        sent = await run_asgi(app, http_scope(path="/health"), body_messages(b""))
        assert response_start(sent)["status"] == 200

    async def test_missing_binding_fails_explicitly(self):
        app = build_fixture_app()
        sent = await run_asgi(app, http_scope(path="/env-name"), body_messages(b""))
        assert response_start(sent)["status"] == 500

    async def test_no_automatic_secret_discovery(self, monkeypatch):
        monkeypatch.setenv("KINGLET_SNEAKY_SECRET", "planted")
        app = Kinglet()

        @app.get("/s", public=True)
        async def sneak(request):
            return {"has": hasattr(request.env, "KINGLET_SNEAKY_SECRET")}

        sent = await run_asgi(app, http_scope(path="/s"), body_messages(b""))
        assert json.loads(response_body(sent)) == {"has": False}

    async def test_lifespan_state_seeds_fresh_request_state(self):
        shared = {"conn": object()}
        seen: dict[str, Any] = {}
        app = Kinglet()

        @app.get("/r", public=True)
        async def res(request):
            seen["shared"] = request.state.shared
            request.state.marker = "per-request"
            seen["leaked"] = "marker" in request.scope.get("state", {})
            return {"ok": True}

        scope = http_scope(path="/r", state={"shared": shared["conn"]})
        sent = await run_asgi(app, scope, body_messages(b""))
        assert response_start(sent)["status"] == 200
        assert seen["shared"] is shared["conn"]
        assert seen["leaked"] is False

        # A later request without lifespan state gets a clean namespace.
        seen.clear()
        sent = await run_asgi(app, http_scope(path="/r"), body_messages(b""))
        assert response_start(sent)["status"] == 500  # no shared binding present
        assert "shared" not in seen

    async def test_interleaved_requests_do_not_leak(self):
        app = build_fixture_app()
        first = run_asgi(
            app,
            http_scope(path="/slow", query=b"m=one", env={"NAME": "env-one"}),
            body_messages(b""),
        )
        second = run_asgi(
            app,
            http_scope(path="/slow", query=b"m=two", env={"NAME": "env-two"}),
            body_messages(b""),
        )
        sent_first, sent_second = await asyncio.gather(first, second)
        got = {
            json.loads(response_body(sent_first))["marker"],
            json.loads(response_body(sent_second))["marker"],
        }
        assert got == {"one", "two"}
        envs = {
            json.loads(response_body(sent_first))["env"],
            json.loads(response_body(sent_second))["env"],
        }
        assert envs == {"env-one", "env-two"}


def _receive_all(messages):
    messages = list(messages)

    async def receive():
        return messages.pop(0)

    return receive


# ---------------------------------------------------------------------------
# F. Security invariants through the ASGI entry point
# ---------------------------------------------------------------------------


@pytest.mark.route_policy
@pytest.mark.asyncio
class TestAsgiSecurity:
    def _secure_app(self, record: list[str]) -> Kinglet:
        app = Kinglet()

        @app.get("/public", public=True)
        async def public(request):
            return {"ok": True}

        @app.get("/private")
        @require_auth
        async def private(request):
            record.append("private")
            return {"id": request.state.user["id"]}

        @app.get("/claimed")
        @require_claim("role", "admin")
        async def claimed(request):
            record.append("claimed")
            return {"admin": True}

        return app

    async def test_public_accessible(self):
        sent = await run_asgi(
            self._secure_app([]), http_scope(path="/public"), body_messages(b"")
        )
        assert response_start(sent)["status"] == 200

    async def test_protected_without_credentials_denied_handler_not_run(self):
        record: list[str] = []
        app = self._secure_app(record)
        sent = await run_asgi(
            app,
            http_scope(path="/private", env={"JWT_SECRET": SECRET}),
            body_messages(b""),
        )
        assert response_start(sent)["status"] == 401
        assert record == []

    async def test_wrong_claim_denied_handler_not_run(self):
        record: list[str] = []
        app = self._secure_app(record)
        sent = await run_asgi(
            app,
            http_scope(
                path="/claimed",
                headers=auth_headers({"role": "viewer"}),
                env={"JWT_SECRET": SECRET},
            ),
            body_messages(b""),
        )
        assert response_start(sent)["status"] == 403
        assert record == []

    async def test_authorized_caller_succeeds(self):
        record: list[str] = []
        app = self._secure_app(record)
        sent = await run_asgi(
            app,
            http_scope(
                path="/claimed",
                headers=auth_headers({"role": "admin"}),
                env={"JWT_SECRET": SECRET},
            ),
            body_messages(b""),
        )
        assert response_start(sent)["status"] == 200
        assert record == ["claimed"]

    async def test_missing_platform_secret_does_not_skip_auth(self):
        record: list[str] = []
        app = self._secure_app(record)
        sent = await run_asgi(
            app,
            http_scope(
                path="/private",
                headers=auth_headers({"role": "admin"}),
                env={},
            ),
            body_messages(b""),
        )
        assert response_start(sent)["status"] == 401
        assert record == []

    async def test_bare_registration_and_reversed_order_fail_closed(self):
        app = Kinglet()
        with pytest.raises(RuntimeError):
            app.router.add_route("/bare", _unprotected, ["GET"])

        app2 = Kinglet()
        with pytest.raises(RuntimeError):

            @require_auth
            @app2.get("/reversed", public=True)
            async def reversed_handler(request):
                return {"ok": True}

    async def test_same_named_handlers_dispatch_by_identity(self):
        app = Kinglet()

        def make(value):
            async def handler(request):
                return {"v": value}

            handler.__name__ = "same"
            return handler

        app.router.add_route("/one", make(1), ["GET"], public=True)
        app.router.add_route("/two", make(2), ["GET"], public=True)
        for path, expected in (("/one", 1), ("/two", 2)):
            sent = await run_asgi(app, http_scope(path=path), body_messages(b""))
            assert json.loads(response_body(sent)) == {"v": expected}

    async def test_restrictive_parent_subrouter_policy_enforced(self):
        sub = Router(enforce_route_policy=False)

        @sub.route("/open", methods=["GET"], public=True)
        async def sub_open(request):
            return {"ok": True}

        parent = Kinglet()
        parent.include_router("/sub", sub)
        sent = await run_asgi(parent, http_scope(path="/sub/open"), body_messages(b""))
        assert response_start(sent)["status"] == 200

        strict_sub = Router(enforce_route_policy=False)

        @strict_sub.route("/bare", methods=["GET"])
        async def sub_bare(request):
            return {"ok": True}

        with pytest.raises(RuntimeError):
            parent.include_router("/other", strict_sub)

    async def test_production_error_redacted(self):
        app = Kinglet(debug=False)

        @app.get("/boom", public=True)
        async def boom(request):
            raise RuntimeError("secret-sauce-failure")

        sent = await run_asgi(app, http_scope(path="/boom"), body_messages(b""))
        assert response_start(sent)["status"] == 500
        raw = response_body(sent)
        payload = json.loads(raw)
        assert payload["error"] == "Internal server error"
        assert b"secret-sauce" not in raw
        assert b"Traceback" not in raw

    async def test_custom_error_handler_runs_on_asgi_path(self):
        app = Kinglet()

        @app.get("/missing-thing", public=True)
        async def missing_thing(request):
            from kinglet import HTTPError

            raise HTTPError(404, "gone-fishing")

        @app.exception_handler(404)
        async def not_found(request, exc):
            return Response({"custom": True, "message": str(exc)}, status=404)

        sent = await run_asgi(
            app, http_scope(path="/missing-thing"), body_messages(b"")
        )
        assert response_start(sent)["status"] == 404
        assert json.loads(response_body(sent))["custom"] is True


async def _unprotected(request):
    return {"ok": True}


# ---------------------------------------------------------------------------
# G. HTTPX integration against the real exported callable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestHttpxIntegration:
    async def test_routing_middleware_auth_errors_bodies_env(self):
        from kinglet import TimingMiddleware

        app = build_fixture_app()
        app.add_middleware(TimingMiddleware())
        wrapped = with_env(
            app.asgi, {"NAME": "httpx", "JWT_SECRET": SECRET, "ENVIRONMENT": "test"}
        )
        transport = httpx.ASGITransport(app=wrapped)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            health = await client.get("/health")
            assert health.status_code == 200
            assert health.json() == {"ok": True}
            assert "X-Response-Time" in health.headers

            echo = await client.post("/echo-json", json={"a": 1})
            assert echo.json() == {"received": {"a": 1}}

            binary = bytes(range(256)) * 64
            up = await client.post(
                "/echo-bytes",
                content=binary,
                headers={"Content-Type": "application/octet-stream"},
            )
            assert bytes(up.content) == binary

            cookies = await client.get("/cookies")
            assert cookies.headers.get_list("set-cookie") == [
                "a=1; Path=/",
                "b=2; Path=/",
            ]

            denied = await client.get("/whoami")
            assert denied.status_code == 401

            allowed = await client.get("/whoami", headers=auth_headers({}))
            assert allowed.json() == {"id": "user-1"}

            env = await client.get("/env-name")
            assert env.json() == {"name": "httpx"}

            empty = await client.get("/empty")
            assert empty.status_code == 204

            stream = await client.get("/stream")
            assert bytes(stream.content) == b"chunk-one-chunk-two-chunk-three"

            boom = await client.get("/boom")
            assert boom.status_code == 500
            assert boom.json()["error"] == "Internal server error"


# ---------------------------------------------------------------------------
# H. Legacy Worker entry parity + boundary divergence
# ---------------------------------------------------------------------------


class TestLegacyParity:
    def test_same_fixture_through_legacy_test_client(self):
        app = build_fixture_app()
        client = TestClient(app, env={"NAME": "legacy", "JWT_SECRET": SECRET})
        status, _, body = client.request("GET", "/health")
        assert status == 200
        assert json.loads(body) == {"ok": True}

        status, _, body = client.request("GET", "/env-name")
        assert status == 200
        assert json.loads(body) == {"name": "legacy"}

        status, _, body = client.request(
            "GET", "/whoami", headers=auth_headers({"role": "admin"})
        )
        assert status == 200
        assert json.loads(body) == {"id": "user-1"}

    @pytest.mark.asyncio
    async def test_legacy_passes_workers_native_through_asgi_rejects(self):
        fake = _fake_workers_response()
        app = Kinglet()

        @app.get("/native", public=True)
        async def native(request):
            return fake

        class RawRequest:
            method = "GET"
            url = "http://localhost/native"

            class headers:
                @staticmethod
                def items():
                    return []

        result = await app(RawRequest(), {})
        assert result is fake

        with pytest.raises(TypeError, match="Workers-native"):
            await run_asgi(app, http_scope(path="/native"), body_messages(b""))

    @pytest.mark.asyncio
    async def test_trusted_origin_not_spoofable_on_plain_asgi(self):
        from kinglet.utils import _trusted_request_origin

        scope = http_scope(path="/", headers={"host": "evil.example"})
        request = await Request.from_asgi(scope, _receive_all(body_messages(b"")))
        assert _trusted_request_origin(request) is None

        scope = http_scope(path="/", headers={"host": "127.0.0.1:8000"})
        request = await Request.from_asgi(scope, _receive_all(body_messages(b"")))
        origin = _trusted_request_origin(request)
        assert origin is not None and "127.0.0.1" in origin
