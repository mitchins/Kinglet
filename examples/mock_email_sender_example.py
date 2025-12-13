"""
MockEmailSender Usage Example

This example demonstrates how to use MockEmailSender to test email
functionality without actually sending emails via AWS SES.
"""

import asyncio
from unittest.mock import patch

from kinglet import MockEmailSender
from kinglet.ses import send_email


async def send_welcome_email(env, user_email: str, user_name: str):
    """Example function that sends a welcome email"""
    result = await send_email(
        env,
        from_email="welcome@example.com",
        to=[user_email],
        subject=f"Welcome, {user_name}!",
        body_text=f"Hi {user_name},\n\nWelcome to our platform!",
        body_html=f"<h1>Welcome, {user_name}!</h1><p>Welcome to our platform!</p>",
    )
    return result


async def send_password_reset(env, user_email: str, reset_token: str):
    """Example function that sends a password reset email"""
    result = await send_email(
        env,
        from_email="noreply@example.com",
        to=[user_email],
        subject="Password Reset Request",
        body_text=f"Reset token: {reset_token}",
    )
    return result


async def example_basic_usage():
    """Example 1: Basic usage - verify email was sent"""
    print("\n=== Example 1: Basic Usage ===")

    mock_sender = MockEmailSender()

    # Use the mock sender
    result = await mock_sender.send_email(
        from_email="test@example.com",
        to=["user@example.com"],
        subject="Test Email",
        body_text="This is a test",
    )

    print(f"Email sent successfully: {result.success}")
    print(f"Message ID: {result.message_id}")
    print(f"Total emails sent: {mock_sender.count}")
    print(f"First email subject: {mock_sender.sent_emails[0].subject}")


async def example_with_patching():
    """Example 2: Using MockEmailSender with patching"""
    print("\n=== Example 2: Using with Patching ===")

    mock_sender = MockEmailSender()

    # Patch the send_email function to use our mock
    with patch("__main__.send_email", mock_sender.send_email):
        # Now when send_welcome_email calls send_email, it uses the mock
        result = await send_welcome_email(None, "alice@example.com", "Alice")

        print(f"Email sent: {result.success}")

    # Verify the email was sent
    mock_sender.assert_sent(to="alice@example.com", subject="Welcome, Alice!")
    print(f"Verified email sent to alice@example.com")


async def example_filtering_emails():
    """Example 3: Filtering and inspecting sent emails"""
    print("\n=== Example 3: Filtering Emails ===")

    mock_sender = MockEmailSender()

    # Send multiple emails
    await mock_sender.send_email(
        from_email="noreply@example.com",
        to=["alice@example.com"],
        subject="Welcome",
        body_text="Welcome!",
    )

    await mock_sender.send_email(
        from_email="noreply@example.com",
        to=["bob@example.com"],
        subject="Welcome",
        body_text="Welcome!",
    )

    await mock_sender.send_email(
        from_email="noreply@example.com",
        to=["alice@example.com"],
        subject="Password Reset",
        body_text="Reset your password",
    )

    # Filter by recipient
    alice_emails = mock_sender.get_sent_to("alice@example.com")
    print(f"Emails sent to Alice: {len(alice_emails)}")

    # Filter by subject
    welcome_emails = mock_sender.get_by_subject("Welcome")
    print(f"Welcome emails sent: {len(welcome_emails)}")

    # Use assertions
    mock_sender.assert_sent(to="alice@example.com", count=2)
    mock_sender.assert_sent(subject="Welcome", count=2)
    print("All assertions passed!")


async def example_simulating_failures():
    """Example 4: Simulating email failures"""
    print("\n=== Example 4: Simulating Failures ===")

    mock_sender = MockEmailSender()

    # Configure a specific email to fail
    mock_sender.set_failure_for("bounced@example.com", "Address bounced")

    # This will succeed
    result1 = await mock_sender.send_email(
        from_email="test@example.com",
        to=["good@example.com"],
        subject="Test",
        body_text="Hello",
    )
    print(f"Email to good@example.com: {result1.success}")

    # This will fail
    result2 = await mock_sender.send_email(
        from_email="test@example.com",
        to=["bounced@example.com"],
        subject="Test",
        body_text="Hello",
    )
    print(f"Email to bounced@example.com: {result2.success}")
    print(f"Error: {result2.error}")

    # Check stats
    print(f"Total sent: {mock_sender.count}")
    print(f"Successful: {mock_sender.success_count}")
    print(f"Failed: {mock_sender.failure_count}")


async def example_bulk_sending():
    """Example 5: Testing bulk email sending"""
    print("\n=== Example 5: Bulk Email Sending ===")

    mock_sender = MockEmailSender()

    recipients = [
        ("alice@example.com", "Alice"),
        ("bob@example.com", "Bob"),
        ("charlie@example.com", "Charlie"),
    ]

    # Send emails to multiple recipients
    for email, name in recipients:
        await mock_sender.send_email(
            from_email="newsletter@example.com",
            to=[email],
            subject="Monthly Newsletter",
            body_text=f"Hi {name}, here's your newsletter!",
        )

    print(f"Sent {mock_sender.count} emails")

    # Verify all were sent successfully
    assert mock_sender.success_count == 3
    assert mock_sender.failure_count == 0
    print("All emails sent successfully!")

    # Check specific email
    alice_email = mock_sender.get_sent_to("alice@example.com")[0]
    print(f"Alice's email body: {alice_email.body_text}")


async def example_default_failure_mode():
    """Example 6: Default failure mode for testing error handling"""
    print("\n=== Example 6: Default Failure Mode ===")

    # Create mock that fails by default
    mock_sender = MockEmailSender(default_success=False)

    result = await mock_sender.send_email(
        from_email="test@example.com",
        to=["user@example.com"],
        subject="Test",
        body_text="This will fail",
    )

    print(f"Email sent: {result.success}")
    print(f"Error: {result.error}")

    # Switch to success mode
    mock_sender.set_default_success()

    result2 = await mock_sender.send_email(
        from_email="test@example.com",
        to=["user@example.com"],
        subject="Test",
        body_text="This will succeed",
    )

    print(f"Email sent after switching mode: {result2.success}")


async def example_integration_test():
    """Example 7: Integration test pattern"""
    print("\n=== Example 7: Integration Test Pattern ===")

    mock_sender = MockEmailSender()

    # Simulate user registration workflow
    async def register_user(env, email: str, name: str):
        # ... registration logic ...

        # Send verification email
        result = await send_email(
            env,
            from_email="verify@example.com",
            to=[email],
            subject="Verify your email",
            body_text=f"Hi {name}, click here to verify",
        )
        return result.success

    # Patch and test
    with patch("__main__.send_email", mock_sender.send_email):
        success = await register_user(None, "newuser@example.com", "New User")

        assert success
        mock_sender.assert_sent(to="newuser@example.com", count=1)

        verification_email = mock_sender.sent_emails[0]
        assert "verify" in verification_email.subject.lower()
        assert "New User" in verification_email.body_text

        print("User registration workflow test passed!")


async def main():
    """Run all examples"""
    print("MockEmailSender Usage Examples")
    print("=" * 50)

    await example_basic_usage()
    await example_with_patching()
    await example_filtering_emails()
    await example_simulating_failures()
    await example_bulk_sending()
    await example_default_failure_mode()
    await example_integration_test()

    print("\n" + "=" * 50)
    print("All examples completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
