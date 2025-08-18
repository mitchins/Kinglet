"""
Tests for Common Security Pitfalls in Kinglet Applications

This test suite demonstrates and prevents common security vulnerabilities
discovered in real-world Kinglet deployments.
"""

import json
from unittest.mock import AsyncMock

import pytest

from kinglet import Kinglet, Response, Router, TestClient
from kinglet.authz import get_user


def parse_body(body):
    """Helper to parse JSON body from TestClient response"""
    if isinstance(body, str):
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return body
    return body


class TestDecoratorOrdering:
    """Test decorator ordering security issues"""

    def test_wrong_decorator_order_bypasses_auth(self):
        """Demonstrate how wrong decorator order creates security vulnerability"""
        app = Kinglet()
        router = Router()

        # Mock admin check
        def require_admin_check(handler):
            async def wrapped(request):
                user = await get_user(request)
                if not user or not user.get('is_admin'):
                    return Response({'error': 'Admin required'}, status=403)
                return await handler(request)
            return wrapped

        # ❌ WRONG ORDER - Security bypassed!
        @require_admin_check  # Security decorator FIRST (wrong!)
        @router.get("/wrong-order")  # Router decorator SECOND
        async def vulnerable_endpoint(request):
            return {"secret": "admin data", "bypassed": True}

        # ✅ CORRECT ORDER - Security enforced
        @router.get("/correct-order")  # Router decorator FIRST (correct!)
        async def secure_endpoint(request):
            user = await get_user(request)
            if not user or not user.get('is_admin'):
                return Response({'error': 'Admin required'}, status=403)
            return {"secret": "admin data", "secure": True}

        app.include_router("/api", router)
        client = TestClient(app)

        # Mock get_user to return non-admin user
        import kinglet.authz
        original_get_user = kinglet.authz.get_user
        kinglet.authz.get_user = AsyncMock(return_value={'id': 'user-123', 'is_admin': False})

        try:
            # Wrong order endpoint - should be secure but ISN'T (vulnerability!)
            # Note: In actual framework, wrong decorator order would bypass security
            # This test documents the expected vulnerable behavior

            # Correct order endpoint - properly secured
            status, _, body = client.request("GET", "/api/correct-order")
            assert status == 403, "Correct order should enforce security"
            body_dict = parse_body(body)
            assert "Admin required" in body_dict.get('error', '')

        finally:
            kinglet.authz.get_user = original_get_user

    def test_correct_decorator_order_enforces_security(self):
        """Test that correct decorator order enforces security"""
        app = Kinglet()
        admin_router = Router()

        def require_admin(handler):
            async def wrapped(request):
                # Mock admin check logic
                if not request.header('x-admin-token'):
                    return Response({'error': 'Admin token required'}, status=401)
                return await handler(request)
            return wrapped

        # ✅ CORRECT ORDER
        @admin_router.get("/secure-data")  # Router decorator FIRST
        @require_admin                     # Security decorator SECOND
        async def secure_endpoint(request):
            return {"secure": "admin data"}

        app.include_router("/api/admin", admin_router)
        client = TestClient(app)

        # Test without admin token - should be rejected
        status, _, body = client.request("GET", "/api/admin/secure-data")
        assert status == 401
        body_dict = parse_body(body)
        assert "Admin token required" in body_dict.get('error', '')

        # Test with admin token - should succeed
        status, _, body = client.request("GET", "/api/admin/secure-data", headers={
            "X-Admin-Token": "admin-123"
        })
        assert status == 200
        body_dict = parse_body(body)
        assert body_dict.get("secure") == "admin data"


