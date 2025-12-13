"""
Tests for MockEmailSender - Mock Email Sender for Unit Testing
"""

from datetime import UTC, datetime

import pytest

from kinglet import EmailMockError, MockEmailSender, MockSentEmail
from kinglet.ses import EmailResult


class TestMockSentEmail:
    """Test MockSentEmail dataclass"""

    def test_basic_creation(self):
        """Test creating a MockSentEmail record"""
        email = MockSentEmail(
            from_email="sender@example.com",
            to=["recipient@example.com"],
            subject="Test Subject",
            body_text="Test body",
            message_id="test-message-id",
        )
        assert email.from_email == "sender@example.com"
        assert email.to == ["recipient@example.com"]
        assert email.subject == "Test Subject"
        assert email.body_text == "Test body"
        assert email.success is True
        assert email.error is None
        assert email.message_id == "test-message-id"

    def test_default_message_id(self):
        """Test that message_id defaults to None"""
        email = MockSentEmail(
            from_email="sender@example.com",
            to=["recipient@example.com"],
            subject="Test Subject",
            body_text="Test body",
        )
        assert email.message_id is None

    def test_with_optional_fields(self):
        """Test MockSentEmail with all optional fields"""
        email = MockSentEmail(
            from_email="sender@example.com",
            to=["recipient@example.com"],
            subject="Test Subject",
            body_text="Test body",
            body_html="<p>Test body</p>",
            cc=["cc@example.com"],
            bcc=["bcc@example.com"],
            reply_to=["reply@example.com"],
            region="us-east-1",
        )
        assert email.body_html == "<p>Test body</p>"
        assert email.cc == ["cc@example.com"]
        assert email.bcc == ["bcc@example.com"]
        assert email.reply_to == ["reply@example.com"]
        assert email.region == "us-east-1"

    def test_failure_record(self):
        """Test recording a failed email"""
        email = MockSentEmail(
            from_email="sender@example.com",
            to=["recipient@example.com"],
            subject="Test Subject",
            body_text="Test body",
            success=False,
            error="Delivery failed",
        )
        assert email.success is False
        assert email.error == "Delivery failed"


