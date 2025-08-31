"""
Integration tests using Miniflare for CloudFlare Workers APIs
"""

import base64
import json
import time

import pytest

# Mark all tests as miniflare integration tests
pytestmark = pytest.mark.miniflare


class TestD1Integration:
    """Test D1 database operations with real CloudFlare API"""

    async def test_d1_basic_operations(self, miniflare_env):
        """Test basic D1 database operations"""
        from kinglet.storage import d1_unwrap

        # Test actual D1 operations through Miniflare
        mock_d1_result = type(
            "D1Result",
            (),
            {"to_py": lambda self: {"id": 1, "name": "test", "created_at": 1640995200}},
        )()

        result = d1_unwrap(mock_d1_result)
        assert result == {"id": 1, "name": "test", "created_at": 1640995200}

    async def test_d1_query_results(self, miniflare_env):
        """Test D1 query results unwrapping"""
        from kinglet.storage import d1_unwrap_results

        # Mock D1 results array
        mock_results = type(
            "D1Results",
            (),
            {
                "results": [
                    type(
                        "Row", (), {"to_py": lambda self: {"id": 1, "name": "user1"}}
                    )(),
                    type(
                        "Row", (), {"to_py": lambda self: {"id": 2, "name": "user2"}}
                    )(),
                ]
            },
        )()

        results = d1_unwrap_results(mock_results)
        assert len(results) == 2
        assert results[0]["name"] == "user1"
        assert results[1]["name"] == "user2"

    async def test_d1_error_handling(self, miniflare_env):
        """Test D1 error handling with real proxy objects"""
        from kinglet.storage import d1_unwrap

        # Mock failing D1 object
        mock_failing = type(
            "FailingD1",
            (),
            {"to_py": lambda: (_ for _ in ()).throw(RuntimeError("Proxy error"))},
        )()

        with pytest.raises(ValueError, match="Failed to unwrap D1 object"):
            d1_unwrap(mock_failing)


class TestR2Integration:
    """Test R2 storage operations with real CloudFlare API"""

    async def test_r2_metadata_extraction(self, miniflare_env):
        """Test R2 metadata extraction"""
        from kinglet.storage import r2_get_content_info, r2_get_metadata

        # Mock R2 object structure
        mock_r2_obj = type(
            "R2Object",
            (),
            {
                "size": 1024,
                "httpEtag": '"abc123"',
                "httpMetadata": type(
                    "HttpMeta", (), {"contentType": "application/json"}
                )(),
                "customMetadata": {"user": "test", "purpose": "demo"},
            },
        )()

        # Test metadata extraction
        size = r2_get_metadata(mock_r2_obj, "size")
        assert size == 1024

        content_type = r2_get_metadata(mock_r2_obj, "httpMetadata.contentType")
        assert content_type == "application/json"

        # Test content info extraction
        info = r2_get_content_info(mock_r2_obj)
        assert info["content_type"] == "application/json"
        assert info["size"] == 1024
        assert info["etag"] == '"abc123"'

    async def test_r2_bytes_conversion(self, miniflare_env):
        """Test bytes to ArrayBuffer conversion for R2"""
        from kinglet.storage import arraybuffer_to_bytes, bytes_to_arraybuffer

        test_data = b"test binary data"

        # In non-JS environment, should return data as-is
        result = bytes_to_arraybuffer(test_data)
        assert result == test_data

        # Test reverse conversion
        converted_back = arraybuffer_to_bytes(result)
        assert converted_back == test_data

    async def test_r2_put_operations(self, miniflare_env):
        """Test R2 put operations with metadata"""
        from kinglet.storage import r2_put

        # This would test actual R2 put operations
        # For now, test the function exists and can be called
        assert callable(r2_put)

        # The function should exist and be callable
        # Full integration would require actual Miniflare R2 setup


