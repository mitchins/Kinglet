"""
Kinglet Testing Utilities - TestClient and Mock classes

This module provides testing utilities for Kinglet applications:
- TestClient: Simple sync wrapper for testing without HTTP overhead
- MockD1Database: In-memory D1 database for unit testing
- MockR2Bucket: In-memory R2 storage for unit testing
- MockEmailSender: In-memory email sender for unit testing
"""

import asyncio
import builtins
import hashlib
import io
import json
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .storage import (
    d1_unwrap as _storage_d1_unwrap,
)
from .storage import (
    d1_unwrap_results as _storage_d1_unwrap_results,
)


class TestClient:
    """Simple sync wrapper for testing Kinglet apps without HTTP/Wrangler overhead"""

    __test__ = False  # Tell pytest this is not a test class

    def __init__(self, app, base_url="https://testserver", env=None):
        self.app = app
        self.base_url = base_url.rstrip("/")
        self.env = env or {}

        # Enable test mode on the app if it's a Kinglet instance
        if hasattr(app, "test_mode"):
            app.test_mode = True

    def request(
        self, method: str, path: str, json_data=None, data=None, headers=None, **kwargs
    ):
        """Make a test request and return (status, headers, body)"""
        import asyncio

        return asyncio.run(
            self._async_request(method, path, json_data, data, headers, **kwargs)
        )

    def _prepare_request_data(self, json_data, data, headers, kwargs):
        """Prepare request headers and body content"""
        # Handle 'json' keyword argument (common in test APIs)
        if "json" in kwargs and json_data is None:
            json_data = kwargs.pop("json")

        # Prepare headers
        test_headers = {"content-type": "application/json"} if json_data else {}
        if headers:
            test_headers.update({k.lower(): v for k, v in headers.items()})

        # Prepare body
        body_content = ""
        if json_data is not None:
            body_content = json.dumps(json_data)
            test_headers["content-type"] = "application/json"
        elif data is not None:
            body_content = str(data)

        return test_headers, body_content

    def _serialize_response_content(self, content):
        """Serialize response content for test consumption"""
        if isinstance(content, dict | list):
            return json.dumps(content)
        return str(content) if content is not None else ""

    def _handle_kinglet_response(self, response):
        """Handle Kinglet Response objects"""
        if hasattr(response, "status") and hasattr(response, "content"):
            status = response.status
            headers = response.headers
            content = response.content
            body = self._serialize_response_content(content)
            return status, headers, body
        return None

    def _handle_raw_response(self, response):
        """Handle raw response objects (dict, string, etc.)"""
        if isinstance(response, dict):
            return 200, {}, json.dumps(response)
        elif isinstance(response, str):
            return 200, {}, response
        else:
            return 200, {}, str(response)

    async def _async_request(
        self, method: str, path: str, json_data=None, data=None, headers=None, **kwargs
    ):
        """Internal async request handler"""
        test_headers, body_content = self._prepare_request_data(
            json_data, data, headers, kwargs
        )
        url = f"{self.base_url}{path}"

        # Create mock objects
        mock_request = MockRequest(method, url, test_headers, body_content)
        mock_env = MockEnv(self.env)

        try:
            response = await self.app(mock_request, mock_env)

            # Try to handle as Kinglet Response first
            kinglet_result = self._handle_kinglet_response(response)
            if kinglet_result:
                return kinglet_result

            # Handle as raw response
            return self._handle_raw_response(response)

        except Exception as e:
            error_body = json.dumps({"error": str(e)})
            return 500, {}, error_body


class MockRequest:
    """Mock request object for testing that matches Workers request interface"""

    def __init__(self, method: str, url: str, headers: dict, body: str = ""):
        self.method = method
        self.url = url
        self.headers = MockHeaders(headers)
        self._body = body

    async def text(self):
        return self._body

    async def json(self):
        if self._body:
            return json.loads(self._body)
        return None


class MockHeaders:
    """Mock headers object that matches Workers headers interface"""

    def __init__(self, headers_dict):
        self._headers = {k.lower(): v for k, v in (headers_dict or {}).items()}

    def get(self, key, default=None):
        return self._headers.get(key.lower(), default)

    def items(self):
        return self._headers.items()

    def __iter__(self):
        return iter(self._headers.items())


class MockEnv:
    """Mock environment object for testing"""

    def __init__(self, env_dict):
        # Set defaults for common Cloudflare bindings
        # Use MockD1Database for full D1 API compatibility
        self.DB = env_dict.get("DB") or _create_default_mock_db()
        self.ENVIRONMENT = env_dict.get("ENVIRONMENT", "test")

        # Add any additional environment variables
        for key, value in env_dict.items():
            setattr(self, key, value)


def _create_default_mock_db():
    """Create default mock database (deferred to avoid circular import)"""
    return MockD1Database()


class MockDatabase:
    """
    Simple mock D1 database stub for basic testing.

    .. deprecated::
        Use MockD1Database instead for full D1 API compatibility including
        proper SQL execution, transactions, and result metadata.

        Example:
            from kinglet import MockD1Database
            env = {"DB": MockD1Database()}
    """

    def __init__(self):
        self._data = {}

    def prepare(self, sql: str):
        return MockQuery(sql, self._data)


class MockQuery:
    """Mock D1 prepared statement"""

    def __init__(self, sql: str, data: dict):
        self.sql = sql
        self.data = data
        self.bindings = []

    def bind(self, *args):
        self.bindings = args
        return self

    async def run(self):
        return MockResult({"changes": 1, "last_row_id": 1})

    async def first(self):
        return MockRow({"id": 1, "name": "Test"})

    async def all(self):
        return MockResult([{"id": 1, "name": "Test"}])


class MockRow:
    """Mock D1 row result with to_py() method"""

    def __init__(self, data):
        self.data = data

    def to_py(self):
        return self.data


