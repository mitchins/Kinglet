"""
Tests for MockD1Database implementation

Verifies that the mock D1 database behaves like the real Cloudflare D1 Workers API.
"""

import pytest

from kinglet.testing import (
    D1DatabaseError,
    D1ExecResult,
    D1PreparedStatementError,
    D1Result,
    D1ResultMeta,
    MockD1Database,
    MockD1PreparedStatement,
    d1_unwrap,
    d1_unwrap_results,
)


class TestMockD1DatabaseBasicOperations:
    """Test basic database operations"""

    @pytest.fixture
    def db(self):
        """Create a fresh mock database for each test"""
        database = MockD1Database()
        yield database
        database.close()

    @pytest.mark.asyncio
    async def test_exec_creates_table(self, db):
        """Test exec() can create tables"""
        result = await db.exec(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)"
        )

        assert isinstance(result, D1ExecResult)
        assert result.count == 1
        assert result.duration >= 0

    @pytest.mark.asyncio
    async def test_exec_multiple_statements(self, db):
        """Test exec() handles multiple statements"""
        result = await db.exec("""
            CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE posts (id INTEGER PRIMARY KEY, user_id INTEGER, title TEXT)
        """)

        assert result.count == 2

    @pytest.mark.asyncio
    async def test_prepare_returns_statement(self, db):
        """Test prepare() returns a MockD1PreparedStatement"""
        stmt = db.prepare("SELECT * FROM users")

        assert isinstance(stmt, MockD1PreparedStatement)

    @pytest.mark.asyncio
    async def test_insert_and_select(self, db):
        """Test basic INSERT and SELECT operations"""
        await db.exec("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")

        # Insert
        insert_stmt = db.prepare("INSERT INTO users (name) VALUES (?)").bind("Alice")
        insert_result = await insert_stmt.run()

        assert isinstance(insert_result, D1Result)
        assert insert_result.success is True
        assert insert_result.meta.last_row_id == 1

        # Select
        select_stmt = db.prepare("SELECT * FROM users")
        select_result = await select_stmt.all()

        assert len(select_result.results) == 1
        assert select_result.results[0]["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_update_operation(self, db):
        """Test UPDATE operation"""
        await db.exec("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        await db.prepare("INSERT INTO users (name) VALUES (?)").bind("Alice").run()

        # Update
        update_stmt = db.prepare("UPDATE users SET name = ? WHERE id = ?").bind(
            "Bob", 1
        )
        update_result = await update_stmt.run()

        assert update_result.success is True

        # Verify
        result = await db.prepare("SELECT name FROM users WHERE id = 1").first()
        assert result["name"] == "Bob"

    @pytest.mark.asyncio
    async def test_delete_operation(self, db):
        """Test DELETE operation"""
        await db.exec("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        await db.prepare("INSERT INTO users (name) VALUES (?)").bind("Alice").run()

        # Delete
        delete_stmt = db.prepare("DELETE FROM users WHERE id = ?").bind(1)
        await delete_stmt.run()

        # Verify
        result = await db.prepare("SELECT * FROM users").all()
        assert len(result.results) == 0


class TestMockD1PreparedStatement:
    """Test prepared statement methods"""

    @pytest.fixture
    async def db_with_data(self):
        """Create database with test data"""
        db = MockD1Database()
        await db.exec("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name TEXT,
                email TEXT,
                active INTEGER DEFAULT 1
            )
        """)
        await (
            db.prepare("INSERT INTO users (name, email) VALUES (?, ?)")
            .bind("Alice", "alice@example.com")
            .run()
        )
        await (
            db.prepare("INSERT INTO users (name, email) VALUES (?, ?)")
            .bind("Bob", "bob@example.com")
            .run()
        )
        await (
            db.prepare("INSERT INTO users (name, email) VALUES (?, ?)")
            .bind("Charlie", "charlie@example.com")
            .run()
        )
        yield db
        db.close()

    @pytest.mark.asyncio
    async def test_bind_returns_self(self, db_with_data):
        """Test bind() returns self for chaining"""
        stmt = db_with_data.prepare("SELECT * FROM users WHERE id = ?")
        result = stmt.bind(1)

        assert result is stmt

    @pytest.mark.asyncio
    async def test_first_returns_dict(self, db_with_data):
        """Test first() returns first row as dict"""
        result = await db_with_data.prepare("SELECT * FROM users ORDER BY id").first()

        assert isinstance(result, dict)
        assert result["id"] == 1
        assert result["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_first_returns_none_for_empty(self, db_with_data):
        """Test first() returns None when no rows match"""
        result = (
            await db_with_data.prepare("SELECT * FROM users WHERE id = ?")
            .bind(999)
            .first()
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_first_with_column_name(self, db_with_data):
        """Test first() with column name returns that column value"""
        result = (
            await db_with_data.prepare("SELECT * FROM users WHERE id = ?")
            .bind(1)
            .first("name")
        )

        assert result == "Alice"

    @pytest.mark.asyncio
    async def test_first_with_invalid_column_raises(self, db_with_data):
        """Test first() with invalid column raises error"""
        with pytest.raises(D1PreparedStatementError, match="does not exist"):
            await (
                db_with_data.prepare("SELECT * FROM users WHERE id = ?")
                .bind(1)
                .first("nonexistent")
            )

    @pytest.mark.asyncio
    async def test_all_returns_d1_result(self, db_with_data):
        """Test all() returns D1Result with metadata"""
        result = await db_with_data.prepare("SELECT * FROM users").all()

        assert isinstance(result, D1Result)
        assert len(result.results) == 3
        assert result.success is True
        assert result.meta.rows_read == 3

    @pytest.mark.asyncio
    async def test_run_equivalent_to_all(self, db_with_data):
        """Test run() is functionally equivalent to all()"""
        all_result = await db_with_data.prepare("SELECT * FROM users").all()
        run_result = await db_with_data.prepare("SELECT * FROM users").run()

        assert len(all_result.results) == len(run_result.results)

    @pytest.mark.asyncio
    async def test_raw_returns_arrays(self, db_with_data):
        """Test raw() returns array of arrays"""
        result = await db_with_data.prepare(
            "SELECT id, name FROM users ORDER BY id"
        ).raw()

        assert isinstance(result, list)
        assert isinstance(result[0], list)
        assert result[0] == [1, "Alice"]
        assert result[1] == [2, "Bob"]

    @pytest.mark.asyncio
    async def test_raw_with_column_names(self, db_with_data):
        """Test raw() with columnNames=True includes headers"""
        result = await db_with_data.prepare(
            "SELECT id, name FROM users ORDER BY id"
        ).raw({"columnNames": True})

        assert result[0] == ["id", "name"]  # Column names as first row
        assert result[1] == [1, "Alice"]

    @pytest.mark.asyncio
    async def test_raw_empty_result(self, db_with_data):
        """Test raw() returns empty list for no results"""
        result = (
            await db_with_data.prepare("SELECT * FROM users WHERE id = ?")
            .bind(999)
            .raw()
        )

        assert result == []


class TestMockD1DatabaseBatch:
    """Test batch operations"""

    @pytest.fixture
    async def db(self):
        """Create database with schema"""
        database = MockD1Database()
        await database.exec("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        yield database
        database.close()

    @pytest.mark.asyncio
    async def test_batch_executes_all_statements(self, db):
        """Test batch() executes all statements"""
        statements = [
            db.prepare("INSERT INTO users (name) VALUES (?)").bind("Alice"),
            db.prepare("INSERT INTO users (name) VALUES (?)").bind("Bob"),
            db.prepare("INSERT INTO users (name) VALUES (?)").bind("Charlie"),
        ]

        results = await db.batch(statements)

        assert len(results) == 3
        assert all(r.success for r in results)

        # Verify all inserts worked
        all_users = await db.prepare("SELECT * FROM users").all()
        assert len(all_users.results) == 3

    @pytest.mark.asyncio
    async def test_batch_returns_ordered_results(self, db):
        """Test batch() returns results in order"""
        statements = [
            db.prepare("INSERT INTO users (name) VALUES (?)").bind("First"),
            db.prepare("INSERT INTO users (name) VALUES (?)").bind("Second"),
        ]

        results = await db.batch(statements)

        assert results[0].meta.last_row_id == 1
        assert results[1].meta.last_row_id == 2


class TestD1TypeConversion:
    """Test D1-compatible type conversion"""

    @pytest.fixture
    async def db(self):
        """Create database with various column types"""
        database = MockD1Database()
        await database.exec("""
            CREATE TABLE data (
                id INTEGER PRIMARY KEY,
                flag INTEGER,
                value REAL,
                name TEXT,
                blob_data BLOB
            )
        """)
        yield database
        database.close()

    @pytest.mark.asyncio
    async def test_boolean_to_integer(self, db):
        """Test boolean values are converted to 0/1"""
        await db.prepare("INSERT INTO data (flag) VALUES (?)").bind(True).run()
        await db.prepare("INSERT INTO data (flag) VALUES (?)").bind(False).run()

        result = await db.prepare("SELECT flag FROM data ORDER BY id").all()

        assert result.results[0]["flag"] == 1
        assert result.results[1]["flag"] == 0

    @pytest.mark.asyncio
    async def test_none_to_null(self, db):
        """Test None values are stored as NULL"""
        await db.prepare("INSERT INTO data (name) VALUES (?)").bind(None).run()

        result = await db.prepare("SELECT name FROM data").first()

        assert result["name"] is None


class TestD1ResultObjects:
    """Test D1 result object behavior"""

    def test_d1_result_to_py(self):
        """Test D1Result.to_py() returns proper dict"""
        meta = D1ResultMeta(duration=0.5, last_row_id=1, changes=1, rows_read=5)
        result = D1Result(
            results=[{"id": 1, "name": "Test"}],
            success=True,
            meta=meta,
        )

        py_dict = result.to_py()

        assert py_dict["success"] is True
        assert py_dict["results"] == [{"id": 1, "name": "Test"}]
        assert py_dict["meta"]["duration"] == 0.5
        assert py_dict["meta"]["last_row_id"] == 1

    def test_d1_exec_result_to_py(self):
        """Test D1ExecResult.to_py() returns proper dict"""
        result = D1ExecResult(count=3, duration=0.1)

        py_dict = result.to_py()

        assert py_dict["count"] == 3
        assert py_dict["duration"] == 0.1


class TestD1UnwrapHelpers:
    """Test d1_unwrap helper functions"""

    def test_d1_unwrap_with_d1_result(self):
        """Test d1_unwrap with D1Result"""
        result = D1Result(results=[{"id": 1}], success=True)

        unwrapped = d1_unwrap(result)

        assert unwrapped["success"] is True
        assert unwrapped["results"] == [{"id": 1}]

    def test_d1_unwrap_with_dict(self):
        """Test d1_unwrap with plain dict"""
        data = {"id": 1, "name": "Test"}

        unwrapped = d1_unwrap(data)

        assert unwrapped == data

    def test_d1_unwrap_results_with_d1_result(self):
        """Test d1_unwrap_results extracts results list"""
        result = D1Result(results=[{"id": 1}, {"id": 2}])

        unwrapped = d1_unwrap_results(result)

        assert len(unwrapped) == 2
        assert unwrapped[0]["id"] == 1

    def test_d1_unwrap_results_with_list(self):
        """Test d1_unwrap_results with plain list"""
        data = [{"id": 1}, {"id": 2}]

        unwrapped = d1_unwrap_results(data)

        assert unwrapped == data


class TestD1DatabaseWithKingletORM:
    """Test MockD1Database works with Kinglet ORM patterns"""

    @pytest.fixture
    async def db(self):
        """Create database with ORM-style schema"""
        database = MockD1Database()
        await database.exec("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                username TEXT NOT NULL,
                name TEXT,
                created_at INTEGER
            )
        """)
        yield database
        database.close()

    @pytest.mark.asyncio
    async def test_orm_style_insert_returning_id(self, db):
        """Test INSERT returns auto-generated ID (ORM pattern)"""
        result = (
            await db.prepare(
                "INSERT INTO users (email, username, name) VALUES (?, ?, ?)"
            )
            .bind("test@example.com", "testuser", "Test User")
            .run()
        )

        assert result.meta.last_row_id is not None
        assert result.meta.last_row_id > 0

    @pytest.mark.asyncio
    async def test_orm_style_filter_query(self, db):
        """Test ORM-style filter queries"""
        # Insert test data
        await (
            db.prepare("INSERT INTO users (email, username, name) VALUES (?, ?, ?)")
            .bind("alice@example.com", "alice", "Alice")
            .run()
        )
        await (
            db.prepare("INSERT INTO users (email, username, name) VALUES (?, ?, ?)")
            .bind("bob@example.com", "bob", "Bob")
            .run()
        )

        # ORM-style filter
        result = (
            await db.prepare("SELECT id, email, name FROM users WHERE username = ?")
            .bind("alice")
            .first()
        )

        assert result is not None
        assert result["email"] == "alice@example.com"
        assert result["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_orm_style_count_query(self, db):
        """Test ORM-style count queries"""
        await (
            db.prepare("INSERT INTO users (email, username, name) VALUES (?, ?, ?)")
            .bind("user1@example.com", "user1", "User 1")
            .run()
        )
        await (
            db.prepare("INSERT INTO users (email, username, name) VALUES (?, ?, ?)")
            .bind("user2@example.com", "user2", "User 2")
            .run()
        )

        result = await db.prepare("SELECT COUNT(*) as count FROM users").first()

        assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_orm_style_exists_query(self, db):
        """Test ORM-style EXISTS pattern (cost-optimized)"""
        await (
            db.prepare("INSERT INTO users (email, username, name) VALUES (?, ?, ?)")
            .bind("test@example.com", "test", "Test")
            .run()
        )

        # Cost-optimized EXISTS pattern
        exists_result = (
            await db.prepare("SELECT 1 FROM users WHERE email = ? LIMIT 1")
            .bind("test@example.com")
            .first()
        )

        assert exists_result is not None

        not_exists_result = (
            await db.prepare("SELECT 1 FROM users WHERE email = ? LIMIT 1")
            .bind("nonexistent@example.com")
            .first()
        )

        assert not_exists_result is None


class TestD1ErrorHandling:
    """Test error handling"""

    @pytest.fixture
    def db(self):
        database = MockD1Database()
        yield database
        database.close()

    @pytest.mark.asyncio
    async def test_sql_syntax_error(self, db):
        """Test SQL syntax errors are caught"""
        with pytest.raises(D1DatabaseError):
            await db.prepare("INVALID SQL QUERY").run()

    @pytest.mark.asyncio
    async def test_exec_error_handling(self, db):
        """Test exec() error handling"""
        with pytest.raises(D1DatabaseError):
            await db.exec("CREATE TABLE ())")  # Invalid syntax

    @pytest.mark.asyncio
    async def test_exec_rollback_on_partial_failure(self):
        """Test exec() rolls back all statements on failure (atomic behavior)"""
        db = MockD1Database()

        # First statement valid, second invalid - should rollback both
        with pytest.raises(D1DatabaseError):
            await db.exec("""
                CREATE TABLE should_not_exist (id INTEGER PRIMARY KEY);
                CREATE TABLE ())"  -- Invalid syntax
            """)

        # Verify the first table was NOT created (rolled back)
        cursor = db.conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='should_not_exist'"
        )
        result = cursor.fetchone()
        assert result is None, "Table should have been rolled back"


class TestD1DatabaseClose:
    """Test database cleanup"""

    @pytest.mark.asyncio
    async def test_close_database(self):
        """Test close() properly closes connection"""
        db = MockD1Database()
        await db.exec("CREATE TABLE test (id INTEGER)")

        db.close()

        # Should not raise, close is idempotent
        db.close()


class TestD1ReturningClause:
    """Test INSERT/UPDATE/DELETE with RETURNING clause"""

    @pytest.fixture
    async def db(self):
        """Create database with test table"""
        database = MockD1Database()
        await database.exec("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT,
                age INTEGER
            )
        """)
        yield database
        database.close()

    @pytest.mark.asyncio
    async def test_insert_with_returning(self, db):
        """Test INSERT with RETURNING clause returns inserted row"""
        result = await db.prepare("""
            INSERT INTO users (email, name, age) 
            VALUES (?, ?, ?)
            RETURNING id, email, name, age
        """).bind("alice@example.com", "Alice", 30).first()

        assert result is not None
        assert result["email"] == "alice@example.com"
        assert result["name"] == "Alice"
        assert result["age"] == 30
        assert result["id"] == 1

    @pytest.mark.asyncio
    async def test_insert_or_replace_with_returning(self, db):
        """Test INSERT OR REPLACE with RETURNING (upsert pattern)"""
        # First insert
        result1 = await db.prepare("""
            INSERT OR REPLACE INTO users (email, name, age)
            VALUES (?, ?, ?)
            RETURNING id, email, name, age
        """).bind("bob@example.com", "Bob", 25).first()

        assert result1 is not None
        assert result1["name"] == "Bob"
        assert result1["age"] == 25
        first_id = result1["id"]

        # Upsert (update based on unique email)
        result2 = await db.prepare("""
            INSERT OR REPLACE INTO users (email, name, age)
            VALUES (?, ?, ?)
            RETURNING id, email, name, age
        """).bind("bob@example.com", "Robert", 26).first()

        assert result2 is not None
        assert result2["name"] == "Robert"
        assert result2["age"] == 26
        # ID might change with INSERT OR REPLACE
        assert result2["id"] is not None

    @pytest.mark.asyncio
    async def test_update_with_returning(self, db):
        """Test UPDATE with RETURNING clause"""
        # Insert initial data
        await db.prepare(
            "INSERT INTO users (email, name, age) VALUES (?, ?, ?)"
        ).bind("charlie@example.com", "Charlie", 35).run()

        # Update with RETURNING
        result = await db.prepare("""
            UPDATE users 
            SET name = ?, age = ?
            WHERE email = ?
            RETURNING id, email, name, age
        """).bind("Charles", 36, "charlie@example.com").first()

        assert result is not None
        assert result["name"] == "Charles"
        assert result["age"] == 36
        assert result["email"] == "charlie@example.com"

    @pytest.mark.asyncio
    async def test_delete_with_returning(self, db):
        """Test DELETE with RETURNING clause"""
        # Insert data
        await db.prepare(
            "INSERT INTO users (email, name, age) VALUES (?, ?, ?)"
        ).bind("delete@example.com", "ToDelete", 40).run()

        # Delete with RETURNING
        result = await db.prepare("""
            DELETE FROM users
            WHERE email = ?
            RETURNING id, email, name, age
        """).bind("delete@example.com").first()

        assert result is not None
        assert result["email"] == "delete@example.com"
        assert result["name"] == "ToDelete"

        # Verify deletion
        check = await db.prepare(
            "SELECT * FROM users WHERE email = ?"
        ).bind("delete@example.com").first()
        assert check is None

    @pytest.mark.asyncio
    async def test_insert_returning_all(self, db):
        """Test INSERT with RETURNING using all() method"""
        result = await db.prepare("""
            INSERT INTO users (email, name, age) 
            VALUES (?, ?, ?)
            RETURNING id, email, name
        """).bind("test@example.com", "Test", 20).all()

        assert isinstance(result.results, list)
        assert len(result.results) == 1
        assert result.results[0]["email"] == "test@example.com"
        assert result.success is True

    @pytest.mark.asyncio
    async def test_multiple_inserts_with_returning_in_batch(self, db):
        """Test batch operations with RETURNING clauses"""
        statements = [
            db.prepare("""
                INSERT INTO users (email, name, age)
                VALUES (?, ?, ?)
                RETURNING id, email, name
            """).bind("user1@example.com", "User1", 21),
            db.prepare("""
                INSERT INTO users (email, name, age)
                VALUES (?, ?, ?)
                RETURNING id, email, name
            """).bind("user2@example.com", "User2", 22),
        ]

        results = await db.batch(statements)

        assert len(results) == 2
        assert all(r.success for r in results)
        assert len(results[0].results) == 1
        assert results[0].results[0]["email"] == "user1@example.com"
        assert len(results[1].results) == 1
        assert results[1].results[0]["email"] == "user2@example.com"

    @pytest.mark.asyncio
    async def test_insert_returning_metadata_accuracy(self, db):
        """Test that metadata (changes, rows_written) is accurate for INSERT with RETURNING"""
        result = await db.prepare("""
            INSERT INTO users (email, name, age)
            VALUES (?, ?, ?)
            RETURNING id, email, name
        """).bind("metadata@example.com", "Meta", 25).all()

        # Verify metadata is accurate
        assert result.meta.changes == 1, "changes should be 1 for single INSERT"
        assert result.meta.rows_written == 1, "rows_written should be 1 for single INSERT"
        assert result.meta.last_row_id is not None, "last_row_id should be set"
        assert result.meta.last_row_id > 0, "last_row_id should be positive"

    @pytest.mark.asyncio
    async def test_update_returning_metadata_accuracy(self, db):
        """Test that metadata (changes, rows_written) is accurate for UPDATE with RETURNING"""
        # Insert initial data
        await db.prepare(
            "INSERT INTO users (email, name, age) VALUES (?, ?, ?)"
        ).bind("update@example.com", "Original", 30).run()

        # Update with RETURNING
        result = await db.prepare("""
            UPDATE users
            SET name = ?, age = ?
            WHERE email = ?
            RETURNING id, email, name, age
        """).bind("Updated", 31, "update@example.com").all()

        # Verify metadata is accurate
        assert result.meta.changes == 1, "changes should be 1 for single UPDATE"
        assert result.meta.rows_written == 1, "rows_written should be 1 for single UPDATE"
        assert len(result.results) == 1, "should return exactly one row"

    @pytest.mark.asyncio
    async def test_delete_returning_metadata_accuracy(self, db):
        """Test that metadata (changes, rows_written) is accurate for DELETE with RETURNING"""
        # Insert initial data
        await db.prepare(
            "INSERT INTO users (email, name, age) VALUES (?, ?, ?)"
        ).bind("deleteme@example.com", "ToDelete", 40).run()

        # Delete with RETURNING
        result = await db.prepare("""
            DELETE FROM users
            WHERE email = ?
            RETURNING id, email, name
        """).bind("deleteme@example.com").all()

        # Verify metadata is accurate
        assert result.meta.changes == 1, "changes should be 1 for single DELETE"
        assert result.meta.rows_written == 1, "rows_written should be 1 for single DELETE"
        assert len(result.results) == 1, "should return exactly one row with deleted data"

    @pytest.mark.asyncio
    async def test_update_multiple_rows_returning_metadata(self, db):
        """Test metadata accuracy for UPDATE affecting multiple rows with RETURNING"""
        # Insert multiple users
        await db.prepare(
            "INSERT INTO users (email, name, age) VALUES (?, ?, ?)"
        ).bind("user1@test.com", "User1", 25).run()
        await db.prepare(
            "INSERT INTO users (email, name, age) VALUES (?, ?, ?)"
        ).bind("user2@test.com", "User2", 25).run()
        await db.prepare(
            "INSERT INTO users (email, name, age) VALUES (?, ?, ?)"
        ).bind("user3@test.com", "User3", 30).run()

        # Update multiple rows with RETURNING
        result = await db.prepare("""
            UPDATE users
            SET age = ?
            WHERE age = ?
            RETURNING id, email, name, age
        """).bind(26, 25).all()

        # Verify metadata reflects multiple updates
        assert result.meta.changes == 2, "changes should be 2 for two UPDATEs"
        assert result.meta.rows_written == 2, "rows_written should be 2 for two UPDATEs"
        assert len(result.results) == 2, "should return exactly two rows"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