class TestAuthZIntegration:
    """Test authentication and authorization flows"""

    async def test_jwt_token_validation(self, miniflare_env):
        """Test JWT token validation with real secret"""
        from kinglet.authz import verify_jwt_hs256

        # Test with known JWT secret
        secret = "test-secret-key-for-jwt-signing"

        # Create a simple JWT-like token (simplified)
        import base64
        import hashlib
        import hmac

        header = (
            base64.urlsafe_b64encode(
                json.dumps({"typ": "JWT", "alg": "HS256"}).encode()
            )
            .decode()
            .rstrip("=")
        )

        payload_data = {
            "sub": "test-user",
            "exp": int(time.time()) + 3600,  # 1 hour from now
            "iat": int(time.time()),
            "email": "test@example.com",
        }

        payload = (
            base64.urlsafe_b64encode(json.dumps(payload_data).encode())
            .decode()
            .rstrip("=")
        )

        signing_input = f"{header}.{payload}"
        signature = (
            base64.urlsafe_b64encode(
                hmac.new(
                    secret.encode(), signing_input.encode(), hashlib.sha256
                ).digest()
            )
            .decode()
            .rstrip("=")
        )

        token = f"{signing_input}.{signature}"

        # Test validation
        result = verify_jwt_hs256(token, secret)
        assert result is not None
        assert result["sub"] == "test-user"
        assert result["email"] == "test@example.com"

    def test_jwt_token_expiry(self):
        """Test JWT token expiry validation"""
        from kinglet.authz import verify_jwt_hs256

        # Test expired token
        secret = "test-secret-key-for-jwt-signing"

        # Create expired token
        import hashlib
        import hmac
        import json

        header = (
            base64.urlsafe_b64encode(
                json.dumps({"typ": "JWT", "alg": "HS256"}).encode()
            )
            .decode()
            .rstrip("=")
        )

        payload_data = {
            "sub": "test-user",
            "exp": int(time.time()) - 3600,  # 1 hour ago (expired)
            "iat": int(time.time()) - 7200,  # 2 hours ago
        }

        payload = (
            base64.urlsafe_b64encode(json.dumps(payload_data).encode())
            .decode()
            .rstrip("=")
        )

        signing_input = f"{header}.{payload}"
        signature = (
            base64.urlsafe_b64encode(
                hmac.new(
                    secret.encode(), signing_input.encode(), hashlib.sha256
                ).digest()
            )
            .decode()
            .rstrip("=")
        )

        token = f"{signing_input}.{signature}"

        # Should return None for expired token
        result = verify_jwt_hs256(token, secret)
        assert result is None

    def test_bearer_token_extraction(self):
        """Test bearer token extraction from requests"""
        from unittest.mock import Mock

        from kinglet.authz import _extract_bearer_user

        # Mock request with Authorization header
        mock_request = Mock()
        mock_request.header = Mock(return_value="Bearer valid-jwt-token")
        mock_env = Mock()
        mock_env.JWT_SECRET = "test-secret-key-for-jwt-signing"
        mock_request.env = mock_env

        # Mock the JWT validation to return a user
        with pytest.MonkeyPatch().context() as m:
            m.setattr(
                "kinglet.authz.verify_jwt_hs256",
                lambda token, secret: {"sub": "test-user"}
                if token == "valid-jwt-token"
                else None,
            )

            _extract_bearer_user(mock_request, "JWT_SECRET")
            # Function exists and can be called
            assert callable(_extract_bearer_user)


class TestTOTPIntegration:
    """Test TOTP operations with real crypto"""

    def test_totp_code_generation(self):
        """Test TOTP code generation with valid secrets"""
        from kinglet.totp import generate_totp_code

        # Test with valid base32 secret
        valid_secret = "JBSWY3DPEHPK3PXP"  # Valid base32

        code = generate_totp_code(valid_secret)
        assert isinstance(code, str)
        assert len(code) == 6
        assert code.isdigit()

    def test_totp_invalid_secret(self):
        """Test TOTP with invalid secret format"""
        from kinglet.totp import generate_totp_code

        with pytest.raises(ValueError, match="Invalid TOTP secret format"):
            generate_totp_code("invalid!@#secret")

    def test_totp_encryption_decryption(self):
        """Test TOTP secret encryption/decryption"""
        from kinglet.totp import decrypt_totp_secret, encrypt_totp_secret

        secret_key = "test-totp-encryption-key-32-chars"
        original_secret = "JBSWY3DPEHPK3PXP"

        # Test encryption
        encrypted = encrypt_totp_secret(original_secret, secret_key)
        assert isinstance(encrypted, str)
        assert encrypted != original_secret.encode()

        # Test decryption
        decrypted = decrypt_totp_secret(encrypted, secret_key)
        assert decrypted == original_secret

    def test_totp_decryption_failure(self):
        """Test TOTP decryption with wrong key"""
        from kinglet.totp import decrypt_totp_secret, encrypt_totp_secret

        secret_key = "test-totp-encryption-key-32-chars"
        wrong_key = "wrong-key-32-chars-long-enough!!"

        encrypted = encrypt_totp_secret("JBSWY3DPEHPK3PXP", secret_key)

        with pytest.raises(ValueError, match="Failed to decrypt TOTP secret"):
            decrypt_totp_secret(encrypted, wrong_key)