class MockResult:
    """Mock D1 query result"""

    def __init__(self, data):
        if isinstance(data, dict):
            self.meta = data
            self.results = []
        else:
            self.results = data
            self.meta = {"changes": len(data)}


# =============================================================================
# D1 Mock Implementation - Comprehensive Cloudflare D1 Database Mock
# =============================================================================


class D1MockError(Exception):
    """Base exception for D1 mock errors"""

    pass


class D1DatabaseError(D1MockError):
    """Raised when a database operation fails"""

    pass


class D1PreparedStatementError(D1MockError):
    """Raised when a prepared statement operation fails"""

    pass


@dataclass
class D1ResultMeta:
    """Metadata from D1 query execution"""

    duration: float = 0.0
    last_row_id: int | None = None
    changes: int = 0
    rows_read: int = 0
    rows_written: int = 0
    size_after: int | None = None


class D1Result:
    """
    D1 query result matching Cloudflare Workers D1 API

    Provides the same interface as real D1 results including:
    - results: List of row dicts
    - success: Boolean status
    - meta: Execution metadata (duration, last_row_id, changes, etc.)
    """

    def __init__(
        self,
        results: list[dict] | None = None,
        success: bool = True,
        meta: D1ResultMeta | None = None,
        error: str | None = None,
    ):
        self.results = results or []
        self.success = success
        self.meta = meta or D1ResultMeta()
        self.error = error

    def to_py(self) -> dict:
        """Convert to Python dict (mimics JsProxy.to_py())"""
        return {
            "results": self.results,
            "success": self.success,
            "meta": {
                "duration": self.meta.duration,
                "last_row_id": self.meta.last_row_id,
                "changes": self.meta.changes,
                "rows_read": self.meta.rows_read,
                "rows_written": self.meta.rows_written,
                "size_after": self.meta.size_after,
            },
        }


@dataclass
class D1ExecResult:
    """Result from D1Database.exec() for schema operations"""

    count: int = 0
    duration: float = 0.0

    def to_py(self) -> dict:
        """Convert to Python dict"""
        return {"count": self.count, "duration": self.duration}


class MockD1PreparedStatement:
    """
    Mock D1 prepared statement matching Cloudflare Workers D1 API

    Supports all D1PreparedStatement methods:
    - bind(*params): Bind parameters to the statement
    - first(column?): Execute and return first row or specific column
    - all(): Execute and return all results with metadata
    - run(): Execute statement (alias for all())
    - raw(columnNames?): Execute and return array of arrays
    """

    def __init__(self, db: "MockD1Database", sql: str):
        self._db = db
        self._sql = sql
        self._params: list = []

    def bind(self, *params) -> "MockD1PreparedStatement":
        """
        Bind parameters to the prepared statement

        Supports both positional (?) and ordered (?NNN) parameters.
        Returns self for method chaining.
        """
        self._params = list(params)
        return self

    async def first(self, column: str | None = None) -> dict | Any | None:
        """
        Execute and return the first row

        Args:
            column: Optional column name to return just that value

        Returns:
            - If column is specified: The value of that column, or None
            - If no column: The entire first row as a dict, or None
        """
        results = await self._execute()

        if not results:
            return None

        first_row = results[0]

        if column is not None:
            if column not in first_row:
                raise D1PreparedStatementError(
                    f"D1_ERROR: Column '{column}' does not exist"
                )
            return first_row[column]

        return first_row

    async def all(self) -> D1Result:
        """
        Execute and return all results with metadata

        Returns:
            D1Result with results list and metadata
        """
        start_time = time.time()
        results = await self._execute()
        duration = time.time() - start_time

        sql_upper = self._sql.strip().upper()
        is_write = sql_upper.startswith(("INSERT", "UPDATE", "DELETE"))

        meta = D1ResultMeta(
            duration=duration,
            rows_read=len(results) if not is_write else 0,
            rows_written=self._db._last_changes if is_write else 0,
            last_row_id=self._db._last_row_id
            if sql_upper.startswith("INSERT")
            else None,
            changes=self._db._last_changes if is_write else 0,
        )

        return D1Result(results=results, success=True, meta=meta)

    async def run(self) -> D1Result:
        """
        Execute statement (functionally equivalent to all())

        Returns:
            D1Result with results and metadata
        """
        return await self.all()

    async def raw(self, options: dict[str, bool] | None = None) -> list[list]:
        """
        Execute and return results as array of arrays

        Args:
            options: Dict with optional 'columnNames' boolean
                     If columnNames=True, first row contains column names

        Returns:
            List of lists (rows as arrays). Returns empty list [] even when
            columnNames=True if there are no results (no header row is
            included for empty result sets).
        """
        results = await self._execute()

        if not results:
            return []

        include_column_names = options and options.get("columnNames", False)
        columns = list(results[0].keys()) if results else []

        raw_results = []
        if include_column_names:
            raw_results.append(columns)

        for row in results:
            raw_results.append([row.get(col) for col in columns])

        return raw_results

    async def _execute(self) -> list[dict]:
        """Execute the SQL statement and return results"""
        return await self._db._execute_sql(self._sql, self._params)


