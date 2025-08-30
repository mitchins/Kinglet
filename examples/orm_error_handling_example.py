"""
ORM Error Handling Example - RFC7807 + Constraint Registry Demo

Demonstrates the complete error handling system with:
- Automatic constraint registration
- RFC7807 problem+json responses
- Central error middleware
- Production-safe field redaction
- Correlation ID tracking
"""

import asyncio

from kinglet.middleware import create_global_error_boundary
from kinglet.orm import BooleanField, IntegerField, Model, StringField
from kinglet.orm_errors import (
    DoesNotExistError,
    UniqueViolationError,
    ValidationError,
    get_constraint_registry,
    orm_problem_response,
)


# Define models (constraints auto-registered)
class User(Model):
    email = StringField(max_length=100, null=False, unique=True)
    username = StringField(max_length=50, null=False, unique=True)
    age = IntegerField(null=True)
    is_active = BooleanField(default=True)

    class Meta:
        table_name = "users"


class Post(Model):
    title = StringField(max_length=200, null=False)
    content = StringField(null=False)
    author_id = IntegerField(null=False)  # Foreign key to User
    published = BooleanField(default=False)

    class Meta:
        table_name = "posts"


def demo_constraint_registry():
    """Demonstrate automatic constraint registration and lookup"""
    print("=== Constraint Registry Demo ===")

    registry = get_constraint_registry()

    # Show auto-registered constraints
    for table_name in registry.list_tables():
        print(f"\n{table_name.upper()} table constraints:")
        constraints = registry.get_table_constraints(table_name)
        for name, info in constraints.items():
            constraint_type = info["type"]
            fields = ", ".join(info["fields"])
            print(f"  {name}: {constraint_type} on [{fields}]")

    # Test constraint lookup
    email_constraint = registry.get_constraint_info("users", "uq_users_email")
    print(f"\nEmail constraint lookup: {email_constraint}")

    # Test field-based lookup
    username_constraint = registry.find_constraint_by_fields("users", ["username"])
    print(f"Username field lookup: {username_constraint}")


async def demo_error_classification():
    """Demonstrate error classification with constraint registry"""
    print("\n=== Error Classification Demo ===")

    from tests.mock_d1 import MockD1Database

    db = MockD1Database()

    await User.create_table(db)

    try:
        # Create first user
        user1 = await User.objects.create(
            db, email="john@example.com", username="john", age=25
        )
        print(f"Created user: {user1.username}")

        # Try to create duplicate email - should raise UniqueViolationError
        user2 = await User.objects.create(
            db,
            email="john@example.com",  # Duplicate!
            username="john2",
            age=30,
        )

    except UniqueViolationError as e:
        print(f"✅ UniqueViolationError caught: {e}")
        print(f"   Field: {e.field_name}")
        print(f"   Original error: {type(e.original_error).__name__}")

    try:
        # Try to create user with null required field
        user3 = User(email=None, username="jane")  # email is required
        await user3.save(db)

    except ValidationError as e:
        print(f"✅ ValidationError caught: {e}")
        print(f"   Field: {e.field_name}")
        print(f"   Value: {e.value}")

    try:
        # Try to get non-existent user
        user = await User.objects.get_queryset(db).filter(id=999).get()

    except DoesNotExistError as e:
        print(f"✅ DoesNotExistError caught: {e}")
        print(f"   Model: {e.model_name}")


def demo_rfc7807_responses():
    """Demonstrate RFC7807 problem+json response generation"""
    print("\n=== RFC7807 Problem+JSON Demo ===")

    # Test validation error
    validation_error = ValidationError("email", "Invalid email format", "bad-email")

    # Development response (shows all fields)
    problem_dev, status, headers = orm_problem_response(
        validation_error, instance="/requests/dev-123", is_prod=False
    )

    print("Development mode response:")
    print(f"Status: {status}")
    print(f"Headers: {headers}")
    import json

    print(f"Body: {json.dumps(problem_dev, indent=2)}")

    # Production response (redacted)
    problem_prod, status, headers = orm_problem_response(
        validation_error,
        instance="/requests/prod-456",
        is_prod=True,  # Field redaction enabled
    )

    print("\nProduction mode response (redacted):")
    print(f"Body: {json.dumps(problem_prod, indent=2)}")


async def demo_error_boundary():
    """Demonstrate central error boundary middleware"""
    print("\n=== Error Boundary Middleware Demo ===")

    # Create error boundary for development
    error_boundary = create_global_error_boundary(
        is_prod=False,
        include_trace=False,  # Set to True to see stack traces
        correlation_header="X-Request-Id",
    )

    @error_boundary
    async def api_create_user(request, env):
        """Simulated API endpoint that may raise ORM errors"""
        from tests.mock_d1 import MockD1Database

        db = MockD1Database()
        await User.create_table(db)

        # Simulate creating a user with validation error
        user_data = {
            "email": None,  # This will cause ValidationError
            "username": "testuser",
            "age": 25,
        }

        user = await User.objects.create(db, **user_data)
        return {"user_id": user.id, "status": "created"}

    # Mock request/env objects
    class MockRequest:
        headers = {"X-Request-Id": "req-abc123"}

    class MockEnv:
        MODE = "dev"

    try:
        response = await api_create_user(MockRequest(), MockEnv())
        print(f"Unexpected success: {response}")
    except Exception as response:
        # Error boundary returns Response object
        if hasattr(response, "status") and hasattr(response, "body"):
            print("✅ Error boundary caught error")
            print(f"   Status: {response.status}")
            print(f"   Content-Type: {response.headers.get('Content-Type')}")

            # The response body contains the RFC7807 problem+json
            if hasattr(response, "_json_data"):
                body = response._json_data
            else:
                body = response.body

            print(f"   Problem+JSON: {json.dumps(body, indent=2)}")


async def main():
    """Run all demonstrations"""
    print("🚀 Kinglet ORM Error Handling System Demo")
    print("=" * 50)

    demo_constraint_registry()
    await demo_error_classification()
    demo_rfc7807_responses()
    await demo_error_boundary()

    print("\n" + "=" * 50)
    print("✅ All demonstrations completed successfully!")
    print("\nKey Features Demonstrated:")
    print("• Automatic constraint registration from model definitions")
    print("• Bulletproof error classification with field extraction")
    print("• RFC7807 compliant problem+json responses")
    print("• Production-safe field redaction")
    print("• Central error boundary middleware")
    print("• Correlation ID tracking for observability")


if __name__ == "__main__":
    asyncio.run(main())
