# TOTP and Session Elevation Guide

## Overview

Kinglet 1.4.0 introduces TOTP (Time-based One-Time Password) support for session elevation, implementing RFC 6238 for enhanced security on sensitive operations.

## Key Components

### 1. OTP Provider Pattern

Kinglet ships with pluggable OTP providers for different environments:

```python
from kinglet.totp import OTPProvider, ProductionOTPProvider, DummyOTPProvider
from kinglet.authz import configure_otp_provider

# Configure at app startup
async def on_fetch(request, env):
    configure_otp_provider(env)  # Reads TOTP_ENABLED from environment
    return await app(request, env)
```

### 2. Provider Types

#### ProductionOTPProvider (Default)
- Full RFC 6238 TOTP implementation
- 30-second time windows
- Cryptographically secure secret generation
- Compatible with Google Authenticator, Authy, etc.

#### DummyOTPProvider (Development)
- Accepts test codes: "000000", "111111", "222222", etc.
- Returns predictable test secret
- Automatically configured when `TOTP_ENABLED=false`

### 3. Environment Configuration

```toml
# wrangler.toml
[vars]
TOTP_ENABLED = "false"  # Development - uses DummyOTPProvider
JWT_SECRET = "your-jwt-secret-here"

[env.production.vars]
TOTP_ENABLED = "true"   # Production - uses ProductionOTPProvider
JWT_SECRET = "production-secret"
```

## Implementation Examples

### Basic TOTP Setup

```python
from kinglet.totp import generate_totp_secret, verify_code, generate_totp_qr_url

# 1. Generate secret for user during registration
@app.post("/auth/totp/setup")
@require_auth
async def setup_totp(request):
    user_id = request.state.user["id"]

    # Generate new TOTP secret
    secret = generate_totp_secret()

    # Store encrypted secret in database
    encrypted = encrypt_totp_secret(secret, request.env)
    await request.env.DB.prepare(
        "UPDATE users SET totp_secret = ? WHERE id = ?"
    ).bind(encrypted, user_id).run()

    # Generate QR code URL
    qr_url = generate_totp_qr_url(secret, user_email, "MyApp")

    return {
        "secret": secret,  # User should save this
        "qr_url": qr_url,  # For scanning with authenticator app
        "backup_codes": generate_backup_codes()  # Optional
    }
```

### Session Elevation

```python
from kinglet.authz import require_elevated_session, require_elevated_claim

# 2. Step-up authentication for sensitive operations
@app.post("/auth/totp/verify")
@require_auth
async def verify_totp(request):
    body = await request.json()
    code = body.get("code", "")
    user_id = request.state.user["id"]

    # Retrieve user's TOTP secret
    user = await get_user_with_totp(request.env.DB, user_id)
    if not user["totp_secret"]:
        return Response({"error": "TOTP not configured"}, status=400)

    # Decrypt and verify code
    secret = decrypt_totp_secret(user["totp_secret"], request.env)
    if not verify_code(secret, code):
        return Response({"error": "Invalid code"}, status=401)

    # Create elevated JWT
    elevated_token = create_elevated_jwt(
        user_id=user_id,
        claims=request.state.user["claims"],
        secret=request.env.JWT_SECRET
    )

    return {
        "token": elevated_token,
        "elevated": True,
        "expires_in": 900  # 15 minutes
    }
```

### Protected Endpoints

```python
# 3. Require elevation for sensitive operations
@app.post("/payment/transfer")
@require_elevated_session  # Requires TOTP verification (or skips in dev)
async def transfer_funds(request):
    # User has proven identity with TOTP
    return {"status": "transfer initiated"}

# 4. Combine elevation with business claims
@app.delete("/publisher/earnings")
@require_elevated_claim("publisher", True)  # Must be publisher AND elevated
async def withdraw_earnings(request):
    # Only verified publishers can access
    return {"withdrawn": True}
```

## Development Workflow

