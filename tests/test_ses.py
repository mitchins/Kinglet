"""
Tests for Kinglet SES Email Module
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kinglet.ses import EmailResult, _get_env_var, send_email


class TestEmailResult:
    """Test EmailResult dataclass"""

    def test_success_result(self):
        """Test successful email result"""
        result = EmailResult(success=True, message_id="abc123")
        assert result.success is True
        assert result.message_id == "abc123"
        assert result.error is None

    def test_error_result(self):
        """Test error email result"""
        result = EmailResult(success=False, error="Something went wrong")
        assert result.success is False
        assert result.message_id is None
        assert result.error == "Something went wrong"

    def test_default_values(self):
        """Test default values for optional fields"""
        result = EmailResult(success=True)
        assert result.message_id is None
        assert result.error is None


class TestGetEnvVar:
    """Test environment variable extraction"""

    def test_attribute_access(self):
        """Test getting env var via attribute"""

        class MockEnv:
            AWS_REGION = "us-east-1"

        assert _get_env_var(MockEnv(), "AWS_REGION") == "us-east-1"

    def test_dict_access(self):
        """Test getting env var via dict-like access"""
        env = {"AWS_REGION": "eu-west-1"}
        assert _get_env_var(env, "AWS_REGION") == "eu-west-1"

    def test_missing_var(self):
        """Test missing env var returns None"""

        class MockEnv:
            pass

        assert _get_env_var(MockEnv(), "MISSING") is None

    def test_none_env(self):
        """Test None env returns None"""
        assert _get_env_var(None, "AWS_REGION") is None

    def test_undefined_value(self):
        """Test undefined value returns None"""

        class MockEnv:
            AWS_REGION = "undefined"

        # String "undefined" should be treated as missing
        assert _get_env_var(MockEnv(), "AWS_REGION") is None

    def test_dict_key_error(self):
        """Test dict-like access with missing key"""
        env = {"OTHER_KEY": "value"}
        assert _get_env_var(env, "AWS_REGION") is None

    def test_type_error_on_dict_access(self):
        """Test handling of TypeError on dict access"""

        class MockEnv:
            def __getitem__(self, key):
                raise TypeError("Not subscriptable")

        assert _get_env_var(MockEnv(), "AWS_REGION") is None


class TestSendEmail:
    """Test send_email function"""

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        """Test error when credentials are missing"""

        class MockEnv:
            pass

        result = await send_email(
            MockEnv(),
            from_email="test@example.com",
            to=["user@example.com"],
            subject="Test",
            body_text="Hello",
        )

        assert result.success is False
        assert result.error is not None
        assert "Missing AWS credentials" in result.error

    @pytest.mark.asyncio
    async def test_missing_region_only(self):
        """Test error when only region is missing"""

        class MockEnv:
            AWS_ACCESS_KEY_ID = "AKIATEST"
            AWS_SECRET_ACCESS_KEY = "secret"

        result = await send_email(
            MockEnv(),
            from_email="test@example.com",
            to=["user@example.com"],
            subject="Test",
            body_text="Hello",
        )

        assert result.success is False
        assert "Missing AWS credentials" in result.error

    @pytest.mark.asyncio
    async def test_missing_access_key_only(self):
        """Test error when only access key is missing"""

        class MockEnv:
            AWS_REGION = "us-east-1"
            AWS_SECRET_ACCESS_KEY = "secret"

        result = await send_email(
            MockEnv(),
            from_email="test@example.com",
            to=["user@example.com"],
            subject="Test",
            body_text="Hello",
        )

        assert result.success is False
        assert "Missing AWS credentials" in result.error

    @pytest.mark.asyncio
    async def test_missing_secret_key_only(self):
        """Test error when only secret key is missing"""

        class MockEnv:
            AWS_REGION = "us-east-1"
            AWS_ACCESS_KEY_ID = "AKIATEST"

        result = await send_email(
            MockEnv(),
            from_email="test@example.com",
            to=["user@example.com"],
            subject="Test",
            body_text="Hello",
        )

        assert result.success is False
        assert "Missing AWS credentials" in result.error

    @pytest.mark.asyncio
    async def test_with_credentials_fails_without_js(self):
        """Test that with credentials, it fails on JS import (expected outside Workers)"""

        class MockEnv:
            AWS_REGION = "us-east-1"
            AWS_ACCESS_KEY_ID = "AKIATEST"
            AWS_SECRET_ACCESS_KEY = "secret"

        result = await send_email(
            MockEnv(),
            from_email="test@example.com",
            to=["user@example.com"],
            subject="Test",
            body_text="Hello",
        )

        # Outside Workers, will fail on js import
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_region_override(self):
        """Test that region parameter is accepted"""

        class MockEnv:
            AWS_REGION = "us-east-1"
            AWS_ACCESS_KEY_ID = "AKIATEST"
            AWS_SECRET_ACCESS_KEY = "secret"

        # Will fail due to no JS, but tests parameter handling
        result = await send_email(
            MockEnv(),
            from_email="test@example.com",
            to=["user@example.com"],
            subject="Test",
            body_text="Hello",
            region="eu-west-1",  # Override
        )

        # Should fail (no JS runtime), but not on credentials
        assert result.success is False

    @pytest.mark.asyncio
    async def test_with_optional_params(self):
        """Test send_email with all optional parameters"""

        class MockEnv:
            AWS_REGION = "us-east-1"
            AWS_ACCESS_KEY_ID = "AKIATEST"
            AWS_SECRET_ACCESS_KEY = "secret"

        result = await send_email(
            MockEnv(),
            from_email="test@example.com",
            to=["user@example.com"],
            subject="Test",
            body_text="Hello",
            body_html="<p>Hello</p>",
            cc=["cc@example.com"],
            bcc=["bcc@example.com"],
            reply_to=["reply@example.com"],
        )

        # Will fail (no JS), but tests parameter validation
        assert result.success is False


class TestSendEmailWithMockedJS:
    """Tests with mocked JS runtime for better coverage"""

    @pytest.mark.asyncio
    async def test_successful_send_with_mock(self):
        """Test successful email send with mocked JS"""

        class MockEnv:
            AWS_REGION = "us-east-1"
            AWS_ACCESS_KEY_ID = "AKIATEST"
            AWS_SECRET_ACCESS_KEY = "secret"

        # Mock the _sign_aws_request function
        with patch("kinglet.ses._sign_aws_request") as mock_sign:
            mock_sign.return_value = MagicMock()

            # Mock js module
            mock_js = MagicMock()
            mock_response = MagicMock()
            mock_response.ok = True
            mock_response.text = AsyncMock(
                return_value='{"MessageId": "test-message-id"}'
            )

            mock_js.fetch = AsyncMock(return_value=mock_response)
            mock_js.Object.fromEntries = MagicMock(return_value={})
            mock_js.Array.of = MagicMock(return_value=[])

            with patch.dict("sys.modules", {"js": mock_js}):
                result = await send_email(
                    MockEnv(),
                    from_email="test@example.com",
                    to=["user@example.com"],
                    subject="Test",
                    body_text="Hello",
                )

                assert result.success is True
                assert result.message_id == "test-message-id"

    @pytest.mark.asyncio
    async def test_ses_error_response(self):
        """Test SES error response handling"""

        class MockEnv:
            AWS_REGION = "us-east-1"
            AWS_ACCESS_KEY_ID = "AKIATEST"
            AWS_SECRET_ACCESS_KEY = "secret"

        with patch("kinglet.ses._sign_aws_request") as mock_sign:
            mock_sign.return_value = MagicMock()

            mock_js = MagicMock()
            mock_response = MagicMock()
            mock_response.ok = False
            mock_response.text = AsyncMock(return_value='{"Message": "Access Denied"}')

            mock_js.fetch = AsyncMock(return_value=mock_response)
            mock_js.Object.fromEntries = MagicMock(return_value={})
            mock_js.Array.of = MagicMock(return_value=[])

            with patch.dict("sys.modules", {"js": mock_js}):
                result = await send_email(
                    MockEnv(),
                    from_email="test@example.com",
                    to=["user@example.com"],
                    subject="Test",
                    body_text="Hello",
                )

                assert result.success is False
                assert "SES error" in result.error

    @pytest.mark.asyncio
    async def test_success_with_invalid_json_response(self):
        """Test successful response with non-JSON body"""

        class MockEnv:
            AWS_REGION = "us-east-1"
            AWS_ACCESS_KEY_ID = "AKIATEST"
            AWS_SECRET_ACCESS_KEY = "secret"

        with patch("kinglet.ses._sign_aws_request") as mock_sign:
            mock_sign.return_value = MagicMock()

            mock_js = MagicMock()
            mock_response = MagicMock()
            mock_response.ok = True
            mock_response.text = AsyncMock(return_value="OK")  # Not JSON

            mock_js.fetch = AsyncMock(return_value=mock_response)
            mock_js.Object.fromEntries = MagicMock(return_value={})
            mock_js.Array.of = MagicMock(return_value=[])

            with patch.dict("sys.modules", {"js": mock_js}):
                result = await send_email(
                    MockEnv(),
                    from_email="test@example.com",
                    to=["user@example.com"],
                    subject="Test",
                    body_text="Hello",
                )

                # Should still be success, just no message_id
                assert result.success is True
                assert result.message_id is None

    @pytest.mark.asyncio
    async def test_with_html_body(self):
        """Test email with HTML body"""

        class MockEnv:
            AWS_REGION = "us-east-1"
            AWS_ACCESS_KEY_ID = "AKIATEST"
            AWS_SECRET_ACCESS_KEY = "secret"

        with patch("kinglet.ses._sign_aws_request") as mock_sign:
            mock_sign.return_value = MagicMock()

            mock_js = MagicMock()
            mock_response = MagicMock()
            mock_response.ok = True
            mock_response.text = AsyncMock(return_value='{"MessageId": "html-msg"}')

            mock_js.fetch = AsyncMock(return_value=mock_response)
            mock_js.Object.fromEntries = MagicMock(return_value={})
            mock_js.Array.of = MagicMock(return_value=[])

            with patch.dict("sys.modules", {"js": mock_js}):
                result = await send_email(
                    MockEnv(),
                    from_email="test@example.com",
                    to=["user@example.com"],
                    subject="Test",
                    body_text="Hello",
                    body_html="<p>Hello</p>",
                )

                assert result.success is True

    @pytest.mark.asyncio
    async def test_with_cc_bcc_reply_to(self):
        """Test email with CC, BCC, and Reply-To"""

        class MockEnv:
            AWS_REGION = "us-east-1"
            AWS_ACCESS_KEY_ID = "AKIATEST"
            AWS_SECRET_ACCESS_KEY = "secret"

        with patch("kinglet.ses._sign_aws_request") as mock_sign:
            mock_sign.return_value = MagicMock()

            mock_js = MagicMock()
            mock_response = MagicMock()
            mock_response.ok = True
            mock_response.text = AsyncMock(return_value='{"MessageId": "full-msg"}')

            mock_js.fetch = AsyncMock(return_value=mock_response)
            mock_js.Object.fromEntries = MagicMock(return_value={})
            mock_js.Array.of = MagicMock(return_value=[])

            with patch.dict("sys.modules", {"js": mock_js}):
                result = await send_email(
                    MockEnv(),
                    from_email="test@example.com",
                    to=["user@example.com"],
                    subject="Test",
                    body_text="Hello",
                    cc=["cc1@example.com", "cc2@example.com"],
                    bcc=["bcc@example.com"],
                    reply_to=["reply@example.com"],
                )

                assert result.success is True
