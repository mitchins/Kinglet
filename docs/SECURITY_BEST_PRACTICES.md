# Security Best Practices for Kinglet

This guide documents critical security patterns learned from real-world production deployments, including common pitfalls that can lead to security vulnerabilities.

## Table of Contents

- [Decorator Ordering Critical Issues](#decorator-ordering-critical-issues)
- [Response Objects vs Tuple Returns](#response-objects-vs-tuple-returns)
- [Development Environment Security Bypasses](#development-environment-security-bypasses)
- [Header Handling Best Practices](#header-handling-best-practices)
- [Admin Endpoint Security](#admin-endpoint-security)
- [Testing Security Controls](#testing-security-controls)

## Decorator Ordering Critical Issues

### ❌ WRONG - Security Bypass
```python
# SECURITY VULNERABILITY: Authentication bypassed!
@require_admin
@admin_router.get("/sensitive-data")
async def get_sensitive_data(request):
    return {"secret": "admin only data"}
```

### ✅ CORRECT - Proper Security
```python
# Router decorator MUST come first, then security decorators
@admin_router.get("/sensitive-data")  # ← Router decorator FIRST
@require_admin                        # ← Security decorator SECOND  
async def get_sensitive_data(request):
    return {"secret": "admin only data"}
```

### Why This Matters
**Router decorators must be applied BEFORE security decorators.** When decorators are applied in the wrong order:

1. The security decorator wraps the function first
2. The router decorator then wraps the security decorator  
3. The router bypasses authentication and calls the original function directly
4. **Result: Complete authentication bypass**

### Testing for Decorator Order Issues
```python
def test_admin_access_control():
    """Test that admin endpoints reject non-admin users"""
    client = TestClient(app)
    
    # Test unauthenticated access
    status, _, _ = client.request("GET", "/api/admin/sensitive-data")
    assert status == 401  # Should reject, not 200!
    
    # Test non-admin authenticated access
    status, _, _ = client.request("GET", "/api/admin/sensitive-data", headers={
        "Authorization": "Bearer non-admin-token"
    })
    assert status == 403  # Should reject, not 200!
```

## Response Objects vs Tuple Returns

### ❌ WRONG - Status Code Ignored
```python
@admin_router.post("/dangerous-action")
@require_admin
async def dangerous_action(request):
    if not request.header('x-confirm-action'):
        # Status code 400 will NOT be returned!
        return {'error': 'Confirmation required'}, 400
```

### ✅ CORRECT - Proper Status Codes  
```python
from kinglet import Response

@admin_router.post("/dangerous-action")
@require_admin
async def dangerous_action(request):
    if not request.header('x-confirm-action'):
        # Status code 400 WILL be returned correctly
        return Response({'error': 'Confirmation required'}, status=400)
```

### Why This Matters
**Tuple returns `(dict, status_code)` may not set HTTP status codes correctly in all environments.** This can lead to:

1. Error responses returning 200 OK instead of proper error codes
2. Security middleware not triggering on error conditions
3. Client-side error handling breaking unexpectedly

### Always Use Response Objects for Non-200 Status Codes
```python
# For success responses, plain dict is fine
return {"success": True, "data": result}

# For error responses, always use Response objects  
return Response({"error": "Not found"}, status=404)
return Response({"error": "Forbidden"}, status=403)  
return Response({"error": "Bad request"}, status=400)
```

## Development Environment Security Bypasses

### ❌ DANGEROUS - Development Bypass
```python
def require_admin(handler):
    async def wrapped(request):
        user = await get_user(request)
        if not user:
            return Response({'error': 'Admin access requires authentication'}, status=401)
        
        # SECURITY VULNERABILITY: Any authenticated user becomes admin in dev!
        if request.env.get('ENVIRONMENT') == 'development':
            return await handler(request)  # ← DANGEROUS BYPASS
            
        # Production security check
        if not user.get('is_admin'):
            return Response({'error': 'Admin access denied'}, status=403)
        
        return await handler(request)
    return wrapped
```

### ✅ SECURE - Proper Development Handling
```python  
def require_admin(handler):
    async def wrapped(request):
        user = await get_user(request)
        if not user:
            return Response({'error': 'Admin access requires authentication'}, status=401)
        
        # Check admin role from JWT claims - SAME logic for dev and production
        claims = user.get('claims', {})
        is_admin = (
            claims.get('role') == 'admin' or 
            claims.get('is_publisher') is True
        )
        
        if not is_admin:
            return Response({'error': 'Admin access denied'}, status=403)
        
        return await handler(request)
    return wrapped
```

### Why Development Bypasses Are Dangerous

1. **Security logic differs between environments** - Creates false confidence
2. **Easy to deploy to production** - Copy/paste can leak bypasses  
3. **Hard to catch in testing** - Tests may only run in development mode
4. **Privilege escalation attacks** - Any authenticated user becomes admin

### Alternative: Dedicated Development Admin Accounts
```python
# Create proper admin accounts for development/testing
await create_dev_admin_user(
    username="dev-admin",
    password="secure-dev-password",
    role="admin"
)

# Test with proper authentication - no bypasses needed
def test_admin_access():
    # Login as development admin user (proper auth flow)
    admin_token = login_as_admin("dev-admin", "secure-dev-password")
    
    # Test admin endpoints with real authentication
    status, _, body = client.request("GET", "/admin/data", headers={
        "Authorization": f"Bearer {admin_token}"
    })
    assert status == 200
```

## Header Handling Best Practices

### ❌ PROBLEMATIC - Case Sensitivity Issues
```python
@admin_router.post("/cache/nuke")
@require_admin
async def nuke_cache(request):
    # Only checks lowercase - may miss X-Confirm-Nuke
    if request.header('x-confirm-nuke') != 'true':
        return Response({'error': 'Confirmation required'}, status=400)
```

### ✅ ROBUST - Case-Insensitive Headers
```python
@admin_router.post("/cache/nuke")
@require_admin  
async def nuke_cache(request):
    # Check both common case variations
    confirm_header = (
        request.header('x-confirm-nuke') or 
        request.header('X-Confirm-Nuke')
    )
    
    if confirm_header != 'true':
        return Response({'error': 'Confirmation required'}, status=400)
```

### Why Header Case Matters
- **HTTP headers are case-insensitive** but implementations vary
- **Client libraries may canonicalize** headers differently  
- **Proxy/CDN layers** may modify header casing
- **Mobile vs desktop clients** may send different cases

### Defensive Header Reading Pattern
```python
def get_header_case_insensitive(request, header_name):
    """Get header value checking multiple case variations"""
    variations = [
        header_name.lower(),                    # x-confirm-action
        header_name.upper(),                    # X-CONFIRM-ACTION  
        header_name.title(),                    # X-Confirm-Action
        '-'.join(word.capitalize() for word in header_name.split('-'))  # X-Confirm-Action
    ]
    
    for variation in variations:
        value = request.header(variation)
        if value:
            return value
    return None

# Usage
confirm_header = get_header_case_insensitive(request, 'x-confirm-nuke')
```

## Admin Endpoint Security

### Complete Admin Security Checklist

```python
from kinglet import Router, Response
from kinglet.authz import require_auth, get_user

admin_router = Router()

def require_admin(handler):
    """Proper admin access control with comprehensive checks"""
    async def wrapped(request):
        # 1. Require authentication first
        user = await get_user(request)
        if not user:
            return Response({'error': 'Admin access requires authentication'}, status=401)
        
        # 2. Check admin claims (NO development bypasses)
        claims = user.get('claims', {})
        is_admin = (
            claims.get('role') == 'admin' or 
            claims.get('is_publisher') is True
        )
        
        if not is_admin:
            return Response({'error': 'Admin access denied'}, status=403)
        
        # 3. Set user in request state for handler access
        request.state = getattr(request, "state", type("S", (), {})())
        request.state.user = user
        
        return await handler(request)
    
    return wrapped

# ✅ CORRECT: Router decorator first, then auth
@admin_router.get("/tables")
@require_admin
async def get_tables(request):
    """Admin-only endpoint with proper security"""
    return {"tables": ["users", "games", "transactions"]}

# ✅ CORRECT: Dangerous operations require confirmation
@admin_router.post("/cache/nuke")
@require_admin  
async def nuke_cache(request):
    """Nuclear cache clear with proper confirmation"""
    
    # Check confirmation header (case-insensitive)
    confirm_header = (
        request.header('x-confirm-nuke') or 
        request.header('X-Confirm-Nuke')
    )
    
    if confirm_header != 'true':
        return Response({
            'error': 'Cache nuke confirmation required. Add X-Confirm-Nuke: true header'
        }, status=400)
    
    # Perform dangerous operation
    cleared_count = await clear_all_cache(request.env.STORAGE)
    
    return Response({
        'success': True,
        'cleared_objects': cleared_count,
        'message': 'Cache successfully nuked'
    })

# ✅ CORRECT: Include admin router in main app
app.include_router("/api/admin", admin_router)
```

## Testing Security Controls

### Comprehensive Admin Security Test Suite

```python
import pytest
from kinglet import TestClient

class TestAdminSecurity:
    """Test admin endpoint security controls"""
    
    def test_unauthenticated_admin_access(self):
        """Admin endpoints must reject unauthenticated requests"""
        client = TestClient(app)
        
        admin_endpoints = [
            "/api/admin/tables",
            "/api/admin/cache/nuke", 
            "/api/admin/users"
        ]
        
        for endpoint in admin_endpoints:
            status, _, _ = client.request("GET", endpoint)
            assert status == 401, f"{endpoint} should reject unauthenticated (401)"
    
    def test_non_admin_authenticated_access(self):
        """Admin endpoints must reject non-admin authenticated users"""
        client = TestClient(app)
        
        # Get regular user token
        regular_token = get_regular_user_token()
        
        admin_endpoints = [
            "/api/admin/tables",
            "/api/admin/cache/info"
        ]
        
        for endpoint in admin_endpoints:
            status, _, _ = client.request("GET", endpoint, headers={
                "Authorization": f"Bearer {regular_token}"
            })
            assert status == 403, f"{endpoint} should reject non-admin (403)"
    
    def test_admin_authenticated_access(self):
        """Admin endpoints must allow admin authenticated users"""
        client = TestClient(app)
        
        # Get admin user token  
        admin_token = get_admin_user_token()
        
        admin_endpoints = [
            "/api/admin/tables",
            "/api/admin/cache/info"
        ]
        
        for endpoint in admin_endpoints:
            status, _, _ = client.request("GET", endpoint, headers={
                "Authorization": f"Bearer {admin_token}"
            })
            assert status == 200, f"{endpoint} should allow admin (200)"
    
    def test_dangerous_operation_confirmation(self):
        """Dangerous operations must require confirmation headers"""
        client = TestClient(app)
        admin_token = get_admin_user_token()
        
        # Test without confirmation header
        status, _, body = client.request("POST", "/api/admin/cache/nuke", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert status == 400, "Should require confirmation header"
        assert "confirmation" in body.get("error", "").lower()
        
        # Test with confirmation header  
        status, _, body = client.request("POST", "/api/admin/cache/nuke", headers={
            "Authorization": f"Bearer {admin_token}",
            "X-Confirm-Nuke": "true"
        })
        assert status == 200, "Should succeed with confirmation"
        assert body.get("success") is True

def get_admin_user_token():
    """Helper to get admin JWT token for testing"""
    # Create proper admin test user - NO shortcuts or bypasses
    client = TestClient(app)
    
    # Register admin user
    client.request("POST", "/api/auth/register", json={
        "username": "test-admin",
        "email": "admin@test.com", 
        "password": "SecureAdminPass123!",
        "role": "admin"  # Set admin role properly
    })
    
    # Login and get token
    status, _, body = client.request("POST", "/api/auth/login", json={
        "username": "test-admin",
        "password": "SecureAdminPass123!"
    })
    
    assert status == 200, "Admin login should succeed"
    return body["token"]

def get_regular_user_token():
    """Helper to get regular user JWT token for testing"""
    client = TestClient(app)
    
    # Register regular user
    client.request("POST", "/api/auth/register", json={
        "username": "test-user",
        "email": "user@test.com",
        "password": "RegularUserPass123!",
        "role": "customer"  # Regular user role
    })
    
    # Login and get token
    status, _, body = client.request("POST", "/api/auth/login", json={
        "username": "test-user", 
        "password": "RegularUserPass123!"
    })
    
    assert status == 200, "Regular login should succeed"
    return body["token"]
```

## Key Security Takeaways

1. **Decorator order is critical** - Router decorators BEFORE security decorators
2. **Use Response objects** - For proper HTTP status codes
3. **No development bypasses** - Same security logic everywhere  
4. **Case-insensitive headers** - Check multiple variations
5. **Test negative cases** - Ensure unauthorized access fails
6. **Dangerous operations need confirmation** - Extra headers/params for destructive actions
7. **Proper test admin accounts** - No shortcuts in testing

Following these patterns prevents common security vulnerabilities that can lead to privilege escalation, authentication bypasses, and unauthorized access to sensitive endpoints.