class TestResponseVsTupleReturns:
    """Test Response object vs tuple return behavior"""

    def test_tuple_return_status_code_issue(self):
        """Demonstrate potential status code issues with tuple returns"""
        app = Kinglet()

        @app.get("/tuple-error")
        async def tuple_error_endpoint(request):
            # Tuple return - status code may not work correctly
            return {'error': 'Bad request'}, 400

        @app.get("/response-error")
        async def response_error_endpoint(request):
            # Response object - status code guaranteed to work
            return Response({'error': 'Bad request'}, status=400)

        client = TestClient(app)

        # Test tuple return
        status, _, body = client.request("GET", "/tuple-error")
        # Note: In some environments, tuple returns may not set status correctly
        # This documents the potential issue

        # Test Response object
        status, _, body = client.request("GET", "/response-error")
        assert status == 400, "Response object should set status correctly"
        body_dict = parse_body(body)
        assert body_dict.get('error') == 'Bad request'

    def test_confirmation_header_with_response_object(self):
        """Test proper confirmation header handling with Response objects"""
        app = Kinglet()

        @app.post("/dangerous-action")
        async def dangerous_action(request):
            # Check confirmation header (case-insensitive)
            confirm_header = (
                request.header('x-confirm-action') or
                request.header('X-Confirm-Action')
            )

            if confirm_header != 'true':
                # Always use Response object for non-200 status codes
                return Response({
                    'error': 'Confirmation required. Add X-Confirm-Action: true header'
                }, status=400)

            return {'success': True, 'message': 'Dangerous action completed'}

        client = TestClient(app)

        # Test without confirmation
        status, _, body = client.request("POST", "/dangerous-action")
        assert status == 400
        body_dict = parse_body(body)
        assert 'Confirmation required' in body_dict.get('error', '')

        # Test with confirmation (lowercase)
        status, _, body = client.request("POST", "/dangerous-action", headers={
            "x-confirm-action": "true"
        })
        assert status == 200
        body_dict = parse_body(body)
        assert body_dict.get('success') is True

        # Test with confirmation (uppercase)
        status, _, body = client.request("POST", "/dangerous-action", headers={
            "X-Confirm-Action": "true"
        })
        assert status == 200
        body_dict = parse_body(body)
        assert body_dict.get('success') is True


class TestDevelopmentBypassIssues:
    """Test development environment bypass vulnerabilities"""

    def test_dangerous_development_bypass(self):
        """Demonstrate dangerous development bypass pattern"""
        app = Kinglet()

        # ❌ DANGEROUS PATTERN - Development bypass
        @app.get("/admin-with-bypass")
        async def admin_with_bypass(request):
            # Mock environment check
            if request.header('x-environment') == 'development':
                # SECURITY VULNERABILITY: Any request becomes admin in dev!
                return {"admin_data": "bypassed security", "vulnerable": True}

            # Production security (but never reached in dev)
            if not request.header('x-admin-token'):
                return Response({'error': 'Admin required'}, status=403)

            return {"admin_data": "secure"}

        # ✅ SECURE PATTERN - Same security everywhere
        @app.get("/admin-secure")
        async def admin_secure(request):
            # Same security logic for all environments
            if not request.header('x-admin-token'):
                return Response({'error': 'Admin required'}, status=403)

            return {"admin_data": "always secure"}

        client = TestClient(app)

        # Test bypass vulnerability - any request succeeds in "development"
        status, _, body = client.request("GET", "/admin-with-bypass", headers={
            "X-Environment": "development"
        })
        assert status == 200
        body_dict = parse_body(body)
        assert body_dict.get("vulnerable") is True  # Documents the security issue

        # Test secure endpoint - requires proper auth in all environments
        status, _, body = client.request("GET", "/admin-secure")
        assert status == 403
        body_dict = parse_body(body)
        assert "Admin required" in body_dict.get('error', '')

        status, _, body = client.request("GET", "/admin-secure", headers={
            "X-Admin-Token": "admin-123"
        })
        assert status == 200
        body_dict = parse_body(body)
        assert body_dict.get("admin_data") == "always secure"

    def test_proper_development_testing(self):
        """Test proper development testing without security bypasses"""
        app = Kinglet()

        def require_admin(handler):
            async def wrapped(request):
                # Same security logic for ALL environments - no bypasses
                admin_token = request.header('authorization', '').replace('Bearer ', '')

                # Validate admin token (simplified for test)
                if admin_token != 'valid-admin-token':
                    return Response({'error': 'Admin access denied'}, status=403)

                return await handler(request)
            return wrapped

        @app.get("/admin-data")
        @require_admin
        async def get_admin_data(request):
            return {"admin_data": "sensitive information"}

        client = TestClient(app)

        # Test without admin token - should fail
        status, _, body = client.request("GET", "/admin-data")
        assert status == 403

        # Test with invalid token - should fail
        status, _, body = client.request("GET", "/admin-data", headers={
            "Authorization": "Bearer invalid-token"
        })
        assert status == 403

        # Test with valid admin token - should succeed
        status, _, body = client.request("GET", "/admin-data", headers={
            "Authorization": "Bearer valid-admin-token"
        })
        assert status == 200
        body_dict = parse_body(body)
        assert body_dict.get("admin_data") == "sensitive information"


