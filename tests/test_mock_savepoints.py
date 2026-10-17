"""Savepoint fidelity tests for MockD1Database.

Pins the transaction/savepoint semantics the mock claims to understand
(BEGIN/COMMIT/ROLLBACK/SAVEPOINT/RELEASE) against real SQLite behavior.
Written BEFORE the stack/depth model; each test must fail on the old
single-bool bookkeeping and pass after.
"""

import pytest

from kinglet.testing import D1DatabaseError, MockD1Database

SCHEMA = "CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)"


@pytest.fixture
def db():
    database = MockD1Database()
    yield database
    database.close()


async def _rows(db, where=""):
    result = await db.prepare(f"SELECT v FROM t {where}".rstrip() + " ORDER BY v").all()
    return [r["v"] for r in result.results]


class TestSavepointSemantics:
    @pytest.mark.asyncio
    async def test_nested_script_from_spec(self, db):
        """The full nested scenario behaves like real SQLite."""
        await db.exec(SCHEMA)
        await db.exec("BEGIN")
        await db.exec("SAVEPOINT a")
        await db.prepare("INSERT INTO t (v) VALUES (?)").bind("outer").run()
        await db.exec("SAVEPOINT b")
        await db.prepare("INSERT INTO t (v) VALUES (?)").bind("inner").run()
        await db.exec("ROLLBACK TO b")
        assert await _rows(db) == ["outer"]
        await db.exec("RELEASE b")
        await db.exec("RELEASE a")
        await db.exec("COMMIT")
        assert await _rows(db) == ["outer"]

    @pytest.mark.asyncio
    async def test_savepoint_suppresses_auto_commit(self, db):
        await db.exec(SCHEMA)
        await db.exec("SAVEPOINT a")
        await db.prepare("INSERT INTO t (v) VALUES (?)").bind("x").run()
        # Uncommitted work is still pending: the write must NOT have auto-committed.
        assert db._conn.in_transaction
        await db.exec("ROLLBACK")
        assert await _rows(db) == []

    @pytest.mark.asyncio
    async def test_rollback_to_preserves_surrounding(self, db):
        await db.exec(SCHEMA)
        await db.exec("BEGIN")
        await db.exec("SAVEPOINT a")
        await db.prepare("INSERT INTO t (v) VALUES (?)").bind("keep").run()
        await db.exec("SAVEPOINT b")
        await db.prepare("INSERT INTO t (v) VALUES (?)").bind("drop").run()
        await db.exec("ROLLBACK TO b")
        assert db._in_explicit_transaction
        # ROLLBACK TO keeps the named savepoint on the stack (SQLite semantics).
        assert db._savepoint_stack == ["A", "B"]
        # Still managed: a further write stays uncommitted until COMMIT.
        await db.prepare("INSERT INTO t (v) VALUES (?)").bind("after").run()
        assert db._conn.in_transaction
        await db.exec("RELEASE b")
        await db.exec("RELEASE a")
        await db.exec("COMMIT")
        assert await _rows(db) == ["after", "keep"]

    @pytest.mark.asyncio
    async def test_release_inner_does_not_commit_outer(self, db):
        await db.exec(SCHEMA)
        await db.exec("BEGIN")
        await db.exec("SAVEPOINT a")
        await db.prepare("INSERT INTO t (v) VALUES (?)").bind("x").run()
        await db.exec("SAVEPOINT b")
        await db.prepare("INSERT INTO t (v) VALUES (?)").bind("y").run()
        await db.exec("RELEASE b")
        # Outer scope still open: nothing committed yet.
        assert db._conn.in_transaction
        # A full ROLLBACK still undoes the released inner work (it merged, not committed).
        await db.exec("ROLLBACK")
        assert await _rows(db) == []
        assert not db._in_explicit_transaction
        assert db._savepoint_stack == []

    @pytest.mark.asyncio
    async def test_release_outermost_savepoint_commits(self, db):
        """SQLite semantics: releasing the outermost savepoint commits."""
        await db.exec(SCHEMA)
        await db.exec("SAVEPOINT a")
        await db.prepare("INSERT INTO t (v) VALUES (?)").bind("x").run()
        await db.exec("RELEASE a")
        assert not db._conn.in_transaction
        assert not db._in_explicit_transaction
        assert db._savepoint_stack == []
        # The write was committed by the outermost RELEASE: a later
        # BEGIN/ROLLBACK cycle cannot undo it.
        await db.exec("BEGIN")
        await db.exec("ROLLBACK")
        assert await _rows(db) == ["x"]

    @pytest.mark.asyncio
    async def test_full_rollback_clears_all_state(self, db):
        await db.exec(SCHEMA)
        await db.exec("BEGIN")
        await db.exec("SAVEPOINT a")
        await db.prepare("INSERT INTO t (v) VALUES (?)").bind("x").run()
        await db.exec("ROLLBACK")
        assert not db._in_explicit_transaction
        assert db._savepoint_stack == []
        assert await _rows(db) == []
        # Bookkeeping cleared: the next write auto-commits again.
        await db.prepare("INSERT INTO t (v) VALUES (?)").bind("y").run()
        assert not db._conn.in_transaction
        assert await _rows(db) == ["y"]

    @pytest.mark.asyncio
    async def test_full_commit_clears_all_state(self, db):
        await db.exec(SCHEMA)
        await db.exec("BEGIN")
        await db.exec("SAVEPOINT a")
        await db.prepare("INSERT INTO t (v) VALUES (?)").bind("x").run()
        await db.exec("COMMIT")
        assert not db._in_explicit_transaction
        assert db._savepoint_stack == []
        assert await _rows(db) == ["x"]

    @pytest.mark.asyncio
    async def test_failed_control_statement_preserves_bookkeeping(self, db):
        await db.exec(SCHEMA)
        await db.exec("BEGIN")
        await db.exec("SAVEPOINT a")
        with pytest.raises(D1DatabaseError):
            await db.exec("RELEASE no_such_savepoint")
        with pytest.raises(D1DatabaseError):
            await db.exec("ROLLBACK TO no_such_savepoint")
        with pytest.raises(D1DatabaseError):
            await db.exec("SAVEPOINT")
        with pytest.raises(D1DatabaseError):
            await db.exec("ROLLBACK TO")
        # Nothing mutated: still inside BEGIN + savepoint a.
        assert db._in_explicit_transaction
        assert db._savepoint_stack == ["A"]
        await db.prepare("INSERT INTO t (v) VALUES (?)").bind("x").run()
        assert db._conn.in_transaction
        await db.exec("RELEASE a")
        await db.exec("COMMIT")
        assert await _rows(db) == ["x"]

    @pytest.mark.asyncio
    async def test_simple_begin_commit_rollback_unchanged(self, db):
        await db.exec(SCHEMA)
        await db.exec("BEGIN")
        await db.prepare("INSERT INTO t (v) VALUES (?)").bind("kept").run()
        await db.exec("COMMIT")
        assert await _rows(db) == ["kept"]
        await db.exec("BEGIN")
        await db.prepare("INSERT INTO t (v) VALUES (?)").bind("dropped").run()
        await db.exec("ROLLBACK")
        assert await _rows(db) == ["kept"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rollback",
    [
        "ROLLBACK TO a",
        "ROLLBACK TRANSACTION TO a",
        "ROLLBACK TO SAVEPOINT a",
        "ROLLBACK TRANSACTION TO SAVEPOINT a",
    ],
)
async def test_optional_rollback_keywords_preserve_transaction(db, rollback):
    await db.exec(SCHEMA)
    await db.exec("BEGIN; SAVEPOINT a")
    await db.prepare("INSERT INTO t (v) VALUES ('before')").run()
    await db.exec("SAVEPOINT b")
    await db.prepare("INSERT INTO t (v) VALUES ('nested')").run()
    await db.exec(rollback)
    assert await _rows(db) == []
    assert db._savepoint_stack == ["A"]
    # ROLLBACK TO retains its target, allowing reuse.
    await db.prepare("INSERT INTO t (v) VALUES ('again')").run()
    await db.exec(rollback)
    assert await _rows(db) == []
    await db.exec("RELEASE a")
    await db.prepare("INSERT INTO t (v) VALUES ('after')").run()
    assert db._conn.in_transaction
    await db.exec("ROLLBACK")
    assert await _rows(db) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("control", ["RELEASE a", "ROLLBACK TO a"])