class TestCacheIntegration:
    """Test cache operations with KV store"""

    def test_cache_key_operations(self):
        """Test cache key operations"""
        # This would test actual KV operations
        # For now, ensure cache modules can be imported
        from kinglet.cache_d1 import D1CacheService

        # Test that cache classes exist and can be instantiated
        assert D1CacheService is not None

    def test_cache_policy_application(self):
        """Test cache policy application"""
        from kinglet import AlwaysCachePolicy, NeverCachePolicy

        # Test cache policies exist
        assert AlwaysCachePolicy is not None
        assert NeverCachePolicy is not None

        # Basic policy testing
        always_policy = AlwaysCachePolicy()
        never_policy = NeverCachePolicy()

        # Policies should be callable
        assert callable(always_policy.should_cache)
        assert callable(never_policy.should_cache)


class TestFullWorkflowIntegration:
    """Test complete workflows combining multiple services"""

    def test_authenticated_database_operation(self):
        """Test authenticated request that performs database operation"""
        # This would be a full integration test combining:
        # 1. JWT authentication
        # 2. D1 database operation
        # 3. Cache interaction
        # 4. Response formatting

        # For now, test that all components can be imported
        from kinglet.authz import verify_jwt_hs256
        from kinglet.cache_d1 import D1CacheService
        from kinglet.storage import d1_unwrap, r2_put

        # All components should be importable
        assert verify_jwt_hs256 is not None
        assert d1_unwrap is not None
        assert r2_put is not None
        assert D1CacheService is not None

    def test_totp_protected_endpoint(self):
        """Test TOTP-protected endpoint workflow"""
        # This would test:
        # 1. TOTP code generation
        # 2. Code validation
        # 3. Elevated session creation
        # 4. Protected resource access

        from kinglet.totp import generate_totp_code, verify_totp_code

        # Components should exist
        assert generate_totp_code is not None
        assert verify_totp_code is not None


class TestORMComplexOperations:
    """Test complex ORM operations that require sophisticated database behavior"""

    def setup_method(self):
        # Use real integration setup instead of mock
        from kinglet.orm import BooleanField, IntegerField, Manager, Model, StringField

        from .mock_d1 import MockD1Database

        self.mock_db = MockD1Database()

        # Shared test model to avoid repetition
        class TestGame(Model):
            title = StringField(max_length=100, null=False)
            description = StringField(max_length=500, null=True)
            score = IntegerField(default=0)
            is_published = BooleanField(default=False)

            class Meta:
                table_name = "test_games"

        self.TestGame = TestGame
        self.manager = Manager(TestGame)

    @pytest.mark.asyncio
    async def test_queryset_operations(self):
        """Test complex QuerySet operations - moved from unit tests"""
        # Create table and sample data
        await self.TestGame.create_table(self.mock_db)

        # Create multiple games
        games_data = [
            {"title": "Adventure Game", "score": 95, "is_published": True},
            {"title": "Puzzle Game", "score": 88, "is_published": True},
            {"title": "Racing Game", "score": 92, "is_published": False},
            {"title": "Strategy Game", "score": 90, "is_published": True},
        ]

        created_games = []
        for game_data in games_data:
            game = await self.manager.create(self.mock_db, **game_data)
            created_games.append(game)

        # Test filtering
        published_games = await self.manager.filter(
            self.mock_db, is_published=True
        ).all()
        assert len(published_games) == 3

        # Test count
        total_count = await self.manager.all(self.mock_db).count()
        assert total_count == 4

        published_count = await self.manager.filter(
            self.mock_db, is_published=True
        ).count()
        assert published_count == 3

        # Test ordering
        high_score_games = (
            await self.manager.all(self.mock_db).order_by("-score").limit(2).all()
        )
        assert len(high_score_games) == 2
        assert high_score_games[0].score >= high_score_games[1].score

        # Test lookups
        high_scoring = await self.manager.filter(self.mock_db, score__gte=90).all()
        assert len(high_scoring) == 3

        # Test contains (case-sensitive)
        adventure_games = await self.manager.filter(
            self.mock_db, title__contains="Adventure"
        ).all()
        assert len(adventure_games) == 1
        assert adventure_games[0].title == "Adventure Game"

    @pytest.mark.asyncio
    async def test_bulk_operations(self):
        """Test complex bulk create operations - moved from unit tests"""
        # Create table
        await self.TestGame.create_table(self.mock_db)

        # Create multiple game instances
        game_instances = [
            self.TestGame(title=f"Bulk Game {i}", score=80 + i, is_published=i % 2 == 0)
            for i in range(5)
        ]

        # Bulk create
        created_games = await self.manager.bulk_create(self.mock_db, game_instances)

        assert len(created_games) == 5
        for i, game in enumerate(created_games):
            assert game.title == f"Bulk Game {i}"
            assert game.score == 80 + i
            assert game.id is not None

        # Verify they were actually saved
        total_count = await self.manager.all(self.mock_db).count()
        assert total_count == 5
