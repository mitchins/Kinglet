"""
Tests for enhanced MockD1Database features

Validates that MockD1Database supports comprehensive SQL features
through SQLite passthrough, including:
- Complex WHERE clauses
- Aggregate functions and GROUP BY
- JOIN operations
- Subqueries
- Advanced operators
- Transaction support
"""

import pytest

from kinglet.testing import D1DatabaseError, MockD1Database


class TestComplexWhereClause:
    """Test Priority 1.1: Enhanced WHERE clause parsing"""

    @pytest.fixture
    async def db(self):
        """Create database with test data"""
        database = MockD1Database()
        await database.exec("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                age INTEGER,
                status TEXT,
                created_at INTEGER
            )
        """)
        # Insert test data
        await database.prepare(
            "INSERT INTO users (email, name, age, status, created_at) VALUES (?, ?, ?, ?, ?)"
        ).bind("alice@example.com", "Alice", 30, "active", 1000).run()
        await database.prepare(
            "INSERT INTO users (email, name, age, status, created_at) VALUES (?, ?, ?, ?, ?)"
        ).bind("bob@example.com", "Bob", 25, "active", 2000).run()
        await database.prepare(
            "INSERT INTO users (email, name, age, status, created_at) VALUES (?, ?, ?, ?, ?)"
        ).bind("charlie@example.com", "Charlie", 35, "inactive", 3000).run()
        await database.prepare(
            "INSERT INTO users (email, name, age, status, created_at) VALUES (?, ?, ?, ?, ?)"
        ).bind("david@example.com", "David", 28, "active", 4000).run()
        yield database
        database.close()

    @pytest.mark.asyncio
    async def test_multiple_and_conditions(self, db):
        """Test multiple conditions with AND"""
        result = await db.prepare("""
            SELECT * FROM users 
            WHERE status = ? AND age > ? AND age < ?
        """).bind("active", 20, 30).all()

        assert len(result.results) == 2
        names = {r["name"] for r in result.results}
        assert names == {"Bob", "David"}

    @pytest.mark.asyncio
    async def test_or_conditions(self, db):
        """Test OR conditions"""
        result = await db.prepare("""
            SELECT * FROM users 
            WHERE age < ? OR status = ?
        """).bind(27, "inactive").all()

        assert len(result.results) == 2
        names = {r["name"] for r in result.results}
        assert names == {"Bob", "Charlie"}

    @pytest.mark.asyncio
    async def test_in_operator(self, db):
        """Test IN operator"""
        result = await db.prepare("""
            SELECT * FROM users 
            WHERE id IN (?, ?, ?)
        """).bind(1, 2, 4).all()

        assert len(result.results) == 3
        names = {r["name"] for r in result.results}
        assert names == {"Alice", "Bob", "David"}

    @pytest.mark.asyncio
    async def test_is_null(self, db):
        """Test IS NULL condition"""
        # Add a user with NULL age
        await db.prepare(
            "INSERT INTO users (email, name, status) VALUES (?, ?, ?)"
        ).bind("eve@example.com", "Eve", "active").run()

        result = await db.prepare("""
            SELECT * FROM users WHERE age IS NULL
        """).all()

        assert len(result.results) == 1
        assert result.results[0]["name"] == "Eve"

    @pytest.mark.asyncio
    async def test_is_not_null(self, db):
        """Test IS NOT NULL condition"""
        result = await db.prepare("""
            SELECT * FROM users WHERE age IS NOT NULL
        """).all()

        assert len(result.results) == 4

    @pytest.mark.asyncio
    async def test_like_pattern_matching(self, db):
        """Test LIKE pattern matching"""
        result = await db.prepare("""
            SELECT * FROM users WHERE email LIKE ?
        """).bind("%example.com").all()

        assert len(result.results) == 4

        # Test more specific pattern
        result2 = await db.prepare("""
            SELECT * FROM users WHERE name LIKE ?
        """).bind("A%").all()

        assert len(result2.results) == 1
        assert result2.results[0]["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_not_like(self, db):
        """Test NOT LIKE pattern matching"""
        result = await db.prepare("""
            SELECT * FROM users WHERE name NOT LIKE ?
        """).bind("A%").all()

        assert len(result.results) == 3
        names = {r["name"] for r in result.results}
        assert "Alice" not in names

    @pytest.mark.asyncio
    async def test_comparison_operators(self, db):
        """Test comparison operators (>, <, >=, <=, !=)"""
        # Greater than
        result = await db.prepare(
            "SELECT * FROM users WHERE age > ?"
        ).bind(30).all()
        assert len(result.results) == 1
        assert result.results[0]["name"] == "Charlie"

        # Less than or equal
        result2 = await db.prepare(
            "SELECT * FROM users WHERE age <= ?"
        ).bind(28).all()
        assert len(result2.results) == 2

        # Not equal
        result3 = await db.prepare(
            "SELECT * FROM users WHERE status != ?"
        ).bind("active").all()
        assert len(result3.results) == 1
        assert result3.results[0]["name"] == "Charlie"

    @pytest.mark.asyncio
    async def test_between_operator(self, db):
        """Test BETWEEN operator"""
        result = await db.prepare("""
            SELECT * FROM users WHERE age BETWEEN ? AND ?
        """).bind(25, 30).all()

        assert len(result.results) == 3
        names = {r["name"] for r in result.results}
        assert names == {"Alice", "Bob", "David"}

    @pytest.mark.asyncio
    async def test_complex_nested_conditions(self, db):
        """Test complex nested AND/OR conditions"""
        result = await db.prepare("""
            SELECT * FROM users 
            WHERE (status = ? AND age > ?) OR (status = ? AND age < ?)
        """).bind("active", 27, "inactive", 40).all()

        assert len(result.results) == 3
        names = {r["name"] for r in result.results}
        assert names == {"Alice", "David", "Charlie"}


class TestAggregateFunctions:
    """Test Priority 1.2: Aggregate functions and GROUP BY"""

    @pytest.fixture
    async def db(self):
        """Create database with test data"""
        database = MockD1Database()
        await database.exec("""
            CREATE TABLE team_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                points INTEGER DEFAULT 0,
                reputation_score INTEGER DEFAULT 0
            )
        """)
        # Insert test data for multiple teams
        members = [
            (1, "Alice", 150, 95),
            (1, "Bob", 120, 85),
            (1, "Charlie", 80, 70),
            (2, "David", 200, 100),
            (2, "Eve", 90, 80),
            (3, "Frank", 50, 60),
        ]
        for team_id, name, points, reputation in members:
            await database.prepare(
                "INSERT INTO team_members (team_id, name, points, reputation_score) VALUES (?, ?, ?, ?)"
            ).bind(team_id, name, points, reputation).run()
        yield database
        database.close()

    @pytest.mark.asyncio
    async def test_count_aggregate(self, db):
        """Test COUNT(*) aggregate function"""
        result = await db.prepare(
            "SELECT COUNT(*) as count FROM team_members WHERE team_id = ?"
        ).bind(1).first()

        assert result["count"] == 3

    @pytest.mark.asyncio
    async def test_sum_aggregate(self, db):
        """Test SUM aggregate function"""
        result = await db.prepare(
            "SELECT SUM(points) as total FROM team_members WHERE team_id = ?"
        ).bind(1).first()

        assert result["total"] == 350

    @pytest.mark.asyncio
    async def test_avg_aggregate(self, db):
        """Test AVG aggregate function"""
        result = await db.prepare(
            "SELECT AVG(points) as avg_points FROM team_members WHERE team_id = ?"
        ).bind(1).first()

        assert result["avg_points"] == pytest.approx(116.67, rel=0.01)

    @pytest.mark.asyncio
    async def test_max_min_aggregates(self, db):
        """Test MAX and MIN aggregate functions"""
        result = await db.prepare("""
            SELECT MAX(points) as max_points, MIN(points) as min_points 
            FROM team_members WHERE team_id = ?
        """).bind(1).first()

        assert result["max_points"] == 150
        assert result["min_points"] == 80

    @pytest.mark.asyncio
    async def test_group_by_with_count(self, db):
        """Test GROUP BY with COUNT aggregate"""
        result = await db.prepare("""
            SELECT team_id, COUNT(*) as member_count 
            FROM team_members 
            GROUP BY team_id
            ORDER BY team_id
        """).all()

        assert len(result.results) == 3
        assert result.results[0]["team_id"] == 1
        assert result.results[0]["member_count"] == 3
        assert result.results[1]["member_count"] == 2
        assert result.results[2]["member_count"] == 1

    @pytest.mark.asyncio
    async def test_group_by_multiple_aggregates(self, db):
        """Test GROUP BY with multiple aggregates"""
        result = await db.prepare("""
            SELECT 
                team_id,
                COUNT(*) as total,
                AVG(points) as avg_points,
                MAX(reputation_score) as top_score
            FROM team_members
            GROUP BY team_id
            ORDER BY team_id
        """).all()

        assert len(result.results) == 3
        # Team 1
        assert result.results[0]["total"] == 3
        assert result.results[0]["avg_points"] == pytest.approx(116.67, rel=0.01)
        assert result.results[0]["top_score"] == 95

    @pytest.mark.asyncio
    async def test_having_clause(self, db):
        """Test HAVING clause filtering on aggregate results"""
        result = await db.prepare("""
            SELECT team_id, COUNT(*) as member_count
            FROM team_members
            GROUP BY team_id
            HAVING COUNT(*) > ?
        """).bind(1).all()

        assert len(result.results) == 2
        team_ids = {r["team_id"] for r in result.results}
        assert team_ids == {1, 2}


class TestJoinOperations:
    """Test Priority 1.3: JOIN operations"""

    @pytest.fixture
    async def db(self):
        """Create database with related tables"""
        database = MockD1Database()
        await database.exec("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL
            );
            
            CREATE TABLE teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
            );
            
            CREATE TABLE team_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                team_id INTEGER NOT NULL,
                points INTEGER DEFAULT 0
            );
        """)
        
        # Insert test data
        await database.prepare("INSERT INTO users (email, name) VALUES (?, ?)").bind(
            "alice@example.com", "Alice"
        ).run()
        await database.prepare("INSERT INTO users (email, name) VALUES (?, ?)").bind(
            "bob@example.com", "Bob"
        ).run()
        await database.prepare("INSERT INTO users (email, name) VALUES (?, ?)").bind(
            "charlie@example.com", "Charlie"
        ).run()
        
        await database.prepare("INSERT INTO teams (name) VALUES (?)").bind("Team A").run()
        await database.prepare("INSERT INTO teams (name) VALUES (?)").bind("Team B").run()
        
        # Alice and Bob in Team A, Charlie in Team B
        await database.prepare(
            "INSERT INTO team_members (user_id, team_id, points) VALUES (?, ?, ?)"
        ).bind(1, 1, 100).run()
        await database.prepare(
            "INSERT INTO team_members (user_id, team_id, points) VALUES (?, ?, ?)"
        ).bind(2, 1, 80).run()
        await database.prepare(
            "INSERT INTO team_members (user_id, team_id, points) VALUES (?, ?, ?)"
        ).bind(3, 2, 120).run()
        
        yield database
        database.close()

    @pytest.mark.asyncio
    async def test_inner_join(self, db):
        """Test INNER JOIN"""
        result = await db.prepare("""
            SELECT u.email, u.name, tm.points
            FROM users u
            INNER JOIN team_members tm ON u.id = tm.user_id
            WHERE tm.team_id = ?
        """).bind(1).all()

        assert len(result.results) == 2
        names = {r["name"] for r in result.results}
        assert names == {"Alice", "Bob"}

    @pytest.mark.asyncio
    async def test_left_join(self, db):
        """Test LEFT JOIN"""
        # Add a user without team membership
        await db.prepare("INSERT INTO users (email, name) VALUES (?, ?)").bind(
            "david@example.com", "David"
        ).run()

        result = await db.prepare("""
            SELECT u.name, tm.points
            FROM users u
            LEFT JOIN team_members tm ON u.id = tm.user_id
            ORDER BY u.id
        """).all()

        assert len(result.results) == 4
        # David should have NULL points
        david_row = [r for r in result.results if r["name"] == "David"][0]
        assert david_row["points"] is None

    @pytest.mark.asyncio
    async def test_multiple_joins(self, db):
        """Test multiple JOIN operations"""
        result = await db.prepare("""
            SELECT u.name, t.name as team_name, tm.points
            FROM team_members tm
            INNER JOIN users u ON tm.user_id = u.id
            INNER JOIN teams t ON tm.team_id = t.id
            WHERE t.name = ?
        """).bind("Team A").all()

        assert len(result.results) == 2
        for row in result.results:
            assert row["team_name"] == "Team A"
            assert row["name"] in ["Alice", "Bob"]

    @pytest.mark.asyncio
    async def test_join_with_aggregates(self, db):
        """Test JOIN with GROUP BY and aggregates"""
        result = await db.prepare("""
            SELECT t.name, COUNT(tm.id) as member_count, SUM(tm.points) as total_points
            FROM teams t
            LEFT JOIN team_members tm ON t.id = tm.team_id
            GROUP BY t.id
            ORDER BY t.name
        """).all()

        assert len(result.results) == 2
        team_a = [r for r in result.results if r["name"] == "Team A"][0]
        assert team_a["member_count"] == 2
        assert team_a["total_points"] == 180