class MockD1Database:
    """
    Mock D1 Database for Unit Testing

    Provides an in-memory SQLite implementation that mimics the
    Cloudflare Workers D1 API. Enables unit tests to run without
    requiring actual Cloudflare Workers environment or Miniflare.

    Supported operations:
    - prepare(query) - Create a prepared statement
    - batch(statements) - Execute multiple statements atomically
    - exec(sql) - Execute raw SQL (for schema creation)

    Type Conversion (matching D1):
    - None → NULL
    - int/float → INTEGER/REAL
    - str → TEXT
    - bool → INTEGER (0/1)
    - bytes → BLOB

    Usage:
        from kinglet import MockD1Database

        db = MockD1Database()
        await db.exec("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")

        stmt = db.prepare("INSERT INTO users (name) VALUES (?)").bind("Alice")
        result = await stmt.run()

        users = await db.prepare("SELECT * FROM users").all()
        for user in users.results:
            print(user["name"])
    """

    def __init__(self, db_path: str = ":memory:", *, foreign_keys: bool = True):
        """
        Initialize mock D1 database

        Args:
            db_path: SQLite database path (default: in-memory)
            foreign_keys: Enable foreign key constraints (default: True).
                         SQLite defaults to OFF; we enable for realistic behavior.
        """
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        if foreign_keys:
            self._conn.execute("PRAGMA foreign_keys = ON")
        self._last_row_id: int | None = None
        self._last_changes: int = 0
        self._in_batch: bool = False  # Track batch context for transaction handling

    @property
    def conn(self) -> sqlite3.Connection:
        """
        Direct access to SQLite connection for backward compatibility

        Note: Prefer using the D1-compatible API (prepare/exec/batch) for
        portable code. This property is provided for tests that need
        direct SQLite access for verification.
        """
        return self._conn

    def prepare(self, sql: str) -> MockD1PreparedStatement:
        """
        Prepare an SQL statement

        Args:
            sql: SQL query with optional ? placeholders

        Returns:
            MockD1PreparedStatement for binding and execution
        """
        return MockD1PreparedStatement(self, sql)

    async def batch(self, statements: list[MockD1PreparedStatement]) -> list[D1Result]:
        """
        Execute multiple statements in a batch

        D1 batch operations are transactional - if any statement fails,
        the entire batch is rolled back.

        Args:
            statements: List of prepared statements to execute

        Returns:
            List of D1Result objects in the same order as input
        """
        results = []

        # Set batch mode to prevent individual commits
        self._in_batch = True

        try:
            # Explicit BEGIN for clarity (SQLite auto-starts transactions,
            # but being explicit makes the transactional intent clear)
            self._conn.execute("BEGIN")

            for stmt in statements:
                result = await stmt.run()
                results.append(result)

            # Commit all statements together
            self._conn.commit()

        except Exception as e:
            self._conn.rollback()
            raise D1DatabaseError(f"Batch operation failed: {e}") from e
        finally:
            # Always reset batch mode
            self._in_batch = False

        return results

    async def exec(self, sql: str) -> D1ExecResult:
        """
        Execute raw SQL directly (for schema creation)

        Supports multiple statements separated by semicolons.
        Does not support parameter binding. All statements are executed
        atomically - if any statement fails, all are rolled back.

        Note:
            Statement splitting uses simple semicolon detection. Semicolons
            inside string literals will incorrectly split statements. This
            is acceptable for typical DDL/fixture SQL but avoid complex
            string values in exec() calls.

        Args:
            sql: Raw SQL to execute

        Returns:
            D1ExecResult with count of executed statements
        """
        start_time = time.time()

        def _do_exec() -> int:
            cursor = self._conn.cursor()
            count_local = 0
            try:
                cursor.execute("BEGIN")
                for statement in sql.split(";"):
                    statement = statement.strip()
                    if statement:
                        cursor.execute(statement)
                        count_local += 1
                self._conn.commit()
                return count_local
            except sqlite3.Error as e:  # pragma: no cover - error path
                self._conn.rollback()
                raise e

        try:
            count = await asyncio.to_thread(_do_exec)
            duration = time.time() - start_time
            return D1ExecResult(count=count, duration=duration)
        except sqlite3.Error as e:  # pragma: no cover - error path
            raise D1DatabaseError(f"exec() failed: {e}") from e

    async def _execute_sql(self, sql: str, params: list) -> list[dict]:
        """
        Internal: Execute SQL and return results as list of dicts

        Uses asyncio.to_thread() to avoid blocking the event loop and
        delegates branches to smaller helpers to reduce complexity.
        """

        def _do_exec() -> list[dict]:
            cursor = self._conn.cursor()
            converted_params = self._convert_params(params)

            cursor.execute(sql, converted_params)
            op = self._operation(sql)
            if op == "SELECT":
                return self._handle_select(cursor)
            if op == "INSERT":
                return self._handle_insert(cursor, sql)
            if op in ("UPDATE", "DELETE"):
                return self._handle_write(cursor, sql)
            return self._handle_ddl()

        try:
            return await asyncio.to_thread(_do_exec)
        except sqlite3.Error as e:  # pragma: no cover - error path
            # Ensure transient write transactions are not left open
            self._conn.rollback()
            raise D1DatabaseError(f"SQL error: {e}") from e

    def _convert_params(self, params: list) -> list:
        converted_params: list = []
        for param in params:
            if isinstance(param, bool):
                converted_params.append(1 if param else 0)
            else:
                converted_params.append(param)
        return converted_params

    def _operation(self, sql: str) -> str:
        return (sql.strip().split()[0] if sql.strip() else "").upper()

    def _has_returning_clause(self, sql: str) -> bool:
        """
        Check if SQL statement has a RETURNING clause
        
        Note: Uses simple regex detection that may match RETURNING in string literals
        or comments. This is acceptable for typical SQL usage in ORM/testing contexts.
        For production use cases requiring strict parsing, consider using sqlparse.
        """
        return bool(re.search(r'\bRETURNING\b', sql, re.IGNORECASE))

    def _handle_select(self, cursor: sqlite3.Cursor) -> list[dict]:
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def _handle_insert(self, cursor: sqlite3.Cursor, sql: str) -> list[dict]:
        # If the INSERT has a RETURNING clause, fetch results before commit
        if self._has_returning_clause(sql):
            rows = cursor.fetchall()
            if not self._in_batch:
                self._conn.commit()
            self._last_row_id = cursor.lastrowid
            self._last_changes = cursor.rowcount
            return [dict(row) for row in rows]

        # Standard INSERT without RETURNING
        if not self._in_batch:
            self._conn.commit()
        self._last_row_id = cursor.lastrowid
        self._last_changes = cursor.rowcount

        if self._last_row_id:
            table_name = self._extract_table_name(sql, "INSERT")
            if table_name:
                try:
                    safe_table = self._safe_identifier(table_name)
                    cursor.execute(  # nosec B608: safe_table validated by _safe_identifier  # NOSONAR
                        f'SELECT * FROM "{safe_table}" WHERE rowid = ?',  # NOSONAR # nosec
                        [self._last_row_id],
                    )
                    row = cursor.fetchone()
                    if row:
                        return [dict(row)]
                except sqlite3.Error:  # pragma: no cover - fallback path
                    # If fetching the inserted row fails (e.g., table without rowid),
                    # fall back to returning the last inserted id only.
                    return [{"id": self._last_row_id}] if self._last_row_id else []
        return [{"id": self._last_row_id}] if self._last_row_id else []

    def _handle_write(self, cursor: sqlite3.Cursor, sql: str) -> list[dict]:
        # If the UPDATE/DELETE has a RETURNING clause, fetch results before commit
        if self._has_returning_clause(sql):
            rows = cursor.fetchall()
            if not self._in_batch:
                self._conn.commit()
            self._last_changes = cursor.rowcount
            self._last_row_id = None
            return [dict(row) for row in rows]

        # Standard UPDATE/DELETE without RETURNING
        if not self._in_batch:
            self._conn.commit()
        self._last_changes = cursor.rowcount
        self._last_row_id = None
        return []

    def _handle_ddl(self) -> list[dict]:
        if not self._in_batch:
            self._conn.commit()
        return []

    def _extract_table_name(self, sql: str, operation: str) -> str | None:
        """Extract table name from SQL statement"""

        if operation == "INSERT":
            match = re.search(
                r"INSERT\s+(?:OR\s+\w+\s+)?INTO\s+[`\"\[]?(\w+)[`\"\]]?",
                sql,
                re.IGNORECASE,
            )
            return match.group(1) if match else None
        return None

    def _safe_identifier(self, name: str) -> str:
        """Validate and return a safe SQL identifier (table/column name)."""
        if not re.fullmatch(r"[A-Za-z_]\w*", name):
            raise D1DatabaseError(f"Unsafe SQL identifier: {name}")
        return name

    def close(self) -> None:
        """
        Close the database connection

        Safe to call multiple times (idempotent). After closing,
        subsequent database operations will raise an error.
        """
        if self._conn:
            self._conn.close()
            self._conn = None  # type: ignore[assignment]