@pytest.mark.parametrize("inner", ["a", '"a"'])
async def test_duplicate_savepoint_targets_innermost_match(db, control, inner):
    await db.exec(SCHEMA)
    # No explicit BEGIN: incorrect stack clearing would auto-commit writes.
    await db.exec("SAVEPOINT a")
    await db.prepare("INSERT INTO t (v) VALUES ('outer')").run()
    await db.exec(f"SAVEPOINT {inner}")
    await db.prepare("INSERT INTO t (v) VALUES ('inner')").run()
    await db.exec("SAVEPOINT b")
    await db.exec(control)
    if control.startswith("RELEASE"):
        assert db._savepoint_stack == ["A"]
        assert await _rows(db) == ["inner", "outer"]
    else:
        assert db._savepoint_stack == ["A", "A"]
        assert await _rows(db) == ["outer"]
    await db.prepare("INSERT INTO t (v) VALUES ('after')").run()
    assert db._conn.in_transaction
    await db.exec("ROLLBACK")
    assert await _rows(db) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "opened,target",
    [
        ('"a"', "a"),
        ("a", "[a]"),
        ("`a`", "'a'"),
        ('"two words"', "[two words]"),
        ('"a""b"', '`a"b`'),
    ],
)
async def test_quoted_savepoint_names_match_across_control_commands(db, opened, target):
    await db.exec(SCHEMA)
    await db.exec(f"SAVEPOINT {opened}")
    await db.prepare("INSERT INTO t (v) VALUES ('drop')").run()
    await db.exec(f"ROLLBACK TO SAVEPOINT {target}")
    assert await _rows(db) == []
    await db.exec(f"RELEASE SAVEPOINT {target}")
    assert db._savepoint_stack == []
    assert not db._in_explicit_transaction
    # Release ended the transaction: this write must commit automatically.
    await db.prepare("INSERT INTO t (v) VALUES ('keep')").run()
    assert not db._conn.in_transaction
    await db.exec("BEGIN; ROLLBACK")
    assert await _rows(db) == ["keep"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rollback",
    [
        "ROLLBACK -- return TO a clean state",
        "ROLLBACK /* TO a */",
        "ROLLBACK /* TO a",
        "/* leading TO */ ROLLBACK -- TO a",
    ],
)
async def test_rollback_comments_cannot_change_transaction_classification(db, rollback):
    await db.exec(SCHEMA)
    await db.exec('SAVEPOINT "a--/* TO */" /* trailing comment */')
    await db.prepare("INSERT INTO t (v) VALUES ('drop')").run()
    await db.exec(rollback)
    assert not db._in_explicit_transaction
    assert db._savepoint_stack == []
    await db.prepare("INSERT INTO t (v) VALUES ('keep')").run()
    assert not db._conn.in_transaction
    await db.exec("BEGIN; ROLLBACK")
    assert await _rows(db) == ["keep"]


@pytest.mark.asyncio
async def test_comments_between_savepoint_control_tokens(db):
    await db.exec(SCHEMA)
    await db.exec("/* before */ SAVEPOINT /* middle */ a--after")
    await db.prepare("INSERT INTO t (v) VALUES ('drop')").run()
    await db.exec("ROLLBACK /* comment */ TO /* comment */ SAVEPOINT a--after")
    assert await _rows(db) == []
    assert db._savepoint_stack == ["A"]
    await db.exec("RELEASE a--after")
    assert db._savepoint_stack == []


@pytest.mark.asyncio
async def test_non_ascii_savepoint_names_do_not_fold_to_ascii(db):
    await db.exec(SCHEMA)
    await db.exec('SAVEPOINT "ß"; SAVEPOINT "ss"')
    await db.prepare("INSERT INTO t (v) VALUES ('keep')").run()
    await db.exec('RELEASE "ß"')
    assert db._savepoint_stack == []
    assert not db._in_explicit_transaction
    await db.prepare("INSERT INTO t (v) VALUES ('after')").run()
    assert not db._conn.in_transaction
    await db.exec("BEGIN; ROLLBACK")
    assert await _rows(db) == ["after", "keep"]
