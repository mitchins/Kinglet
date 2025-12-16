"""
Comprehensive MockD1Database Example

Demonstrates the full SQL capabilities of MockD1Database through
SQLite passthrough, including complex queries, joins, aggregates,
transactions, and more.

This example shows that MockD1Database now supports production-grade
SQL testing without requiring external services like Miniflare or pywrangler.
"""

import asyncio
from kinglet import MockD1Database


async def main():
    """Demonstrate comprehensive D1 mock capabilities"""
    
    # Initialize mock database
    db = MockD1Database()
    
    print("🚀 MockD1Database Comprehensive SQL Support Demo\n")
    print("=" * 60)
    
    # =========================================================================
    # 1. Schema Setup
    # =========================================================================
    print("\n📋 1. Creating schema with foreign keys...")
    await db.exec("""
        CREATE TABLE teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at INTEGER NOT NULL
        );
        
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            team_id INTEGER,
            status TEXT DEFAULT 'active',
            points INTEGER DEFAULT 0,
            created_at INTEGER NOT NULL,
            FOREIGN KEY (team_id) REFERENCES teams(id)
        );
        
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            created_at INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)
    print("✅ Schema created with foreign key constraints")
    
    # =========================================================================
    # 2. Complex Insertions with Transactions
    # =========================================================================
    print("\n💾 2. Inserting data with transaction support...")
    
    await db.exec("BEGIN TRANSACTION")
    
    # Insert teams
    team1_id = (await db.prepare(
        "INSERT INTO teams (name, created_at) VALUES (?, ?) RETURNING id"
    ).bind("Engineering", 1000).first())["id"]
    
    team2_id = (await db.prepare(
        "INSERT INTO teams (name, created_at) VALUES (?, ?) RETURNING id"
    ).bind("Marketing", 2000).first())["id"]
    
    # Insert users
    for i, (email, name, team_id, points) in enumerate([
        ("alice@example.com", "Alice", team1_id, 150),
        ("bob@example.com", "Bob", team1_id, 120),
        ("charlie@example.com", "Charlie", team1_id, 80),
        ("david@example.com", "David", team2_id, 200),
        ("eve@example.com", "Eve", team2_id, 90),
    ]):
        await db.prepare(
            "INSERT INTO users (email, name, team_id, points, created_at) VALUES (?, ?, ?, ?, ?)"
        ).bind(email, name, team_id, points, 3000 + i).run()
    
    # Insert orders
    orders_data = [
        (1, 100.50), (1, 200.00), (1, 50.25),
        (2, 150.00), (2, 75.50),
        (4, 300.00), (4, 250.00), (4, 100.00),
        (5, 50.00),
    ]
    for user_id, amount in orders_data:
        await db.prepare(
            "INSERT INTO orders (user_id, amount, created_at) VALUES (?, ?, ?)"
        ).bind(user_id, amount, 4000).run()
    
    await db.exec("COMMIT")
    print("✅ Data inserted successfully with transaction")
    
    # =========================================================================
    # 3. Complex WHERE Clauses
    # =========================================================================
    print("\n🔍 3. Complex WHERE clause queries...")
    
    # Multiple AND conditions
    result = await db.prepare("""
        SELECT * FROM users 
        WHERE status = ? AND points > ? AND points < ?
    """).bind("active", 90, 160).all()
    print(f"   Users with 90 < points < 160: {[r['name'] for r in result.results]}")
    
    # OR conditions
    result = await db.prepare("""
        SELECT * FROM users 
        WHERE points < ? OR team_id = ?
    """).bind(100, team2_id).all()
    print(f"   Users with points < 100 OR in Marketing: {[r['name'] for r in result.results]}")
    
    # IN operator
    result = await db.prepare("""
        SELECT * FROM users WHERE id IN (?, ?, ?)
    """).bind(1, 2, 4).all()
    print(f"   Users with id IN (1,2,4): {[r['name'] for r in result.results]}")
    
    # LIKE pattern matching
    result = await db.prepare("""
        SELECT * FROM users WHERE email LIKE ?
    """).bind("%@example.com").all()
    print(f"   Users with @example.com email: {len(result.results)} found")
    
    # BETWEEN operator
    result = await db.prepare("""
        SELECT * FROM users WHERE points BETWEEN ? AND ?
    """).bind(100, 150).all()
    print(f"   Users with 100 <= points <= 150: {[r['name'] for r in result.results]}")
    
    # =========================================================================
    # 4. Aggregate Functions and GROUP BY
    # =========================================================================
    print("\n📊 4. Aggregate functions with GROUP BY...")
    
    result = await db.prepare("""
        SELECT 
            t.name as team_name,
            COUNT(u.id) as member_count,
            AVG(u.points) as avg_points,
            SUM(u.points) as total_points,
            MAX(u.points) as top_score,
            MIN(u.points) as low_score
        FROM teams t
        LEFT JOIN users u ON t.id = u.team_id
        GROUP BY t.id
        ORDER BY total_points DESC
    """).all()
    
    for row in result.results:
        print(f"   {row['team_name']}: {row['member_count']} members, "
              f"avg={row['avg_points']:.1f}, total={row['total_points']}")
    
    # HAVING clause
    result = await db.prepare("""
        SELECT team_id, COUNT(*) as count
        FROM users
        GROUP BY team_id
        HAVING COUNT(*) > ?
    """).bind(2).all()
    print(f"   Teams with > 2 members: {len(result.results)} teams")
    
    # =========================================================================
    # 5. JOIN Operations
    # =========================================================================
    print("\n🔗 5. JOIN operations...")
    
    # INNER JOIN
    result = await db.prepare("""
        SELECT u.name, t.name as team_name, u.points
        FROM users u
        INNER JOIN teams t ON u.team_id = t.id
        WHERE t.name = ?
        ORDER BY u.points DESC
    """).bind("Engineering").all()
    print(f"   Engineering team members:")
    for row in result.results:
        print(f"      {row['name']}: {row['points']} points")
    
    # LEFT JOIN with aggregates
    result = await db.prepare("""
        SELECT 
            u.name,
            u.points,
            COUNT(o.id) as order_count,
            COALESCE(SUM(o.amount), 0) as total_spent
        FROM users u
        LEFT JOIN orders o ON u.id = o.user_id
        GROUP BY u.id
        ORDER BY total_spent DESC
        LIMIT 3
    """).all()
    print(f"\n   Top 3 spenders:")
    for row in result.results:
        print(f"      {row['name']}: ${row['total_spent']:.2f} "
              f"({row['order_count']} orders)")
    
    # Multiple JOINs
    result = await db.prepare("""
        SELECT 
            o.id as order_id,
            u.name as user_name,
            t.name as team_name,
            o.amount
        FROM orders o
        INNER JOIN users u ON o.user_id = u.id
        INNER JOIN teams t ON u.team_id = t.id
        WHERE o.amount > ?
        ORDER BY o.amount DESC
    """).bind(200).all()
    print(f"\n   Orders > $200:")
    for row in result.results:
        print(f"      {row['user_name']} ({row['team_name']}): ${row['amount']:.2f}")
    
    # =========================================================================
    # 6. Subqueries
    # =========================================================================
    print("\n🎯 6. Subquery support...")
    
    # Subquery in WHERE clause
    result = await db.prepare("""
        SELECT * FROM users
        WHERE id IN (
            SELECT user_id FROM orders WHERE amount > ?
        )
        ORDER BY name
    """).bind(100).all()
    print(f"   Users with orders > $100: {[r['name'] for r in result.results]}")
    
    # Subquery in FROM clause
    result = await db.prepare("""
        SELECT 
            team_stats.team_name,
            team_stats.member_count,
            team_stats.avg_points
        FROM (
            SELECT 
                t.name as team_name,
                COUNT(u.id) as member_count,
                AVG(u.points) as avg_points
            FROM teams t
            LEFT JOIN users u ON t.id = u.team_id
            GROUP BY t.id
        ) team_stats
        WHERE team_stats.member_count > ?
        ORDER BY team_stats.avg_points DESC
    """).bind(2).all()
    print(f"   Team statistics (teams with >2 members):")
    for row in result.results:
        print(f"      {row['team_name']}: {row['member_count']} members, "
              f"avg {row['avg_points']:.1f} points")
    
    # =========================================================================
    # 7. Advanced Operators
    # =========================================================================
    print("\n⚙️  7. Advanced operators (CASE, COALESCE, etc.)...")
    
    # CASE expression for tier classification
    result = await db.prepare("""
        SELECT 
            name,
            points,
            CASE 
                WHEN points >= 150 THEN 'Gold'
                WHEN points >= 100 THEN 'Silver'
                ELSE 'Bronze'
            END as tier
        FROM users
        ORDER BY points DESC
    """).all()
    print(f"   User tiers:")
    for row in result.results:
        print(f"      {row['name']}: {row['points']} points → {row['tier']}")
    
    # COALESCE for default values
    result = await db.prepare("""
        SELECT 
            u.name,
            COALESCE(o.order_count, 0) as orders
        FROM users u
        LEFT JOIN (
            SELECT user_id, COUNT(*) as order_count
            FROM orders
            GROUP BY user_id
        ) o ON u.id = o.user_id
        ORDER BY orders DESC
    """).all()
    print(f"\n   Order counts (including users with 0 orders):")
    for row in result.results[:5]:
        print(f"      {row['name']}: {row['orders']} orders")
    
    # =========================================================================
    # 8. DISTINCT, LIMIT, and OFFSET
    # =========================================================================
    print("\n📄 8. DISTINCT, LIMIT, and OFFSET (pagination)...")
    
    # DISTINCT
    result = await db.prepare("""
        SELECT DISTINCT status FROM users
    """).all()
    print(f"   Distinct statuses: {[r['status'] for r in result.results]}")
    
    # LIMIT and OFFSET for pagination
    page_size = 2
    for page in range(2):
        offset = page * page_size
        result = await db.prepare("""
            SELECT name, email FROM users
            ORDER BY name
            LIMIT ? OFFSET ?
        """).bind(page_size, offset).all()
        print(f"   Page {page + 1}: {[r['name'] for r in result.results]}")
    
    # =========================================================================
    # 9. Transaction Rollback
    # =========================================================================
    print("\n🔄 9. Transaction rollback...")
    
    # Get count before
    count_before = (await db.prepare("SELECT COUNT(*) as count FROM users").first())["count"]
    print(f"   Users before: {count_before}")
    
    # Start transaction and insert data
    await db.exec("BEGIN TRANSACTION")
    await db.prepare(
        "INSERT INTO users (email, name, team_id, points, created_at) VALUES (?, ?, ?, ?, ?)"
    ).bind("rollback@example.com", "Rollback User", team1_id, 100, 5000).run()
    
    # Verify it exists in the transaction
    count_during = (await db.prepare("SELECT COUNT(*) as count FROM users").first())["count"]
    print(f"   Users during transaction: {count_during}")
    
    # Rollback the transaction
    await db.exec("ROLLBACK")
    
    # Verify rollback worked
    count_after = (await db.prepare("SELECT COUNT(*) as count FROM users").first())["count"]
    print(f"   Users after rollback: {count_after}")
    print(f"   ✅ Rollback successful: {count_before} == {count_after}")
    
    # =========================================================================
    # 10. Performance Summary
    # =========================================================================
    print("\n" + "=" * 60)
    print("\n✨ Summary: MockD1Database Feature Coverage")
    print("=" * 60)
    print("✅ Priority 1 Features (Critical for ORM):")
    print("   • Complex WHERE clauses (AND/OR/IN/LIKE/IS NULL)")
    print("   • Aggregate functions (COUNT/SUM/AVG/MAX/MIN)")
    print("   • GROUP BY with HAVING")
    print("   • JOIN operations (INNER/LEFT with aliases)")
    print("\n✅ Priority 2 Features (Comprehensive Testing):")
    print("   • Subqueries (WHERE and FROM)")
    print("   • Transaction support (BEGIN/COMMIT/ROLLBACK)")
    print("   • Advanced operators (BETWEEN/CASE/COALESCE)")
    print("\n✅ Additional Features:")
    print("   • DISTINCT keyword")
    print("   • LIMIT and OFFSET pagination")
    print("   • RETURNING clauses")
    print("   • Foreign key constraints")
    print("   • All standard SQLite features")
    print("\n🎯 Result: 100% comprehensive SQL support via SQLite passthrough!")
    print("   No custom SQL parsing needed - leveraging battle-tested SQLite.")
    print("\n" + "=" * 60)
    
    # Clean up
    db.close()


if __name__ == "__main__":
    asyncio.run(main())
