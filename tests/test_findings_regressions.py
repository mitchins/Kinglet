"""Behavioral regressions for actionable security-review findings."""

import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from kinglet import Kinglet
from kinglet.authz import require_auth
from kinglet.http import Request
from kinglet.testing import D1DatabaseError, MockD1Database

from .asgi_harness import Harness, body_messages, http_scope, response_start


@pytest.mark.asyncio
async def test_unauthenticated_request_does_not_read_body():
    app = Kinglet()

    @app.post("/private")
    @require_auth
    async def private(request):
        return await request.json()

    receive = AsyncMock(side_effect=AssertionError("body read before authentication"))
    harness = Harness(http_scope("/private", method="POST"), [])
    await app.asgi(harness.scope, receive, harness.send)
    assert response_start(harness.sent)["status"] == 401
    receive.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("accessor", ["bytes", "text", "json"])
async def test_chunked_body_limit_without_content_length(accessor):
    app = Kinglet(max_body_size=4)

    @app.post("/body", public=True)
    async def body(request):
        await getattr(request, accessor)()
        return {"ok": True}

    harness = Harness(http_scope("/body", method="POST"), body_messages(b"12345", 2))
    await app.asgi(harness.scope, harness.receive, harness.send)
    assert response_start(harness.sent)["status"] == 413


@pytest.mark.asyncio
async def test_body_exactly_at_limit_is_cached():
    harness = Harness(http_scope(), body_messages(b"1234", 2))
    request = await Request.from_asgi(
        harness.scope, harness.receive, max_body_size=4, lazy=True
    )
    assert await request.bytes() == b"1234"
    assert await request.text() == "1234"
    assert await request.json() == 1234


@pytest.mark.asyncio
@pytest.mark.parametrize("first", [True, False])
async def test_workers_json_conversion_modes_consume_once(first):
    raw = SimpleNamespace(
        url="https://test/",
        method="POST",
        headers={},
        json=AsyncMock(return_value={"a": 1}),
    )
    request = Request(raw)
    assert await request.json(first) == {"a": 1}
    assert await request.json(not first) == {"a": 1}
    raw.json.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("authorization", ["", "Bearer incorrect", "Bearer ÿ"])
async def test_r2_upload_fails_closed_before_body_or_storage(authorization):
    spec = importlib.util.spec_from_file_location(
        "r2_demo", Path(__file__).parents[1] / "examples/demo-r2/app.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for env, expected in [
        (SimpleNamespace(), 503),
        (SimpleNamespace(UPLOAD_TOKEN="secret"), 401),
    ]:
        harness = Harness(
            http_scope(
                "/media",
                method="POST",
                env=env,
                headers={"authorization": authorization},
            ),
            [],
        )
        receive = AsyncMock(side_effect=AssertionError("unauthorized upload read"))
        await module.app.asgi(harness.scope, receive, harness.send)
        assert response_start(harness.sent)["status"] == expected
        receive.assert_not_awaited()


@pytest.mark.asyncio
async def test_mock_transaction_recovers_after_statement_error():
    db = MockD1Database()
    await db.exec("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    await db.exec("BEGIN")
    await db.prepare("INSERT INTO t VALUES (1)").run()
    with pytest.raises(D1DatabaseError):
        await db.prepare("INSERT INTO t VALUES (1)").run()
    await db.prepare("INSERT INTO t VALUES (2)").run()
    assert not db._conn.in_transaction
    assert not db._in_explicit_transaction
    rows = await db.prepare("SELECT id FROM t").all()
    assert rows.results == [{"id": 2}]


@pytest.mark.asyncio
async def test_mock_concurrent_batches_are_atomic():
    db = MockD1Database()
    await db.exec("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    await asyncio.gather(
        *(db.batch([db.prepare("INSERT INTO t VALUES (?)").bind(i)]) for i in range(20))
    )
    rows = await db.prepare("SELECT id FROM t").all()
    assert len(rows.results) == 20


@pytest.mark.asyncio
async def test_mock_rollback_failure_preserves_wrapped_sql_error():
    import sqlite3
    from unittest.mock import Mock

    db = MockD1Database()
    connection = Mock(wraps=db._conn)
    connection.in_transaction = db._conn.in_transaction
    connection.rollback.side_effect = sqlite3.OperationalError("rollback unavailable")
    db._conn = connection
    with pytest.raises(D1DatabaseError, match="no such table"):
        await db.prepare("INSERT INTO missing VALUES (1)").run()
    assert not db._in_explicit_transaction


@pytest.mark.asyncio
async def test_concurrent_body_accessors_share_one_chunked_read():
    payload = b'{"message": "complete"}'
    messages = iter(body_messages(payload, 3))
    calls = 0

    async def receive():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return next(messages)

    request = await Request.from_asgi(http_scope(), receive, lazy=True)
    results = await asyncio.wait_for(
        asyncio.gather(request.bytes(), request.text(), request.json()), timeout=1
    )
    assert results == [payload, payload.decode(), {"message": "complete"}]
    assert calls == len(body_messages(payload, 3))


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["limit", "transport"])
async def test_body_read_failure_is_shared_without_retry(failure):
    from kinglet import HTTPError

    messages = iter(body_messages(b"12345", 2))
    calls = 0

    async def receive():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        if failure == "transport":
            raise RuntimeError("broken transport")
        return next(messages)

    request = await Request.from_asgi(http_scope(), receive, lazy=True, max_body_size=1)
    results = await asyncio.wait_for(
        asyncio.gather(
            request.bytes(), request.text(), request.json(), return_exceptions=True
        ),
        timeout=1,
    )
    expected = HTTPError if failure == "limit" else RuntimeError
    assert all(isinstance(result, expected) for result in results)
    if failure == "limit":
        assert all(result.status_code == 413 for result in results)
    with pytest.raises(expected):
        await request.bytes()
    assert calls == 1


@pytest.mark.asyncio
async def test_failed_rollback_preserves_active_transaction_until_recovery():
    import sqlite3
    from unittest.mock import Mock

    db = MockD1Database()
    await db.exec("CREATE TABLE t (id INTEGER PRIMARY KEY); BEGIN; SAVEPOINT a")
    await db.prepare("INSERT INTO t VALUES (1)").run()
    real = db._conn
    connection = Mock(wraps=real)
    connection.in_transaction = True
    connection.rollback.side_effect = sqlite3.OperationalError("rollback unavailable")
    db._conn = connection
    with pytest.raises(D1DatabaseError):
        await db.prepare("INSERT INTO t VALUES (1)").run()
    assert db._in_explicit_transaction
    assert db._savepoint_stack == ["A"]
    await db.prepare("INSERT INTO t VALUES (2)").run()
    connection.commit.assert_not_called()
    db._conn = real
    await db.exec("ROLLBACK")
    assert not db._in_explicit_transaction
    assert (await db.prepare("SELECT * FROM t").all()).results == []