"""Helper functions for D1 result unwrapping (delegate to storage variants)."""


def d1_unwrap(obj) -> dict:
    """Unwrap D1 result to Python dict, supporting mock result types."""
    if isinstance(obj, D1Result | D1ExecResult):
        return obj.to_py()
    return _storage_d1_unwrap(obj)


def d1_unwrap_results(results) -> list[dict]:
    """Unwrap a D1 results container to list[dict], supporting mock types."""
    if isinstance(results, D1Result):
        return results.results
    return _storage_d1_unwrap_results(results)


# =============================================================================
# R2 Mock Implementation
# =============================================================================


class R2MockError(Exception):
    """Base exception for R2 mock errors"""

    pass


class R2MultipartAbortedError(R2MockError):
    """Raised when attempting to operate on an aborted multipart upload"""

    pass


class R2MultipartCompletedError(R2MockError):
    """Raised when attempting to operate on a completed multipart upload"""

    pass


class R2PartNotFoundError(R2MockError):
    """Raised when a part is not found in a multipart upload"""

    pass


class R2TooManyKeysError(R2MockError):
    """Raised when attempting to delete more than 1000 keys"""

    pass


class R2MultipartUploadError(R2MockError):
    """Raised when a multipart upload fails to complete"""

    pass


@dataclass
class R2HTTPMetadata:
    """HTTP metadata for R2 objects"""

    contentType: str | None = None
    contentLanguage: str | None = None
    contentDisposition: str | None = None
    contentEncoding: str | None = None
    cacheControl: str | None = None
    cacheExpiry: datetime | None = None


@dataclass
class R2Checksums:
    """Checksums for R2 objects"""

    md5: bytes | None = None
    sha1: bytes | None = None
    sha256: bytes | None = None
    sha384: bytes | None = None
    sha512: bytes | None = None


@dataclass
class R2Range:
    """Range information for partial reads"""

    offset: int = 0
    length: int | None = None
    suffix: int | None = None


class MockR2Object:
    """
    Mock R2Object - metadata only (returned by head() and list())

    Matches the Workers R2Object interface.
    """

    def __init__(
        self,
        key: str,
        size: int,
        etag: str,
        uploaded: datetime,
        http_metadata: R2HTTPMetadata | None = None,
        custom_metadata: dict[str, str] | None = None,
        version: str | None = None,
        checksums: R2Checksums | None = None,
        storage_class: str = "Standard",
    ):
        self.key = key
        self.size = size
        self.etag = etag
        self.httpEtag = f'"{etag}"'
        self.uploaded = uploaded
        self.httpMetadata = http_metadata or R2HTTPMetadata()
        self.customMetadata = custom_metadata or {}
        self.version = version or str(uuid.uuid4())
        self.checksums = checksums or R2Checksums()
        self.storageClass = storage_class
        self.range: R2Range | None = None

    def writeHttpMetadata(self, headers: dict[str, str]) -> None:
        """Write HTTP metadata to headers dict"""
        if self.httpMetadata.contentType:
            headers["Content-Type"] = self.httpMetadata.contentType
        if self.httpMetadata.contentLanguage:
            headers["Content-Language"] = self.httpMetadata.contentLanguage
        if self.httpMetadata.contentDisposition:
            headers["Content-Disposition"] = self.httpMetadata.contentDisposition
        if self.httpMetadata.contentEncoding:
            headers["Content-Encoding"] = self.httpMetadata.contentEncoding
        if self.httpMetadata.cacheControl:
            headers["Cache-Control"] = self.httpMetadata.cacheControl