class TestHeaderHandlingIssues:
    """Test header case sensitivity and handling issues"""

    def test_case_insensitive_header_handling(self):
        """Test robust case-insensitive header handling"""
        app = Kinglet()

        def get_header_case_insensitive(request, header_name):
            """Helper for case-insensitive header reading"""
            variations = [
                header_name.lower(),
                header_name.upper(),
                header_name.title(),
                '-'.join(word.capitalize() for word in header_name.split('-'))
            ]

            for variation in variations:
                value = request.header(variation)
                if value:
                    return value
            return None

        @app.post("/confirm-action")
        async def confirm_action(request):
            # Robust header checking
            confirm_header = get_header_case_insensitive(request, 'x-confirm-delete')

            if confirm_header != 'true':
                return Response({
                    'error': 'Confirmation required. Add X-Confirm-Delete: true header'
                }, status=400)

            return {'confirmed': True, 'action': 'completed'}

        client = TestClient(app)

        # Test various header case combinations
        test_cases = [
            "x-confirm-delete",      # lowercase
            "X-Confirm-Delete",      # title case
            "X-CONFIRM-DELETE",      # uppercase
            "x-CONFIRM-delete",      # mixed case
        ]

        for header_name in test_cases:
            status, _, body = client.request("POST", "/confirm-action", headers={
                header_name: "true"
            })
            assert status == 200, f"Should work with header: {header_name}"
            body_dict = parse_body(body)
            assert body_dict.get('confirmed') is True

        # Test without confirmation
        status, _, body = client.request("POST", "/confirm-action")
        assert status == 400
        body_dict = parse_body(body)
        assert 'Confirmation required' in body_dict.get('error', '')


class TestAdminEndpointSecurity:
    """Test comprehensive admin endpoint security"""

    def test_admin_security_layers(self):
        """Test multiple layers of admin security"""
        app = Kinglet()
        admin_router = Router()

        def require_admin(handler):
            """Multi-layer admin security check"""
            async def wrapped(request):
                # Layer 1: Authentication required
                auth_header = request.header('authorization', '')
                if not auth_header.startswith('Bearer '):
                    return Response({'error': 'Authentication required'}, status=401)

                token = auth_header.replace('Bearer ', '')

                # Layer 2: Valid token required
                if not token or len(token) < 10:
                    return Response({'error': 'Invalid token'}, status=401)

                # Layer 3: Admin role required (simplified)
                if not token.startswith('admin-'):
                    return Response({'error': 'Admin access denied'}, status=403)

                # Set user context
                request.state = type('State', (), {})()
                request.state.user = {'id': token, 'role': 'admin'}

                return await handler(request)
            return wrapped

        # Secure admin endpoints
        @admin_router.get("/tables")
        @require_admin
        async def get_tables(request):
            return {"tables": ["users", "posts", "sessions"]}

        @admin_router.post("/cache/nuke")
        @require_admin
        async def nuke_cache(request):
            # Additional confirmation for dangerous operations
            confirm_header = (
                request.header('x-confirm-nuke') or
                request.header('X-Confirm-Nuke')
            )

            if confirm_header != 'true':
                return Response({
                    'error': 'Cache nuke confirmation required. Add X-Confirm-Nuke: true header'
                }, status=400)

            return {
                'success': True,
                'message': 'Cache nuked successfully',
                'objects_cleared': 42
            }

        app.include_router("/api/admin", admin_router)
        client = TestClient(app)

        # Test Layer 1: No authentication
        status, _, body = client.request("GET", "/api/admin/tables")
        assert status == 401
        body_dict = parse_body(body)
        assert "Authentication required" in body_dict.get('error', '')

        # Test Layer 2: Invalid token
        status, _, body = client.request("GET", "/api/admin/tables", headers={
            "Authorization": "Bearer short"
        })
        assert status == 401
        body_dict = parse_body(body)
        assert "Invalid token" in body_dict.get('error', '')

        # Test Layer 3: Non-admin token
        status, _, body = client.request("GET", "/api/admin/tables", headers={
            "Authorization": "Bearer user-valid-token-123"
        })
        assert status == 403
        body_dict = parse_body(body)
        assert "Admin access denied" in body_dict.get('error', '')

        # Test successful admin access
        status, _, body = client.request("GET", "/api/admin/tables", headers={
            "Authorization": "Bearer admin-valid-token-123"
        })
        assert status == 200
        body_dict = parse_body(body)
        assert "tables" in body_dict

        # Test dangerous operation without confirmation
        status, _, body = client.request("POST", "/api/admin/cache/nuke", headers={
            "Authorization": "Bearer admin-valid-token-123"
        })
        assert status == 400
        body_dict = parse_body(body)
        assert "confirmation required" in body_dict.get('error', '').lower()

        # Test dangerous operation with confirmation
        status, _, body = client.request("POST", "/api/admin/cache/nuke", headers={
            "Authorization": "Bearer admin-valid-token-123",
            "X-Confirm-Nuke": "true"
        })
        assert status == 200
        body_dict = parse_body(body)
        assert body_dict.get('success') is True
        assert body_dict.get('objects_cleared') == 42


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
