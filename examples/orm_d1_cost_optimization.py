"""
D1 Cost Optimization Guide - Kinglet ORM

Demonstrates cost-optimized patterns for D1's row-based pricing.
D1 charges per row read/written, so every operation matters.

Key Principles:
• Eliminate pre-checks (let writes fail, map errors)  
• Use projection (only/values) to reduce columns read
• Use EXISTS instead of COUNT for boolean checks
• Use fail-fast patterns over defensive checks
• Batch operations when possible

Cost Model:
• Row reads: $0.001 per 1K rows
• Row writes: $1.00 per 1M rows 
• Each column in SELECT * counts as part of row read cost
"""

import asyncio
from kinglet.orm import Model, StringField, IntegerField, BooleanField
from kinglet.orm_errors import UniqueViolationError


# Example models
class User(Model):
    email = StringField(max_length=100, null=False, unique=True)
    username = StringField(max_length=50, null=False, unique=True)
    name = StringField(max_length=100, null=False)
    age = IntegerField(null=True)
    is_active = BooleanField(default=True)
    
    class Meta:
        table_name = "users"


class Post(Model):
    title = StringField(max_length=200, null=False)
    content = StringField(null=False)
    author_id = IntegerField(null=False)
    views = IntegerField(default=0)
    published = BooleanField(default=False)
    
    class Meta:
        table_name = "posts"


async def demonstrate_cost_patterns():
    """Show before/after patterns for D1 cost optimization"""
    from tests.mock_d1 import MockD1Database
    db = MockD1Database()
    
    await User.create_table(db)
    await Post.create_table(db)
    
    print("=== D1 COST OPTIMIZATION PATTERNS ===\\n")
    
    # Pattern 1: EXISTS vs COUNT
    print("1. BOOLEAN CHECKS: EXISTS vs COUNT")
    print("   ❌ BAD:  SELECT COUNT(*) FROM users WHERE active = 1")
    print("            (Scans ALL rows even if 1M+ users)")
    print("   ✅ GOOD: SELECT 1 FROM users WHERE active = 1 LIMIT 1") 
    print("            (Stops at first match)")
    
    # Create test data
    user = await User.objects.create(db, email="test@example.com", username="test", name="Test User")
    
    # Cost-optimized existence check
    has_users = await User.objects.exists(db)
    has_active_users = await User.objects.exists(db, is_active=True)
    print(f"   Result: has_users={has_users}, has_active={has_active_users}")
    print(f"   💰 Cost: 1 row read vs full table scan\\n")
    
    # Pattern 2: PROJECTION vs SELECT *
    print("2. FIELD SELECTION: Projection vs SELECT *")
    print("   ❌ BAD:  SELECT * FROM users (all 5 columns charged per row)")
    print("   ✅ GOOD: SELECT email FROM users (1 column charged per row)")
    
    # Create more test data
    await User.objects.create(db, email="user2@example.com", username="user2", name="User Two", age=25)
    await User.objects.create(db, email="user3@example.com", username="user3", name="User Three", age=30)
    
    # Cost-optimized field selection
    all_emails = await User.objects.values(db, 'email').all()
    user_summaries = await User.objects.only(db, 'email', 'name').all()
    
    print(f"   values() emails: {len(all_emails)} results, 1 column each")
    print(f"   only() summaries: {len(user_summaries)} results, 2 columns each")
    print(f"   💰 Cost: 1-2 columns per row vs 5 columns per row (60-80% savings)\\n")
    
    # Pattern 3: FAIL-FAST vs PRE-CHECKS
    print("3. UPSERT PATTERNS: Fail-fast vs Pre-checks")
    print("   ❌ BAD:  SELECT to check existence + INSERT/UPDATE (2-3 operations)")
    print("   ✅ GOOD: Try INSERT, handle UniqueViolationError (1-2 operations)")
    
    # Cost-optimized get-or-create
    user_new, created1 = await User.objects.get_or_create(
        db,
        email="new@example.com",
        defaults={"username": "newuser", "name": "New User", "age": 20}
    )
    
    user_existing, created2 = await User.objects.get_or_create(
        db, 
        email="new@example.com",  # Duplicate
        defaults={"username": "should_not_use", "name": "Should Not Use"}
    )
    
    print(f"   First call: created={created1} (1 INSERT)")
    print(f"   Second call: created={created2} (1 INSERT attempt + 1 SELECT)")
    print(f"   💰 Cost: 1-2 operations vs 2-3 operations (33-50% savings)\\n")
    
    # Pattern 4: API-OPTIMIZED QUERIES
    print("4. API RESPONSES: Optimized field selection")
    
    # Typical API endpoint needs
    async def get_user_list_api():
        """Cost-optimized user list for API endpoint"""
        return await User.objects.values(db, 'id', 'email', 'name', 'is_active').all()
    
    async def get_user_emails_api():
        """Email-only endpoint (e.g., for autocomplete)"""
        return await User.objects.values(db, 'email').all()
    
    async def check_email_available_api(email: str):
        """Email availability check"""
        return not await User.objects.exists(db, email=email)
        
    # Test API patterns
    user_list = await get_user_list_api()
    email_list = await get_user_emails_api() 
    email_available = await check_email_available_api("available@example.com")
    
    print(f"   User list API: {len(user_list)} users, 4 fields each")
    print(f"   Email list API: {len(email_list)} emails, 1 field each")
    print(f"   Email check API: available={email_available} (1 row read max)")
    print(f"   💰 Cost: Minimal columns + early termination\\n")
    
    # Pattern 5: BULK OPERATIONS
    print("5. BULK OPERATIONS: Batch vs Individual")
    print("   ❌ BAD:  Multiple individual INSERTs (N operations)")
    print("   ✅ GOOD: Single batch INSERT (1 operation)")
    
    # Cost-optimized bulk creation
    posts_data = [
        Post(title=f"Post {i}", content=f"Content {i}", author_id=user.id)
        for i in range(1, 6)
    ]
    
    created_posts = await Post.objects.bulk_create(db, posts_data)
    print(f"   Bulk created: {len(created_posts)} posts in 1 batch operation")
    print(f"   💰 Cost: 1 batch vs 5 individual INSERTs\\n")