class MockR2ObjectBody(MockR2Object):
    """
    Mock R2ObjectBody - metadata plus body (returned by get())

    Matches the Workers R2ObjectBody interface with body as ReadableStream.
    """

    def __init__(
        self,
        key: str,
        size: int,
        etag: str,
        uploaded: datetime,
        data: bytes,
        http_metadata: R2HTTPMetadata | None = None,
        custom_metadata: dict[str, str] | None = None,
        version: str | None = None,
        checksums: R2Checksums | None = None,
        storage_class: str = "Standard",
        range_info: R2Range | None = None,
    ):
        super().__init__(
            key=key,
            size=size,
            etag=etag,
            uploaded=uploaded,
            http_metadata=http_metadata,
            custom_metadata=custom_metadata,
            version=version,
            checksums=checksums,
            storage_class=storage_class,
        )
        self._data = data
        self._body_used = False
        self.range = range_info

        # Mock ReadableStream-like body
        self.body = MockReadableStream(data)

    @property
    def bodyUsed(self) -> bool:
        return self._body_used

    async def arrayBuffer(self) -> bytes:
        """Return data as ArrayBuffer (bytes in Python)"""
        await asyncio.sleep(0)
        self._body_used = True
        return self._data

    async def text(self) -> str:
        """Return data as string"""
        await asyncio.sleep(0)
        self._body_used = True
        return self._data.decode("utf-8")

    async def json(self) -> Any:
        """Return data as parsed JSON"""
        await asyncio.sleep(0)
        self._body_used = True
        return json.loads(self._data.decode("utf-8"))

    async def blob(self) -> bytes:
        """Return data as Blob (bytes in Python)"""
        await asyncio.sleep(0)
        self._body_used = True
        return self._data


class MockReadableStream:
    """Mock ReadableStream for R2 body"""

    def __init__(self, data: bytes):
        self._data = data
        self._stream = io.BytesIO(data)
        self.locked = False

    def getReader(self):
        """Get a reader for the stream"""
        return MockStreamReader(self._stream)

    async def read(self) -> bytes:
        """Read all data from stream"""
        await asyncio.sleep(0)
        return self._data


class MockStreamReader:
    """Mock stream reader"""

    def __init__(self, stream: io.BytesIO):
        self._stream = stream

    async def read(self) -> dict[str, Any]:
        """Read next chunk"""
        await asyncio.sleep(0)
        chunk = self._stream.read(8192)
        if chunk:
            return {"value": chunk, "done": False}
        return {"value": None, "done": True}


@dataclass
class MockR2Objects:
    """
    Mock R2Objects - list() result

    Matches the Workers R2Objects interface.
    """

    objects: list[MockR2Object]
    truncated: bool = False
    cursor: str | None = None
    delimitedPrefixes: list[str] = field(default_factory=list)


@dataclass
class MockR2UploadedPart:
    """Represents an uploaded part in multipart upload"""

    partNumber: int
    etag: str


class MockR2MultipartUpload:
    """
    Mock R2MultipartUpload for multipart upload operations

    Supports uploadPart, abort, and complete operations.
    """

    def __init__(
        self,
        bucket: "MockR2Bucket",
        key: str,
        upload_id: str,
        http_metadata: R2HTTPMetadata | None = None,
        custom_metadata: dict[str, str] | None = None,
    ):
        self.key = key
        self.uploadId = upload_id
        self._bucket = bucket
        self._parts: dict[int, bytes] = {}
        self._http_metadata = http_metadata
        self._custom_metadata = custom_metadata
        self._aborted = False
        self._completed = False

    async def uploadPart(
        self, partNumber: int, value: bytes | str
    ) -> MockR2UploadedPart:
        """Upload a part to the multipart upload"""
        await asyncio.sleep(0)
        if self._aborted:
            raise R2MultipartAbortedError("Multipart upload has been aborted")
        if self._completed:
            raise R2MultipartCompletedError("Multipart upload has been completed")

        if isinstance(value, str):
            value = value.encode("utf-8")

        self._parts[partNumber] = value
        etag = hashlib.md5(value, usedforsecurity=False).hexdigest()

        return MockR2UploadedPart(partNumber=partNumber, etag=etag)

    async def abort(self) -> None:
        """Abort the multipart upload"""
        await asyncio.sleep(0)
        self._aborted = True
        self._parts.clear()
        if self.uploadId in self._bucket._multipart_uploads:
            del self._bucket._multipart_uploads[self.uploadId]

    async def complete(self, uploadedParts: list[MockR2UploadedPart]) -> MockR2Object:
        """Complete the multipart upload"""
        if self._aborted:
            raise R2MultipartAbortedError("Multipart upload has been aborted")
        if self._completed:
            raise R2MultipartCompletedError(
                "Multipart upload has already been completed"
            )

        sorted_parts = sorted(uploadedParts, key=lambda p: p.partNumber)

        data = b""
        for part in sorted_parts:
            if part.partNumber not in self._parts:
                raise R2PartNotFoundError(f"Part {part.partNumber} not found")
            data += self._parts[part.partNumber]

        options = {}
        if self._http_metadata:
            options["httpMetadata"] = {
                "contentType": self._http_metadata.contentType,
            }
        if self._custom_metadata:
            options["customMetadata"] = self._custom_metadata

        result = await self._bucket.put(self.key, data, options)
        self._completed = True

        if self.uploadId in self._bucket._multipart_uploads:
            del self._bucket._multipart_uploads[self.uploadId]

        if result is None:
            raise R2MultipartUploadError("Failed to complete multipart upload")
        return result


