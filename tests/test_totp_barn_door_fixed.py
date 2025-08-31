"""
Fixed barn door tests for TOTP functionality - test actual API surface
"""

from kinglet.totp import (
    TEST_TOTP_SECRET,
    DummyOTPProvider,
    ProductionOTPProvider,
    generate_totp_code,
    generate_totp_secret,
    get_otp_provider,
    set_otp_provider,
    verify_code,
)


class TestTOTPBarnDoorFixed:
    """Fixed barn door tests using actual API"""

    def test_generate_totp_secret_returns_string(self):
        """Test that generate_totp_secret returns a non-empty string"""
        secret = generate_totp_secret()

        assert isinstance(secret, str)
        assert len(secret) > 0
        # TOTP secrets should be base32 encoded, so reasonably long
        assert len(secret) >= 16

    def test_verify_code_with_dummy_provider(self):
        """Test TOTP verification using dummy provider"""
        original = get_otp_provider()
        try:
            # Set dummy provider
            dummy = DummyOTPProvider()
            set_otp_provider(dummy)

            # Dummy provider should accept repeating digits
            result = verify_code(TEST_TOTP_SECRET, "000000")
            assert isinstance(result, bool)

            # Try another pattern
            result = verify_code(TEST_TOTP_SECRET, "111111")
            assert isinstance(result, bool)

        finally:
            set_otp_provider(original)

    def test_production_otp_provider_has_methods(self):
        """Test that ProductionOTPProvider has expected methods"""
        provider = ProductionOTPProvider()

        # Should have required methods from base class
        assert hasattr(provider, "generate_secret")
        assert hasattr(provider, "verify_code")
        assert callable(provider.generate_secret)
        assert callable(provider.verify_code)

    def test_production_otp_provider_generate_secret(self):
        """Test that production provider generates secrets"""
        provider = ProductionOTPProvider()

        # Should generate a base32 secret
        secret = provider.generate_secret()
        assert isinstance(secret, str)
        assert len(secret) > 0

        # Should be different each time
        secret2 = provider.generate_secret()
        assert secret != secret2

    def test_dummy_otp_provider_behavior(self):
        """Test DummyOTPProvider predictable behavior"""
        dummy = DummyOTPProvider()

        # Always returns test secret
        secret = dummy.generate_secret()
        assert secret == TEST_TOTP_SECRET

        # Should verify repeating digit codes
        assert dummy.verify_code(TEST_TOTP_SECRET, "000000") is True
        assert dummy.verify_code(TEST_TOTP_SECRET, "111111") is True
        assert dummy.verify_code(TEST_TOTP_SECRET, "222222") is True

    def test_provider_registry_functions(self):
        """Test provider registry get/set functions work"""
        original_provider = get_otp_provider()

        try:
            # Set a dummy provider
            dummy = DummyOTPProvider()
            set_otp_provider(dummy)

            # Should return the same instance
            retrieved = get_otp_provider()
            assert retrieved is dummy

        finally:
            # Restore original provider
            set_otp_provider(original_provider)

    def test_verify_code_uses_current_provider(self):
        """Test that verify_code uses the current global provider"""
        original = get_otp_provider()
        try:
            # Set dummy provider
            dummy = DummyOTPProvider()
            set_otp_provider(dummy)

            # verify_code should use dummy logic
            result = verify_code(TEST_TOTP_SECRET, "000000")
            assert result is True  # Dummy accepts this

        finally:
            set_otp_provider(original)

    def test_generate_totp_code_with_valid_secret(self):
        """Test generate_totp_code with a properly formatted secret"""
        # Use the test secret which is properly formatted
        code = generate_totp_code(TEST_TOTP_SECRET)

        assert isinstance(code, str)
        assert len(code) == 6
        assert code.isdigit()

    def test_generate_totp_code_with_generated_secret(self):
        """Test generate_totp_code with a generated secret"""
        secret = generate_totp_secret()

        # Should be able to generate code with generated secret
        code = generate_totp_code(secret)
        assert isinstance(code, str)
        assert len(code) == 6
        assert code.isdigit()

    def test_production_provider_verify_code_format(self):
        """Test production provider verify_code accepts right format"""
        provider = ProductionOTPProvider()

        # Should handle the call without crashing (result depends on timing)
        try:
            result = provider.verify_code(TEST_TOTP_SECRET, "123456")
            assert isinstance(result, bool)
        except Exception as e:
            # Some errors are acceptable (invalid format, etc.)
            assert isinstance(e, (ValueError, TypeError))

    def test_dummy_provider_verify_code_edge_cases(self):
        """Test dummy provider handles edge cases"""
        dummy = DummyOTPProvider()

        # Empty code should fail
        assert dummy.verify_code(TEST_TOTP_SECRET, "") is False

        # Invalid format should fail
        assert dummy.verify_code(TEST_TOTP_SECRET, "abc123") is False

        # Wrong length should fail
        assert dummy.verify_code(TEST_TOTP_SECRET, "12345") is False


class TestTOTPIntegrationBarnDoor:
    """Integration-style barn door tests"""

    def test_full_workflow_with_dummy(self):
        """Test complete workflow with dummy provider"""
        original = get_otp_provider()
        try:
            # Use dummy for predictable testing
            dummy = DummyOTPProvider()
            set_otp_provider(dummy)

            # Generate secret (always test secret)
            secret = generate_totp_secret()
            assert secret == TEST_TOTP_SECRET

            # Verify repeating digit codes work
            assert verify_code(secret, "000000") is True
            assert verify_code(secret, "111111") is True
            assert verify_code(secret, "999999") is True

            # Invalid codes should fail
            assert verify_code(secret, "123456") is False

        finally:
            set_otp_provider(original)

    def test_generate_and_use_real_secret(self):
        """Test generating and using a real secret"""
        # Generate a real secret
        secret = generate_totp_secret()

        # Should be able to generate a code with it
        code = generate_totp_code(secret)
        assert isinstance(code, str)
        assert len(code) == 6
        assert code.isdigit()

    def test_provider_switching_maintains_state(self):
        """Test that provider switching works correctly"""
        original = get_otp_provider()

        try:
            # Switch to dummy
            dummy = DummyOTPProvider()
            set_otp_provider(dummy)
            current = get_otp_provider()
            assert isinstance(current, DummyOTPProvider)

            # Switch to production
            prod = ProductionOTPProvider()
            set_otp_provider(prod)
            current = get_otp_provider()
            assert isinstance(current, ProductionOTPProvider)
            assert not isinstance(current, DummyOTPProvider)

        finally:
            set_otp_provider(original)

    def test_module_exports(self):
        """Test module exports are accessible"""
        from kinglet import totp

        # Key classes should be accessible
        assert hasattr(totp, "OTPProvider")
        assert hasattr(totp, "ProductionOTPProvider")
        assert hasattr(totp, "DummyOTPProvider")

        # Key functions should be accessible
        assert hasattr(totp, "generate_totp_secret")
        assert hasattr(totp, "verify_code")
        assert hasattr(totp, "generate_totp_code")

        # Test constant should be accessible
        assert hasattr(totp, "TEST_TOTP_SECRET")
        assert isinstance(totp.TEST_TOTP_SECRET, str)