class TestMockEmailSender:
    """Test MockEmailSender functionality"""

    @pytest.mark.asyncio
    async def test_basic_send(self):
        """Test sending a basic email"""
        sender = MockEmailSender()
        result = await sender.send_email(
            from_email="sender@example.com",
            to=["recipient@example.com"],
            subject="Test Subject",
            body_text="Test body",
        )

        assert isinstance(result, EmailResult)
        assert result.success is True
        assert result.message_id is not None
        assert result.error is None
        assert len(sender.sent_emails) == 1

        sent = sender.sent_emails[0]
        assert sent.from_email == "sender@example.com"
        assert sent.to == ["recipient@example.com"]
        assert sent.subject == "Test Subject"
        assert sent.body_text == "Test body"

    @pytest.mark.asyncio
    async def test_send_with_env(self):
        """Test that env parameter is accepted but ignored"""
        sender = MockEmailSender()

        class MockEnv:
            AWS_REGION = "us-east-1"
            AWS_ACCESS_KEY_ID = "test"
            AWS_SECRET_ACCESS_KEY = "test"

        result = await sender.send_email(
            MockEnv(),  # env parameter should be ignored
            from_email="sender@example.com",
            to=["recipient@example.com"],
            subject="Test Subject",
            body_text="Test body",
        )

        assert result.success is True
        assert len(sender.sent_emails) == 1

    @pytest.mark.asyncio
    async def test_send_with_all_fields(self):
        """Test sending an email with all optional fields"""
        sender = MockEmailSender()
        result = await sender.send_email(
            from_email="sender@example.com",
            to=["recipient@example.com"],
            subject="Test Subject",
            body_text="Test body",
            body_html="<p>Test body</p>",
            cc=["cc@example.com"],
            bcc=["bcc@example.com"],
            reply_to=["reply@example.com"],
            region="us-west-2",
        )

        assert result.success is True
        sent = sender.sent_emails[0]
        assert sent.body_html == "<p>Test body</p>"
        assert sent.cc == ["cc@example.com"]
        assert sent.bcc == ["bcc@example.com"]
        assert sent.reply_to == ["reply@example.com"]
        assert sent.region == "us-west-2"

    @pytest.mark.asyncio
    async def test_multiple_sends(self):
        """Test sending multiple emails"""
        sender = MockEmailSender()

        for i in range(3):
            await sender.send_email(
                from_email="sender@example.com",
                to=[f"recipient{i}@example.com"],
                subject=f"Subject {i}",
                body_text=f"Body {i}",
            )

        assert len(sender.sent_emails) == 3
        assert sender.count == 3
        assert sender.success_count == 3
        assert sender.failure_count == 0

    @pytest.mark.asyncio
    async def test_set_failure_for(self):
        """Test setting specific email to fail"""
        sender = MockEmailSender()
        sender.set_failure_for("bad@example.com", "Invalid address")

        # This should succeed
        result1 = await sender.send_email(
            from_email="sender@example.com",
            to=["good@example.com"],
            subject="Test",
            body_text="Body",
        )
        assert result1.success is True

        # This should fail
        result2 = await sender.send_email(
            from_email="sender@example.com",
            to=["bad@example.com"],
            subject="Test",
            body_text="Body",
        )
        assert result2.success is False
        assert result2.error == "Invalid address"
        assert result2.message_id is None

        assert sender.count == 2
        assert sender.success_count == 1
        assert sender.failure_count == 1

    @pytest.mark.asyncio
    async def test_clear_failures(self):
        """Test clearing configured failures"""
        sender = MockEmailSender()
        sender.set_failure_for("bad@example.com", "Invalid address")

        # Should fail
        result1 = await sender.send_email(
            from_email="sender@example.com",
            to=["bad@example.com"],
            subject="Test",
            body_text="Body",
        )
        assert result1.success is False

        # Clear failures
        sender.clear_failures()

        # Should now succeed
        result2 = await sender.send_email(
            from_email="sender@example.com",
            to=["bad@example.com"],
            subject="Test",
            body_text="Body",
        )
        assert result2.success is True

    @pytest.mark.asyncio
    async def test_default_failure(self):
        """Test setting all emails to fail by default"""
        sender = MockEmailSender(default_success=False)

        result = await sender.send_email(
            from_email="sender@example.com",
            to=["recipient@example.com"],
            subject="Test",
            body_text="Body",
        )

        assert result.success is False
        assert "configured to fail" in result.error
        assert result.message_id is None

    @pytest.mark.asyncio
    async def test_set_default_failure_with_custom_error(self):
        """Test setting custom error for default failures"""
        sender = MockEmailSender()
        sender.set_default_failure("Custom error message")

        result = await sender.send_email(
            from_email="sender@example.com",
            to=["recipient@example.com"],
            subject="Test",
            body_text="Body",
        )

        assert result.success is False
        assert result.error == "Custom error message"

    @pytest.mark.asyncio
    async def test_set_default_success(self):
        """Test switching from fail to success mode"""
        sender = MockEmailSender(default_success=False)

        # Should fail initially
        result1 = await sender.send_email(
            from_email="sender@example.com",
            to=["recipient@example.com"],
            subject="Test",
            body_text="Body",
        )
        assert result1.success is False

        # Switch to success mode
        sender.set_default_success()

        # Should now succeed
        result2 = await sender.send_email(
            from_email="sender@example.com",
            to=["recipient@example.com"],
            subject="Test",
            body_text="Body",
        )
        assert result2.success is True

    def test_clear(self):
        """Test clearing sent emails"""
        sender = MockEmailSender()
        sender.sent_emails.append(
            MockSentEmail(
                from_email="test@example.com",
                to=["user@example.com"],
                subject="Test",
                body_text="Body",
            )
        )

        assert len(sender.sent_emails) == 1
        sender.clear()
        assert len(sender.sent_emails) == 0

    @pytest.mark.asyncio
    async def test_get_sent_to(self):
        """Test filtering emails by recipient"""
        sender = MockEmailSender()

        await sender.send_email(
            from_email="sender@example.com",
            to=["alice@example.com"],
            subject="To Alice",
            body_text="Body",
        )
        await sender.send_email(
            from_email="sender@example.com",
            to=["bob@example.com"],
            subject="To Bob",
            body_text="Body",
        )
        await sender.send_email(
            from_email="sender@example.com",
            to=["alice@example.com"],
            subject="To Alice Again",
            body_text="Body",
        )

        alice_emails = sender.get_sent_to("alice@example.com")
        assert len(alice_emails) == 2
        assert all("alice@example.com" in e.to for e in alice_emails)

        bob_emails = sender.get_sent_to("bob@example.com")
        assert len(bob_emails) == 1
        assert "bob@example.com" in bob_emails[0].to

    @pytest.mark.asyncio
    async def test_get_by_subject(self):
        """Test filtering emails by subject"""
        sender = MockEmailSender()

        await sender.send_email(
            from_email="sender@example.com",
            to=["user@example.com"],
            subject="Welcome",
            body_text="Body",
        )
        await sender.send_email(
            from_email="sender@example.com",
            to=["user@example.com"],
            subject="Password Reset",
            body_text="Body",
        )
        await sender.send_email(
            from_email="sender@example.com",
            to=["user@example.com"],
            subject="Welcome",
            body_text="Body",
        )

        welcome_emails = sender.get_by_subject("Welcome")
        assert len(welcome_emails) == 2
        assert all(e.subject == "Welcome" for e in welcome_emails)

        reset_emails = sender.get_by_subject("Password Reset")
        assert len(reset_emails) == 1
        assert reset_emails[0].subject == "Password Reset"

    @pytest.mark.asyncio
    async def test_assert_sent_by_to(self):
        """Test assert_sent with to filter"""
        sender = MockEmailSender()

        await sender.send_email(
            from_email="sender@example.com",
            to=["user@example.com"],
            subject="Test",
            body_text="Body",
        )

        # Should pass
        sender.assert_sent(to="user@example.com")

        # Should fail
        with pytest.raises(AssertionError):
            sender.assert_sent(to="nobody@example.com")

    @pytest.mark.asyncio
    async def test_assert_sent_by_subject(self):
        """Test assert_sent with subject filter"""
        sender = MockEmailSender()

        await sender.send_email(
            from_email="sender@example.com",
            to=["user@example.com"],
            subject="Welcome",
            body_text="Body",
        )

        # Should pass
        sender.assert_sent(subject="Welcome")

        # Should fail
        with pytest.raises(AssertionError):
            sender.assert_sent(subject="Goodbye")

    @pytest.mark.asyncio
    async def test_assert_sent_with_count(self):
        """Test assert_sent with count parameter"""
        sender = MockEmailSender()

        for i in range(3):
            await sender.send_email(
                from_email="sender@example.com",
                to=["user@example.com"],
                subject="Test",
                body_text="Body",
            )

        # Should pass
        sender.assert_sent(count=3)
        sender.assert_sent(to="user@example.com", count=3)
        sender.assert_sent(subject="Test", count=3)

        # Should fail
        with pytest.raises(AssertionError, match="Expected 5 emails but found 3"):
            sender.assert_sent(count=5)

    @pytest.mark.asyncio
    async def test_assert_sent_combined_filters(self):
        """Test assert_sent with multiple filters"""
        sender = MockEmailSender()

        await sender.send_email(
            from_email="sender@example.com",
            to=["alice@example.com"],
            subject="Welcome",
            body_text="Body",
        )
        await sender.send_email(
            from_email="sender@example.com",
            to=["bob@example.com"],
            subject="Welcome",
            body_text="Body",
        )
        await sender.send_email(
            from_email="sender@example.com",
            to=["alice@example.com"],
            subject="Goodbye",
            body_text="Body",
        )

        # Should pass
        sender.assert_sent(to="alice@example.com", subject="Welcome", count=1)
        sender.assert_sent(subject="Welcome", count=2)

        # Should fail
        with pytest.raises(AssertionError):
            sender.assert_sent(to="alice@example.com", subject="Welcome", count=2)

    def test_count_properties(self):
        """Test count, success_count, and failure_count properties"""
        sender = MockEmailSender()

        # Add successful emails
        sender.sent_emails.append(
            MockSentEmail(
                from_email="test@example.com",
                to=["user@example.com"],
                subject="Success",
                body_text="Body",
                success=True,
            )
        )
        sender.sent_emails.append(
            MockSentEmail(
                from_email="test@example.com",
                to=["user@example.com"],
                subject="Success",
                body_text="Body",
                success=True,
            )
        )

        # Add failed email
        sender.sent_emails.append(
            MockSentEmail(
                from_email="test@example.com",
                to=["user@example.com"],
                subject="Failure",
                body_text="Body",
                success=False,
                error="Failed",
            )
        )

        assert sender.count == 3
        assert sender.success_count == 2
        assert sender.failure_count == 1