### Testing with DummyOTPProvider

When `TOTP_ENABLED=false`, the DummyOTPProvider accepts these test codes:

```bash
# Login first
TOKEN=$(curl -X POST http://localhost:8787/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"test"}' | jq -r '.token')

# Step-up with test code
ELEVATED=$(curl -X POST http://localhost:8787/api/auth/totp/verify \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"code":"000000"}' | jq -r '.token')

# Access protected endpoint
curl -H "Authorization: Bearer $ELEVATED" \
  http://localhost:8787/api/publisher/dashboard
```

### Custom Provider Implementation

```python
from kinglet.totp import OTPProvider, set_otp_provider

class SMSOTPProvider(OTPProvider):
    """Custom SMS-based OTP provider"""

    def generate_secret(self) -> str:
        # Generate phone-based identifier
        return f"sms:{generate_random_id()}"

    def verify_code(self, secret: str, code: str, window: int = 1) -> bool:
        # Check SMS verification service
        return check_sms_code(secret, code)

    def generate_qr_url(self, secret: str, account: str, issuer: str) -> str:
        # SMS doesn't use QR codes
        return ""

# Use custom provider
if env.USE_SMS_AUTH:
    set_otp_provider(SMSOTPProvider())
```

## Security Best Practices

### 1. Secret Storage
- Always encrypt TOTP secrets at rest
- Use environment-specific encryption keys
- Never log or expose secrets

### 2. Time Window Tolerance
- Default window is ±1 time step (±30 seconds)
- Adjust for clock skew if needed
- Rate limit verification attempts

### 3. Backup Codes
- Generate one-time backup codes
- Store hashed versions
- Allow account recovery

### 4. Session Management
- Elevated sessions should expire (15 minutes default)
- Re-verify for critical operations
- Clear elevation on logout

## Migration Guide

### From Basic Auth to TOTP

1. Add TOTP columns to user table:
```sql
ALTER TABLE users ADD COLUMN totp_secret TEXT;
ALTER TABLE users ADD COLUMN totp_enabled BOOLEAN DEFAULT false;
```

2. Update decorators:
```python
# Before
@require_auth
async def sensitive_operation(request):
    pass

# After
@require_elevated_session
async def sensitive_operation(request):
    pass
```

3. Add step-up flow to frontend:
```javascript
// Detect elevation required
if (response.status === 403 && data.code === 'ELEVATION_REQUIRED') {
    const code = await promptForTOTP();
    const elevated = await stepUpAuth(code);
    // Retry with elevated token
}
```

## Troubleshooting

### Common Issues

1. **"Invalid code" errors**
   - Check device time synchronization
   - Verify secret encoding (base32)
   - Test with wider time window

2. **Development environment issues**
   - Ensure `TOTP_ENABLED=false` in wrangler.toml
   - Check OTP provider configuration at startup
   - Use test codes: "000000", "111111", etc.

3. **JWT verification failures**
   - Verify `JWT_SECRET` is bound in environment
   - Check token expiration times
   - Ensure consistent secret between sign/verify

## API Reference

### Functions

- `generate_totp_secret()` - Create new base32 secret
- `verify_code(secret, code, window=1)` - Verify TOTP code
- `generate_totp_qr_url(secret, account, issuer)` - Create QR URL
- `create_elevated_jwt(user_id, claims, secret)` - Generate elevated token
- `encrypt_totp_secret(secret, env)` - Encrypt for storage
- `decrypt_totp_secret(encrypted, env)` - Decrypt from storage

### Decorators

- `@require_elevated_session` - Require TOTP verification
- `@require_elevated_claim(claim, value)` - Require elevation + claim
- `@require_claim(claim, value)` - Require specific claim only

### Providers

- `configure_otp_provider(env)` - Auto-configure based on environment
- `set_otp_provider(provider)` - Manually set provider
- `get_otp_provider()` - Get current provider instance
