"""
Mock D1 Database for Unit Testing

This module re-exports the MockD1Database implementation from kinglet.testing
for backward compatibility and convenience.

Why a re-export?
    The canonical implementation lives in kinglet.testing so it can be
    imported directly via `from kinglet import MockD1Database`. This re-export
    allows existing tests using `from tests.mock_d1 import MockD1Database`
    to continue working.

Provides an in-memory D1 database implementation that mimics
Cloudflare Workers D1 API for testing without requiring actual
Cloudflare Workers environment or Miniflare.

Usage:
    from tests.mock_d1 import MockD1Database
    # or
    from kinglet import MockD1Database

    db = MockD1Database()
    await db.exec("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    await db.prepare("INSERT INTO users (name) VALUES (?)").bind("Alice").run()
    result = await db.prepare("SELECT * FROM users").all()
"""

# Re-export from kinglet.testing for backward compatibility
from kinglet.testing import (
    D1DatabaseError,
    D1ExecResult,
    D1MockError,
    D1PreparedStatementError,
    D1Result,
    D1ResultMeta,
    MockD1Database,
    MockD1PreparedStatement,
    d1_unwrap,
    d1_unwrap_results,
)

__all__ = [
    "MockD1Database",
    "MockD1PreparedStatement",
    "D1Result",
    "D1ResultMeta",
    "D1ExecResult",
    "D1MockError",
    "D1DatabaseError",
    "D1PreparedStatementError",
    "d1_unwrap",
    "d1_unwrap_results",
]
