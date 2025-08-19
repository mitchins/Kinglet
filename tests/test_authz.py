"""
Tests for Kinglet 1.4.0 FGA (Fine-Grained Authorization) system
"""

import base64
import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from kinglet import Response
from kinglet.authz import (
    allow_public_or_owner,
    d1_load_owner_public,
    get_user,
    r2_media_owner,
    require_auth,
    require_owner,
    require_participant,
    verify_jwt_hs256,
)


class TestJWTVerification:
    """Test JWT token verification"""

    def test_valid_jwt_token(self):
        """Test valid JWT token verification"""
        # Create a valid JWT token
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "sub": "user-123",
            "exp": int(time.time()) + 3600,  # 1 hour from now
            "iat": int(time.time())
        }
        secret = "test-secret"

        # Encode header and payload
        header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip('=')
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')

        # Create signature
        signing_input = f"{header_b64}.{payload_b64}".encode()
        signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
        signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip('=')

        token = f"{header_b64}.{payload_b64}.{signature_b64}"

        # Verify token
        result = verify_jwt_hs256(token, secret)

        assert result is not None
        assert result["sub"] == "user-123"
        assert "exp" in result

    def test_expired_jwt_token(self):
        """Test expired JWT token"""
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "sub": "user-123",
            "exp": int(time.time()) - 3600,  # 1 hour ago (expired)
            "iat": int(time.time()) - 7200   # 2 hours ago
        }
        secret = "test-secret"

        # Create token (same process as above)
        header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip('=')
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        signing_input = f"{header_b64}.{payload_b64}".encode()
        signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
        signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip('=')
        token = f"{header_b64}.{payload_b64}.{signature_b64}"

        result = verify_jwt_hs256(token, secret)
        assert result is None  # Should reject expired token

    def test_invalid_signature(self):
        """Test JWT with invalid signature"""
        token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyLTEyMyIsImV4cCI6OTk5OTk5OTk5OX0.invalid-signature"
        result = verify_jwt_hs256(token, "test-secret")
        assert result is None

    def test_malformed_token(self):
        """Test malformed JWT token"""
        result = verify_jwt_hs256("not.a.valid.jwt.token", "test-secret")
        assert result is None


class TestGetUser:
    """Test user extraction from requests"""

    @pytest.mark.asyncio
    async def test_get_user_bearer_token(self):
        """Test extracting user from Bearer token"""
        # Mock request with valid Bearer token
        mock_request = MagicMock()
        mock_request.header = MagicMock(return_value="Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyLTEyMyIsImV4cCI6OTk5OTk5OTk5OX0.test-signature")
        mock_request.env.JWT_SECRET = "test-secret"

        # Mock successful JWT verification
        import kinglet.authz
        original_verify = kinglet.authz.verify_jwt_hs256
        kinglet.authz.verify_jwt_hs256 = lambda token, secret: {"sub": "user-123", "email": "test@example.com"}

        try:
            result = await get_user(mock_request)
            assert result is not None
            assert result["id"] == "user-123"
            assert result["claims"]["email"] == "test@example.com"
        finally:
            kinglet.authz.verify_jwt_hs256 = original_verify

    @pytest.mark.asyncio
    async def test_get_user_no_auth(self):
        """Test request without authentication"""
        mock_request = MagicMock()
        mock_request.header = MagicMock(return_value="")

        result = await get_user(mock_request)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_user_cf_access_header(self):
        """Test extracting user from Cloudflare Access JWT"""
        mock_request = MagicMock()
        mock_request.header = MagicMock(side_effect=lambda header, default="": {
            "authorization": "",
            "cf-access-jwt-assertion": "header.eyJzdWIiOiJ1c2VyLWNmLTEyMyIsImVtYWlsIjoidGVzdEBleGFtcGxlLmNvbSJ9.signature"
        }.get(header.lower(), default))

        result = await get_user(mock_request)
        assert result is not None
        assert result["id"] == "user-cf-123"