class MockR2Bucket:
    """
    Mock R2 Bucket for Unit Testing

    Provides an in-memory implementation of the Cloudflare Workers R2 API.
    All operations are async to match the real R2 API.

    Supported operations:
    - head(key) - Get object metadata only
    - get(key, options?) - Get object with body
    - put(key, value, options?) - Store object
    - delete(key | keys[]) - Delete object(s)
    - list(options?) - List objects with pagination
    - createMultipartUpload(key, options?) - Start multipart upload
    - resumeMultipartUpload(key, uploadId) - Resume multipart upload

    Usage:
        from kinglet import MockR2Bucket

        bucket = MockR2Bucket()
        await bucket.put("my-key", b"hello world", {"httpMetadata": {"contentType": "text/plain"}})
        obj = await bucket.get("my-key")
        content = await obj.text()
    """

    def __init__(self):
        self._objects: dict[str, dict[str, Any]] = {}
        self._multipart_uploads: dict[str, MockR2MultipartUpload] = {}

    async def head(self, key: str) -> MockR2Object | None:
        """
        Get object metadata without body

        Args:
            key: Object key

        Returns:
            MockR2Object with metadata, or None if not found
        """
        await asyncio.sleep(0)
        if key not in self._objects:
            return None

        stored = self._objects[key]
        return MockR2Object(
            key=key,
            size=stored["size"],
            etag=stored["etag"],
            uploaded=stored["uploaded"],
            http_metadata=stored.get("httpMetadata"),
            custom_metadata=stored.get("customMetadata"),
            version=stored.get("version"),
            checksums=stored.get("checksums"),
            storage_class=stored.get("storageClass", "Standard"),
        )

    async def get(
        self, key: str, options: dict[str, Any] | None = None
    ) -> MockR2ObjectBody | None:
        """
        Get object with body

        Args:
            key: Object key
            options: R2GetOptions (onlyIf, range)

        Returns:
            MockR2ObjectBody with body, or None if not found or preconditions not met
        """
        await asyncio.sleep(0)
        if key not in self._objects:
            return None

        stored = self._objects[key]
        data = stored["data"]
        range_info = None

        # Handle range requests
        if options and "range" in options:
            range_opts = options["range"]
            offset = range_opts.get("offset", 0)
            length = range_opts.get("length")
            suffix = range_opts.get("suffix")

            if suffix is not None:
                data = data[-suffix:]
                offset = max(0, len(stored["data"]) - suffix)
            elif length is not None:
                data = data[offset : offset + length]
            else:
                data = data[offset:]

            range_info = R2Range(offset=offset, length=len(data))

        # Handle conditional requests (onlyIf)
        if options and "onlyIf" in options:
            cond = options["onlyIf"]
            if "etagMatches" in cond and stored["etag"] != cond["etagMatches"]:
                # Precondition failed: return None (like real R2 API for 304/412)
                return None
            if (
                "etagDoesNotMatch" in cond
                and stored["etag"] == cond["etagDoesNotMatch"]
            ):
                # Precondition failed: return None (like real R2 API for 304/412)
                return None

        return MockR2ObjectBody(
            key=key,
            size=stored["size"],
            etag=stored["etag"],
            uploaded=stored["uploaded"],
            data=data,
            http_metadata=stored.get("httpMetadata"),
            custom_metadata=stored.get("customMetadata"),
            version=stored.get("version"),
            checksums=stored.get("checksums"),
            storage_class=stored.get("storageClass", "Standard"),
            range_info=range_info,
        )

    def _check_conditional_put(self, key: str, options: dict[str, Any]) -> bool:
        """Check if conditional put should proceed. Returns False if preconditions fail."""
        if "onlyIf" not in options:
            return True

        cond = options["onlyIf"]
        existing = self._objects.get(key)

        if "etagMatches" in cond:
            if not existing or existing["etag"] != cond["etagMatches"]:
                return False
        if "etagDoesNotMatch" in cond:
            if existing and existing["etag"] == cond["etagDoesNotMatch"]:
                return False
        return True

    def _parse_http_metadata(self, options: dict[str, Any]) -> R2HTTPMetadata | None:
        """Parse HTTP metadata from options"""
        if "httpMetadata" not in options:
            return None
        hm = options["httpMetadata"]
        return R2HTTPMetadata(
            contentType=hm.get("contentType"),
            contentLanguage=hm.get("contentLanguage"),
            contentDisposition=hm.get("contentDisposition"),
            contentEncoding=hm.get("contentEncoding"),
            cacheControl=hm.get("cacheControl"),
        )

    async def put(
        self,
        key: str,
        value: bytes | str | None,
        options: dict[str, Any] | None = None,
    ) -> MockR2Object | None:
        """
        Store an object

        Args:
            key: Object key
            value: Object data (bytes, string, or None)
            options: R2PutOptions (httpMetadata, customMetadata, checksums, etc.)

        Returns:
            MockR2Object with metadata, or None if conditional put fails
        """
        await asyncio.sleep(0)
        options = options or {}

        if isinstance(value, str):
            value = value.encode("utf-8")
        elif value is None:
            value = b""

        # Handle conditional put
        if not self._check_conditional_put(key, options):
            return None

        md5_hash = hashlib.md5(value, usedforsecurity=False).hexdigest()
        checksums = R2Checksums(md5=hashlib.md5(value, usedforsecurity=False).digest())
        http_metadata = self._parse_http_metadata(options)
        version = str(uuid.uuid4())
        uploaded = datetime.now(UTC)

        self._objects[key] = {
            "data": value,
            "size": len(value),
            "etag": md5_hash,
            "uploaded": uploaded,
            "httpMetadata": http_metadata,
            "customMetadata": options.get("customMetadata", {}),
            "version": version,
            "checksums": checksums,
            "storageClass": options.get("storageClass", "Standard"),
        }

        return MockR2Object(
            key=key,
            size=len(value),
            etag=md5_hash,
            uploaded=uploaded,
            http_metadata=http_metadata,
            custom_metadata=options.get("customMetadata", {}),
            version=version,
            checksums=checksums,
            storage_class=options.get("storageClass", "Standard"),
        )

    async def delete(self, keys: str | list[str]) -> None:
        """
        Delete one or more objects

        Args:
            keys: Single key or list of keys to delete (up to 1000)
        """
        await asyncio.sleep(0)
        if isinstance(keys, str):
            keys = [keys]

        if len(keys) > 1000:
            raise R2TooManyKeysError("Cannot delete more than 1000 keys at once")

        for key in keys:
            if key in self._objects:
                del self._objects[key]

    def _filter_keys_by_cursor(self, keys: list[str], cursor: str | None) -> list[str]:
        """Filter keys to start after the cursor position"""
        if not cursor:
            return keys
        for i, k in enumerate(keys):
            if k > cursor:
                return keys[i:]
        return []

    def _apply_delimiter(
        self, keys: list[str], prefix: str, delimiter: str
    ) -> tuple[list[str], list[str]]:
        """Apply delimiter to extract delimited prefixes and filter keys"""
        seen_prefixes: set[str] = set()
        delimited_prefixes: list[str] = []
        filtered_keys: list[str] = []

        for key in keys:
            remaining = key[len(prefix) :] if prefix else key
            delim_pos = remaining.find(delimiter)
            if delim_pos >= 0:
                dir_prefix = prefix + remaining[: delim_pos + 1]
                if dir_prefix not in seen_prefixes:
                    seen_prefixes.add(dir_prefix)
                    delimited_prefixes.append(dir_prefix)
            else:
                filtered_keys.append(key)

        return filtered_keys, delimited_prefixes

    def _build_object_for_list(self, key: str, include: list[str]) -> MockR2Object:
        """Build a MockR2Object for list results with optional metadata"""
        stored = self._objects[key]
        return MockR2Object(
            key=key,
            size=stored["size"],
            etag=stored["etag"],
            uploaded=stored["uploaded"],
            http_metadata=stored.get("httpMetadata")
            if "httpMetadata" in include
            else None,
            custom_metadata=stored.get("customMetadata")
            if "customMetadata" in include
            else None,
        )

    async def list(self, options: dict[str, Any] | None = None) -> MockR2Objects:
        """
        List objects in the bucket

        Args:
            options: R2ListOptions (limit, prefix, cursor, delimiter, include)

        Returns:
            MockR2Objects with matching objects
        """
        await asyncio.sleep(0)
        options = options or {}
        limit = min(options.get("limit", 1000), 1000)
        prefix = options.get("prefix", "")
        cursor = options.get("cursor")
        delimiter = options.get("delimiter")
        include = options.get("include", [])

        # Get all keys sorted and filtered by prefix
        all_keys = sorted(self._objects.keys())
        if prefix:
            all_keys = [k for k in all_keys if k.startswith(prefix)]

        # Apply cursor filtering
        all_keys = self._filter_keys_by_cursor(all_keys, cursor)

        # Apply delimiter
        delimited_prefixes: list[str] = []
        if delimiter:
            all_keys, delimited_prefixes = self._apply_delimiter(
                all_keys, prefix, delimiter
            )

        # Apply pagination
        truncated = len(all_keys) > limit
        result_keys = all_keys[:limit]
        next_cursor = result_keys[-1] if truncated and result_keys else None

        # Build result objects
        objects = [self._build_object_for_list(key, include) for key in result_keys]

        return MockR2Objects(
            objects=objects,
            truncated=truncated,
            cursor=next_cursor,
            delimitedPrefixes=sorted(delimited_prefixes),
        )

    def createMultipartUpload(
        self, key: str, options: dict[str, Any] | None = None
    ) -> MockR2MultipartUpload:
        """
        Create a new multipart upload

        Args:
            key: Object key
            options: R2MultipartOptions (httpMetadata, customMetadata, storageClass)

        Returns:
            MockR2MultipartUpload for managing the upload
        """
        options = options or {}
        upload_id = str(uuid.uuid4())

        http_metadata = None
        if "httpMetadata" in options:
            hm = options["httpMetadata"]
            http_metadata = R2HTTPMetadata(
                contentType=hm.get("contentType"),
            )

        upload = MockR2MultipartUpload(
            bucket=self,
            key=key,
            upload_id=upload_id,
            http_metadata=http_metadata,
            custom_metadata=options.get("customMetadata"),
        )

        self._multipart_uploads[upload_id] = upload
        return upload

    def resumeMultipartUpload(self, key: str, uploadId: str) -> MockR2MultipartUpload:
        """
        Resume an existing multipart upload

        Note: Like the real R2 API, this doesn't validate the upload exists.

        Args:
            key: Object key
            uploadId: Upload ID from createMultipartUpload

        Returns:
            MockR2MultipartUpload for managing the upload
        """
        if uploadId in self._multipart_uploads:
            return self._multipart_uploads[uploadId]

        upload = MockR2MultipartUpload(bucket=self, key=key, upload_id=uploadId)
        return upload

    # Utility methods for testing

    def clear(self) -> None:
        """Clear all objects from the bucket (test utility)"""
        self._objects.clear()
        self._multipart_uploads.clear()

    def get_all_keys(self) -> builtins.list[str]:
        """Get all keys in the bucket (test utility)"""
        return list(self._objects.keys())

    def object_count(self) -> int:
        """Get number of objects in the bucket (test utility)"""
        return len(self._objects)