async def demonstrate_antipatterns():
    """Show expensive antipatterns to avoid"""
    print("=== EXPENSIVE ANTIPATTERNS TO AVOID ===\\n")
    
    print("❌ 1. Unnecessary COUNT queries:")
    print("   if await User.objects.count(db) > 0:  # Scans all rows")
    print("   ✅ if await User.objects.exists(db):  # Stops at first row\\n")
    
    print("❌ 2. SELECT * when you need specific fields:")
    print("   users = await User.objects.all(db)  # All columns")
    print("   emails = [u.email for u in users]  # Only using email")
    print("   ✅ emails = await User.objects.values(db, 'email').all()\\n")
    
    print("❌ 3. Pre-check queries:")
    print("   existing = await User.objects.get(db, email='test')") 
    print("   if existing: existing.name = 'Updated'; await existing.save(db)")
    print("   ✅ Just try the write, handle UniqueViolationError\\n")
    
    print("❌ 4. Expensive pagination:")
    print("   page_10 = await User.objects.all(db)[9000:9020]  # Scans 9000 rows")
    print("   ✅ Use keyset pagination with WHERE id > last_id LIMIT 20\\n")
    
    print("❌ 5. Individual operations in loops:")
    print("   for data in batch: await Model.objects.create(db, **data)")
    print("   ✅ instances = [Model(**data) for data in batch]")
    print("      await Model.objects.bulk_create(db, instances)\\n")


async def show_cost_calculator():
    """Show potential cost savings with real numbers"""
    print("=== COST IMPACT CALCULATOR ===\\n")
    
    scenarios = [
        {
            "name": "User login check",
            "old_pattern": "SELECT * FROM users WHERE email=? + UPDATE last_login", 
            "old_cost": "2 operations (1 read all columns + 1 write)",
            "new_pattern": "SELECT id FROM users WHERE email=? + UPDATE last_login",
            "new_cost": "2 operations (1 read 1 column + 1 write)", 
            "savings": "~80% on read cost"
        },
        {
            "name": "Email availability check",
            "old_pattern": "SELECT COUNT(*) FROM users WHERE email=?",
            "old_cost": "Full table scan (10K+ rows)",
            "new_pattern": "SELECT 1 FROM users WHERE email=? LIMIT 1", 
            "new_cost": "1 row read maximum",
            "savings": "99%+ cost reduction"
        },
        {
            "name": "User list API (1000 users)",
            "old_pattern": "SELECT * FROM users (5 columns each)",
            "old_cost": "5000 column reads",
            "new_pattern": "SELECT id, email, name FROM users",
            "new_cost": "3000 column reads", 
            "savings": "40% cost reduction"
        },
        {
            "name": "Bulk user creation (100 users)",
            "old_pattern": "100 individual INSERTs",
            "old_cost": "100 write operations",
            "new_pattern": "1 batch INSERT with 100 values",
            "new_cost": "1 write operation",
            "savings": "99% cost reduction"
        }
    ]
    
    for scenario in scenarios:
        print(f"📊 {scenario['name']}:")
        print(f"   Old: {scenario['old_pattern']}")
        print(f"        {scenario['old_cost']}")
        print(f"   New: {scenario['new_pattern']}")
        print(f"        {scenario['new_cost']}")
        print(f"   💰 Savings: {scenario['savings']}\\n")


async def main():
    print("🚀 Kinglet ORM - D1 Cost Optimization Guide")
    print("=" * 50)
    
    await demonstrate_cost_patterns()
    await demonstrate_antipatterns() 
    await show_cost_calculator()
    
    print("=" * 50)
    print("✅ Key Takeaways:")
    print("• Use exists() instead of count() > 0")
    print("• Use values()/only() instead of SELECT *") 
    print("• Use fail-fast writes instead of pre-checks")
    print("• Use batch operations instead of loops")
    print("• Use keyset pagination instead of OFFSET")
    print("\\n💡 Result: 70-99% reduction in D1 row operations!")


if __name__ == "__main__":
    asyncio.run(main())