class TestD1Resolver:
    """Test D1 database owner resolver"""

    @pytest.mark.asyncio
    async def test_d1_load_owner_public_found(self):
        """Test loading owner/public status from D1"""
        # Mock D1 database
        mock_d1 = AsyncMock()
        mock_result = AsyncMock()
        mock_result.first = AsyncMock(return_value={
            "owner_id": "user-owner-123",
            "public": 1
        })
        mock_d1.prepare = MagicMock(return_value=mock_result)
        mock_result.bind = MagicMock(return_value=mock_result)

        result = await d1_load_owner_public(mock_d1, "listings", "listing-123")

        assert result is not None
        assert result["owner_id"] == "user-owner-123"
        assert result["public"] is True

        # Verify correct SQL was called
        mock_d1.prepare.assert_called_once_with("SELECT owner_id, public FROM listings WHERE id=? LIMIT 1")
        mock_result.bind.assert_called_once_with("listing-123")

    @pytest.mark.asyncio
    async def test_d1_load_owner_public_not_found(self):
        """Test loading non-existent resource"""
        mock_d1 = AsyncMock()
        mock_result = AsyncMock()
        mock_result.first = AsyncMock(return_value=None)
        mock_d1.prepare = MagicMock(return_value=mock_result)
        mock_result.bind = MagicMock(return_value=mock_result)

        result = await d1_load_owner_public(mock_d1, "listings", "nonexistent")
        assert result is None


class TestR2MediaResolver:
    """Test R2 media owner resolver"""

    @pytest.mark.asyncio
    async def test_r2_media_owner_found(self):
        """Test loading media owner from R2 metadata"""
        # Mock R2 bucket and response
        mock_env = MagicMock()
        mock_bucket = AsyncMock()
        mock_env.STORAGE = mock_bucket

        mock_head_result = MagicMock()
        mock_head_result.customMetadata = {"owner_id": "user-media-123"}
        mock_bucket.head = AsyncMock(return_value=mock_head_result)

        result = await r2_media_owner(mock_env, "STORAGE", "media-uid-123")

        assert result is not None
        assert result["owner_id"] == "user-media-123"
        assert result["public"] is False  # Default for R2 media

        mock_bucket.head.assert_called_once_with("media-uid-123")

    @pytest.mark.asyncio
    async def test_r2_media_owner_not_found(self):
        """Test loading non-existent media"""
        mock_env = MagicMock()
        mock_bucket = AsyncMock()
        mock_env.STORAGE = mock_bucket
        mock_bucket.head = AsyncMock(return_value=None)

        result = await r2_media_owner(mock_env, "STORAGE", "nonexistent")
        assert result is None


class TestRequireAuthDecorator:
    """Test @require_auth decorator"""

    @pytest.mark.asyncio
    async def test_require_auth_success(self):
        """Test successful authentication"""
        @require_auth
        async def protected_handler(req):
            return {"message": f"Hello {req.state.user['id']}"}

        # Mock authenticated request
        mock_request = MagicMock()

        # Mock get_user to return authenticated user
        import kinglet.authz
        original_get_user = kinglet.authz.get_user
        kinglet.authz.get_user = AsyncMock(return_value={"id": "user-123", "claims": {}})

        try:
            result = await protected_handler(mock_request)
            assert result["message"] == "Hello user-123"
            assert hasattr(mock_request.state, "user")
            assert mock_request.state.user["id"] == "user-123"
        finally:
            kinglet.authz.get_user = original_get_user

    @pytest.mark.asyncio
    async def test_require_auth_unauthorized(self):
        """Test unauthorized request"""
        @require_auth
        async def protected_handler(req):
            return {"message": "Should not reach here"}

        mock_request = MagicMock()

        # Mock get_user to return None (no auth)
        import kinglet.authz
        original_get_user = kinglet.authz.get_user
        kinglet.authz.get_user = AsyncMock(return_value=None)

        try:
            result = await protected_handler(mock_request)
            assert isinstance(result, Response)
            assert result.status == 401
            assert "unauthorized" in result.content["error"]
        finally:
            kinglet.authz.get_user = original_get_user