# =============================================================================
# Email Mock Implementation - Mock SES Email Sender
# =============================================================================


class EmailMockError(Exception):
    """Base exception for email mock errors"""

    pass


@dataclass
class MockSentEmail:
    """
    Record of a sent email for test verification

    Contains all parameters passed to send_email() plus metadata
    about when it was sent and whether it succeeded.
    """

    from_email: str
    to: list[str]
    subject: str
    body_text: str
    body_html: str | None = None
    cc: list[str] | None = None
    bcc: list[str] | None = None
    reply_to: list[str] | None = None
    region: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    message_id: str | None = None
    success: bool = True
    error: str | None = None


class MockEmailSender:
    """
    Mock Email Sender for Unit Testing

    Provides an in-memory email sender that mimics the kinglet.ses.send_email()
    behavior. Enables unit tests to run without actual AWS SES or email delivery.

    Features:
    - Records all sent emails for test verification
    - Supports success/failure simulation
    - Async callbacks for awaiting email sends
    - Configurable default behavior (success/fail)

    Usage:
        from kinglet import MockEmailSender
        from kinglet.ses import EmailResult

        # Basic usage - automatically succeed
        sender = MockEmailSender()
        result = await sender.send_email(
            from_email="test@example.com",
            to=["user@example.com"],
            subject="Test",
            body_text="Hello"
        )
        assert result.success
        assert len(sender.sent_emails) == 1

        # Force specific emails to fail
        sender = MockEmailSender()
        sender.set_failure_for("user@example.com", "Invalid address")
        result = await sender.send_email(
            from_email="test@example.com",
            to=["user@example.com"],
            subject="Test",
            body_text="Hello"
        )
        assert not result.success
        assert "Invalid address" in result.error

        # Use with patching in tests
        with patch("kinglet.ses.send_email", sender.send_email):
            # Test code that sends emails
            ...
    """

    def __init__(self, *, default_success: bool = True):
        """
        Initialize mock email sender

        Args:
            default_success: Whether emails should succeed by default (True)
                           or fail by default (False)
        """
        self.sent_emails: list[MockSentEmail] = []
        self._default_success = default_success
        self._failures: dict[str, str] = {}  # email -> error message
        self._default_error: str | None = None

    async def send_email(
        self,
        env=None,
        *,
        from_email: str,
        to: list[str],
        subject: str,
        body_text: str,
        body_html: str | None = None,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        reply_to: list[str] | None = None,
        region: str | None = None,
    ):
        """
        Mock send_email implementation matching kinglet.ses.send_email signature

        Records the email and returns EmailResult based on configured behavior.
        Note: env parameter is accepted but ignored (for API compatibility).

        Args:
            env: Ignored (for API compatibility with real send_email)
            from_email: Sender email address
            to: List of recipient email addresses
            subject: Email subject
            body_text: Plain text email body
            body_html: Optional HTML email body
            cc: Optional CC recipients
            bcc: Optional BCC recipients
            reply_to: Optional reply-to addresses
            region: AWS region (recorded but not used)

        Returns:
            EmailResult from kinglet.ses module
        """
        # Import here to avoid circular dependency
        from .ses import EmailResult

        # Small async delay to simulate network I/O
        await asyncio.sleep(0)

        # Check if any recipient should fail
        failure_error = None
        for recipient in to:
            if recipient in self._failures:
                failure_error = self._failures[recipient]
                break

        # Determine success/failure
        if failure_error:
            success = False
            error = failure_error
            message_id = None
        elif not self._default_success:
            success = False
            error = self._default_error or "Mock email sender configured to fail"
            message_id = None
        else:
            success = True
            error = None
            message_id = str(uuid.uuid4())

        # Record the sent email
        sent_email = MockSentEmail(
            from_email=from_email,
            to=to,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            cc=cc,
            bcc=bcc,
            reply_to=reply_to,
            region=region,
            message_id=message_id,
            success=success,
            error=error,
        )
        self.sent_emails.append(sent_email)

        return EmailResult(success=success, message_id=message_id, error=error)

    def set_failure_for(self, email: str, error: str) -> None:
        """
        Configure a specific email address to fail

        Args:
            email: Email address that should fail
            error: Error message to return
        """
        self._failures[email] = error

    def clear_failures(self) -> None:
        """Clear all configured failures"""
        self._failures.clear()

    def set_default_failure(self, error: str | None = None) -> None:
        """
        Set all emails to fail by default

        Args:
            error: Optional custom error message
        """
        self._default_success = False
        self._default_error = error

    def set_default_success(self) -> None:
        """Set all emails to succeed by default"""
        self._default_success = True
        self._default_error = None

    def clear(self) -> None:
        """Clear all sent emails (test utility)"""
        self.sent_emails.clear()

    def get_sent_to(self, email: str) -> list[MockSentEmail]:
        """
        Get all emails sent to a specific address

        Args:
            email: Email address to filter by

        Returns:
            List of MockSentEmail records sent to that address
        """
        return [e for e in self.sent_emails if email in e.to]

    def get_by_subject(self, subject: str) -> list[MockSentEmail]:
        """
        Get all emails with a specific subject

        Args:
            subject: Subject line to filter by (exact match)

        Returns:
            List of MockSentEmail records with that subject
        """
        return [e for e in self.sent_emails if e.subject == subject]

    def assert_sent(
        self,
        *,
        to: str | None = None,
        subject: str | None = None,
        count: int | None = None,
    ) -> None:
        """
        Assert that emails matching criteria were sent

        Args:
            to: Optional email address to filter by
            subject: Optional subject to filter by
            count: Optional expected count of matching emails.
                   If not provided, asserts at least one email matches.

        Raises:
            AssertionError: If assertions fail
        """
        emails = self.sent_emails

        if to:
            emails = [e for e in emails if to in e.to]

        if subject:
            emails = [e for e in emails if e.subject == subject]

        if count is not None:
            actual = len(emails)
            if actual != count:
                raise AssertionError(
                    f"Expected {count} emails but found {actual}. "
                    f"Filters: to={to}, subject={subject}"
                )
        else:
            # If no count specified, assert at least one email matches
            if len(emails) == 0:
                raise AssertionError(
                    f"No emails found matching criteria. "
                    f"Filters: to={to}, subject={subject}"
                )

    @property
    def count(self) -> int:
        """Get total number of sent emails"""
        return len(self.sent_emails)

    @property
    def success_count(self) -> int:
        """Get number of successfully sent emails"""
        return sum(1 for e in self.sent_emails if e.success)

    @property
    def failure_count(self) -> int:
        """Get number of failed emails"""
        return sum(1 for e in self.sent_emails if not e.success)