class TestMockEmailSenderIntegration:
    """Integration tests showing real-world usage patterns"""

    @pytest.mark.asyncio
    async def test_with_patching(self):
        """Test using MockEmailSender with patching"""
        from unittest.mock import patch

        sender = MockEmailSender()

        with patch("kinglet.ses.send_email", sender.send_email):
            # Import after patching
            from kinglet.ses import send_email

            result = await send_email(
                None,  # env
                from_email="app@example.com",
                to=["user@example.com"],
                subject="Test",
                body_text="Body",
            )

            assert result.success is True

        assert sender.count == 1
        assert sender.sent_emails[0].to == ["user@example.com"]

    @pytest.mark.asyncio
    async def test_verification_workflow(self):
        """Test a typical email verification workflow"""
        sender = MockEmailSender()

        # Simulate user registration flow
        user_email = "newuser@example.com"

        # Send verification email
        result = await sender.send_email(
            from_email="noreply@example.com",
            to=[user_email],
            subject="Verify Your Email",
            body_text="Click the link to verify",
            body_html="<p>Click the link to verify</p>",
        )

        assert result.success is True

        # Verify email was sent
        sender.assert_sent(to=user_email, subject="Verify Your Email", count=1)

        # Check email contents
        emails = sender.get_sent_to(user_email)
        assert len(emails) == 1
        assert emails[0].body_html is not None
        assert "verify" in emails[0].body_text.lower()

    @pytest.mark.asyncio
    async def test_bulk_email_scenario(self):
        """Test sending bulk emails with some failures"""
        sender = MockEmailSender()
        sender.set_failure_for("bounced@example.com", "Address bounced")

        recipients = [
            "user1@example.com",
            "user2@example.com",
            "bounced@example.com",
            "user3@example.com",
        ]

        results = []
        for recipient in recipients:
            result = await sender.send_email(
                from_email="newsletter@example.com",
                to=[recipient],
                subject="Monthly Newsletter",
                body_text="Newsletter content",
            )
            results.append(result)

        # Verify counts
        assert sender.count == 4
        assert sender.success_count == 3
        assert sender.failure_count == 1

        # Check which one failed
        failed_emails = [e for e in sender.sent_emails if not e.success]
        assert len(failed_emails) == 1
        assert "bounced@example.com" in failed_emails[0].to
        assert "bounced" in failed_emails[0].error

    @pytest.mark.asyncio
    async def test_notification_types(self):
        """Test different notification types"""
        sender = MockEmailSender()

        # Welcome email
        await sender.send_email(
            from_email="noreply@example.com",
            to=["user@example.com"],
            subject="Welcome to Our Service",
            body_text="Welcome!",
        )

        # Password reset
        await sender.send_email(
            from_email="noreply@example.com",
            to=["user@example.com"],
            subject="Password Reset Request",
            body_text="Reset your password",
        )

        # Notification
        await sender.send_email(
            from_email="noreply@example.com",
            to=["user@example.com"],
            subject="New Message",
            body_text="You have a new message",
        )

        # Verify all types sent
        assert sender.count == 3
        welcome_emails = sender.get_by_subject("Welcome to Our Service")
        assert len(welcome_emails) == 1
        reset_emails = sender.get_by_subject("Password Reset Request")
        assert len(reset_emails) == 1
        notification_emails = sender.get_by_subject("New Message")
        assert len(notification_emails) == 1