class TestAllowPublicOrOwnerDecorator:
    """Test @allow_public_or_owner decorator"""

    @pytest.mark.asyncio
    async def test_public_resource_access(self):
        """Test accessing public resource without authentication"""
        async def load_resource(req, rid):
            return {"owner_id": "owner-123", "public": True}

        @allow_public_or_owner(load_resource)
        async def handler(req, obj):
            return {"resource_id": req.path_param("id"), "public": obj["public"]}

        mock_request = MagicMock()
        mock_request.path_param = MagicMock(return_value="resource-123")

        # Mock get_user to return None (no auth)
        import kinglet.authz
        original_get_user = kinglet.authz.get_user
        kinglet.authz.get_user = AsyncMock(return_value=None)

        try:
            result = await handler(mock_request)
            assert result["resource_id"] == "resource-123"
            assert result["public"] is True
        finally:
            kinglet.authz.get_user = original_get_user

    @pytest.mark.asyncio
    async def test_private_resource_owner_access(self):
        """Test accessing private resource as owner"""
        async def load_resource(req, rid):
            return {"owner_id": "owner-123", "public": False}

        @allow_public_or_owner(load_resource)
        async def handler(req, obj):
            return {"resource_id": req.path_param("id"), "owner_access": True}

        mock_request = MagicMock()
        mock_request.path_param = MagicMock(return_value="resource-123")

        # Mock get_user to return owner
        import kinglet.authz
        original_get_user = kinglet.authz.get_user
        kinglet.authz.get_user = AsyncMock(return_value={"id": "owner-123", "claims": {}})

        try:
            result = await handler(mock_request)
            assert result["resource_id"] == "resource-123"
            assert result["owner_access"] is True
            assert hasattr(mock_request.state, "user")
        finally:
            kinglet.authz.get_user = original_get_user

    @pytest.mark.asyncio
    async def test_private_resource_forbidden(self):
        """Test accessing private resource as non-owner"""
        async def load_resource(req, rid):
            return {"owner_id": "owner-123", "public": False}

        @allow_public_or_owner(load_resource, forbidden_as_404=True)
        async def handler(req, obj):
            return {"should": "not reach here"}

        mock_request = MagicMock()
        mock_request.path_param = MagicMock(return_value="resource-123")

        # Mock get_user to return different user
        import kinglet.authz
        original_get_user = kinglet.authz.get_user
        kinglet.authz.get_user = AsyncMock(return_value={"id": "other-user", "claims": {}})

        try:
            result = await handler(mock_request)
            assert isinstance(result, Response)
            assert result.status == 404  # forbidden_as_404=True
        finally:
            kinglet.authz.get_user = original_get_user


class TestRequireOwnerDecorator:
    """Test @require_owner decorator"""

    @pytest.mark.asyncio
    async def test_owner_access(self):
        """Test successful owner access"""
        async def load_resource(req, rid):
            return {"owner_id": "owner-123"}

        @require_owner(load_resource)
        async def handler(req, obj):
            return {"message": "Owner access granted", "resource": obj}

        mock_request = MagicMock()
        mock_request.path_param = MagicMock(return_value="resource-123")

        # Mock get_user to return owner
        import kinglet.authz
        original_get_user = kinglet.authz.get_user
        kinglet.authz.get_user = AsyncMock(return_value={"id": "owner-123", "claims": {}})

        try:
            result = await handler(mock_request)
            assert result["message"] == "Owner access granted"
            assert result["resource"]["owner_id"] == "owner-123"
        finally:
            kinglet.authz.get_user = original_get_user

    @pytest.mark.asyncio
    async def test_admin_override(self):
        """Test admin override for owner-only resource"""
        async def load_resource(req, rid):
            return {"owner_id": "owner-123"}

        @require_owner(load_resource, allow_admin_env="TEST_ADMIN_IDS")
        async def handler(req, obj):
            return {"admin_access": True}

        mock_request = MagicMock()
        mock_request.path_param = MagicMock(return_value="resource-123")
        mock_request.env.TEST_ADMIN_IDS = "admin-1,admin-2,admin-3"

        # Mock get_user to return admin user
        import kinglet.authz
        original_get_user = kinglet.authz.get_user
        kinglet.authz.get_user = AsyncMock(return_value={"id": "admin-2", "claims": {}})

        try:
            result = await handler(mock_request)
            assert result["admin_access"] is True
        finally:
            kinglet.authz.get_user = original_get_user