class TestSubqueries:
    """Test Priority 2.1: Subquery support"""

    @pytest.fixture
    async def db(self):
        """Create database with test data"""
        database = MockD1Database()
        await database.exec("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL
            );
            
            CREATE TABLE team_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                team_id INTEGER NOT NULL,
                points INTEGER DEFAULT 0
            );
        """)
        
        # Insert test data
        for i in range(1, 6):
            await database.prepare("INSERT INTO users (email, name) VALUES (?, ?)").bind(
                f"user{i}@example.com", f"User{i}"
            ).run()
        
        # Users 1, 2, 3 in team 1
        for user_id in [1, 2, 3]:
            await database.prepare(
                "INSERT INTO team_members (user_id, team_id, points) VALUES (?, ?, ?)"
            ).bind(user_id, 1, 100).run()
        
        yield database
        database.close()

    @pytest.mark.asyncio
    async def test_subquery_in_where(self, db):
        """Test subquery in WHERE clause with IN operator"""
        result = await db.prepare("""
            SELECT * FROM users 
            WHERE id IN (SELECT user_id FROM team_members WHERE team_id = ?)
        """).bind(1).all()

        assert len(result.results) == 3
        names = {r["name"] for r in result.results}
        assert names == {"User1", "User2", "User3"}

    @pytest.mark.asyncio
    async def test_subquery_in_from(self, db):
        """Test subquery in FROM clause"""
        result = await db.prepare("""
            SELECT team_stats.team_id, team_stats.member_count
            FROM (
                SELECT team_id, COUNT(*) as member_count 
                FROM team_members 
                GROUP BY team_id
            ) team_stats
            WHERE team_stats.member_count > ?
        """).bind(2).all()

        assert len(result.results) == 1
        assert result.results[0]["member_count"] == 3


class TestAdvancedOperators:
    """Test Priority 2.3: Advanced operators"""

    @pytest.fixture
    async def db(self):
        """Create database with test data"""
        database = MockD1Database()
        await database.exec("""
            CREATE TABLE team_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                points INTEGER DEFAULT 0,
                avatar TEXT
            )
        """)
        
        await database.prepare(
            "INSERT INTO team_members (name, points, avatar) VALUES (?, ?, ?)"
        ).bind("Alice", 150, "alice.png").run()
        await database.prepare(
            "INSERT INTO team_members (name, points) VALUES (?, ?)"
        ).bind("Bob", 75).run()
        await database.prepare(
            "INSERT INTO team_members (name, points, avatar) VALUES (?, ?, ?)"
        ).bind("Charlie", 30, "charlie.png").run()
        
        yield database
        database.close()

    @pytest.mark.asyncio
    async def test_case_expression(self, db):
        """Test CASE expressions"""
        result = await db.prepare("""
            SELECT 
                name,
                points,
                CASE 
                    WHEN points > 100 THEN 'gold'
                    WHEN points > 50 THEN 'silver'
                    ELSE 'bronze'
                END as tier
            FROM team_members
            ORDER BY points DESC
        """).all()

        assert len(result.results) == 3
        assert result.results[0]["tier"] == "gold"
        assert result.results[1]["tier"] == "silver"
        assert result.results[2]["tier"] == "bronze"

    @pytest.mark.asyncio
    async def test_coalesce_function(self, db):
        """Test COALESCE function"""
        result = await db.prepare("""
            SELECT 
                name,
                COALESCE(avatar, 'default.png') as avatar_url
            FROM team_members
            ORDER BY id
        """).all()

        assert len(result.results) == 3
        assert result.results[0]["avatar_url"] == "alice.png"
        assert result.results[1]["avatar_url"] == "default.png"  # Bob has NULL avatar
        assert result.results[2]["avatar_url"] == "charlie.png"


class TestTransactionSupport:
    """Test Priority 2.2: Transaction support"""

    @pytest.fixture
    def db(self):
        """Create database with schema"""
        database = MockD1Database()
        yield database
        database.close()

    @pytest.mark.asyncio
    async def test_transaction_commit(self, db):
        """Test BEGIN/COMMIT transaction"""
        await db.exec("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        
        # Execute transaction
        await db.exec("BEGIN TRANSACTION")
        await db.prepare("INSERT INTO users (name) VALUES (?)").bind("Alice").run()
        await db.prepare("INSERT INTO users (name) VALUES (?)").bind("Bob").run()
        await db.exec("COMMIT")
        
        # Verify data was committed
        result = await db.prepare("SELECT * FROM users").all()
        assert len(result.results) == 2

    @pytest.mark.asyncio
    async def test_transaction_rollback(self, db):
        """Test BEGIN/ROLLBACK transaction"""
        await db.exec("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        
        # Insert initial data
        await db.prepare("INSERT INTO users (name) VALUES (?)").bind("Alice").run()
        
        # Start transaction and insert more data
        await db.exec("BEGIN TRANSACTION")
        await db.prepare("INSERT INTO users (name) VALUES (?)").bind("Bob").run()
        await db.prepare("INSERT INTO users (name) VALUES (?)").bind("Charlie").run()
        
        # Rollback the transaction
        await db.exec("ROLLBACK")
        
        # Verify only Alice remains (Bob and Charlie were rolled back)
        result = await db.prepare("SELECT * FROM users").all()
        assert len(result.results) == 1
        assert result.results[0]["name"] == "Alice"


class TestDistinctAndLimitOffset:
    """Test DISTINCT, LIMIT, and OFFSET support"""

    @pytest.fixture
    async def db(self):
        """Create database with test data"""
        database = MockD1Database()
        await database.exec("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                team_id INTEGER NOT NULL
            )
        """)
        
        # Insert duplicate team_ids
        for i in range(10):
            team_id = (i % 3) + 1  # Teams 1, 2, 3
            await database.prepare(
                "INSERT INTO users (name, team_id) VALUES (?, ?)"
            ).bind(f"User{i}", team_id).run()
        
        yield database
        database.close()

    @pytest.mark.asyncio
    async def test_distinct(self, db):
        """Test DISTINCT keyword"""
        result = await db.prepare("""
            SELECT DISTINCT team_id FROM users ORDER BY team_id
        """).all()

        assert len(result.results) == 3
        team_ids = [r["team_id"] for r in result.results]
        assert team_ids == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_limit(self, db):
        """Test LIMIT clause"""
        result = await db.prepare("""
            SELECT * FROM users LIMIT ?
        """).bind(5).all()

        assert len(result.results) == 5

    @pytest.mark.asyncio
    async def test_offset_pagination(self, db):
        """Test OFFSET pagination"""
        result = await db.prepare("""
            SELECT * FROM users ORDER BY id LIMIT ? OFFSET ?
        """).bind(3, 5).all()

        assert len(result.results) == 3
        # Should get users 6, 7, 8 (ids starting from 1)
        ids = [r["id"] for r in result.results]
        assert ids == [6, 7, 8]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