class TestRequireParticipantDecorator:
    """Test @require_participant decorator"""

    @pytest.mark.asyncio
    async def test_participant_access(self):
        """Test successful participant access"""
        async def load_participants(req, _conversation_id):
            return {"user-1", "user-2", "user-3"}

        @require_participant(load_participants)
        async def handler(req):
            return {"conversation_access": True, "user": req.state.user["id"]}

        mock_request = MagicMock()
        mock_request.path_param = MagicMock(return_value="conversation-123")

        # Mock get_user to return participant
        import kinglet.authz
        original_get_user = kinglet.authz.get_user
        kinglet.authz.get_user = AsyncMock(return_value={"id": "user-2", "claims": {}})

        try:
            result = await handler(mock_request)
            assert result["conversation_access"] is True
            assert result["user"] == "user-2"
        finally:
            kinglet.authz.get_user = original_get_user

    @pytest.mark.asyncio
    async def test_non_participant_forbidden(self):
        """Test non-participant access denied"""
        async def load_participants(req, _conversation_id):
            return {"user-1", "user-2", "user-3"}

        @require_participant(load_participants)
        async def handler(req):
            return {"should": "not reach here"}

        mock_request = MagicMock()
        mock_request.path_param = MagicMock(return_value="conversation-123")
        mock_request.env.ADMIN_IDS = ""  # No admin override

        # Mock get_user to return non-participant
        import kinglet.authz
        original_get_user = kinglet.authz.get_user
        kinglet.authz.get_user = AsyncMock(return_value={"id": "outsider-user", "claims": {}})

        try:
            result = await handler(mock_request)
            assert isinstance(result, Response)
            assert result.status == 403
        finally:
            kinglet.authz.get_user = original_get_user


# Integration test showing complete FGA flow
class TestFGAIntegration:
    """Integration tests for complete FGA flow"""

    @pytest.mark.asyncio
    async def test_listing_access_flow(self):
        """Test complete listing access control flow"""

        # Mock listing data
        async def load_listing(req, listing_id):
            listings = {
                "public-listing": {"owner_id": "owner-1", "public": True},
                "private-listing": {"owner_id": "owner-2", "public": False},
            }
            return listings.get(listing_id)

        @allow_public_or_owner(load_listing, forbidden_as_404=True)
        async def get_listing(req, obj):
            return {
                "id": req.path_param("listing_id"),
                "owner_id": obj["owner_id"],
                "public": obj["public"],
                "viewer": getattr(req.state, "user", {}).get("id", "anonymous")
            }

        # Test 1: Anonymous user accessing public listing
        mock_request = MagicMock()
        mock_request.path_param = MagicMock(return_value="public-listing")
        mock_request.state = MagicMock()
        mock_request.state.user = {}  # Empty dict for anonymous

        import kinglet.authz
        original_get_user = kinglet.authz.get_user
        kinglet.authz.get_user = AsyncMock(return_value=None)

        try:
            result = await get_listing(mock_request)
            assert result["id"] == "public-listing"
            assert result["public"] is True
            assert result["viewer"] == "anonymous"

            # Test 2: Owner accessing private listing
            mock_request.path_param = MagicMock(return_value="private-listing")
            kinglet.authz.get_user = AsyncMock(return_value={"id": "owner-2", "claims": {}})

            result = await get_listing(mock_request)
            assert result["id"] == "private-listing"
            assert result["public"] is False
            assert result["viewer"] == "owner-2"

            # Test 3: Non-owner trying to access private listing
            kinglet.authz.get_user = AsyncMock(return_value={"id": "other-user", "claims": {}})

            result = await get_listing(mock_request)
            assert isinstance(result, Response)
            assert result.status == 404  # Hidden from non-owner

        finally:
            kinglet.authz.get_user = original_get_user


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
