"""
TOTP Authentication Example
Demonstrates session elevation with TOTP in Kinglet
"""

from kinglet import Kinglet, Response
from kinglet.authz import (
    configure_otp_provider,
    require_auth,
    require_elevated_claim,
    require_elevated_session,
)
from kinglet.totp import (
    create_elevated_jwt,
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_totp_qr_url,
    generate_totp_secret,
    verify_code,
)

app = Kinglet(debug=True)

# ============================================
# CONFIGURATION
# ============================================


async def on_fetch(request, env):
    """Cloudflare Workers entry point"""
    # Configure OTP provider based on TOTP_ENABLED environment variable
    # Development: TOTP_ENABLED=false uses DummyOTPProvider (accepts "000000")
    # Production: TOTP_ENABLED=true uses ProductionOTPProvider (real TOTP)
    configure_otp_provider(env)
    return await app(request, env)


# ============================================
# TOTP SETUP ENDPOINTS
# ============================================


@app.post("/auth/totp/setup")
@require_auth
async def setup_totp(request):
    """
    Enable TOTP for the current user
    Returns secret and QR code for authenticator apps
    """
    user = request.state.user
    user_id = user["id"]

    # Generate new TOTP secret
    secret = generate_totp_secret()

    # Encrypt secret for storage
    encrypted_secret = encrypt_totp_secret(secret, request.env)

    # Store in database
    await (
        request.env.DB.prepare("""
        UPDATE users
        SET totp_secret = ?, totp_enabled = true, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """)
        .bind(encrypted_secret, user_id)
        .run()
    )

    # Generate QR code URL for scanning
    email = user["claims"].get("email", f"user_{user_id}")
    qr_url = generate_totp_qr_url(secret, email, "MyApp")

    return {
        "success": True,
        "secret": secret,  # User should save this securely
        "qr_url": qr_url,  # For authenticator app scanning
        "instructions": [
            "1. Install an authenticator app (Google Authenticator, Authy, etc.)",
            "2. Scan the QR code or manually enter the secret",
            "3. Enter the 6-digit code to verify setup",
        ],
    }


@app.post("/auth/totp/verify-setup")
@require_auth
async def verify_totp_setup(request):
    """
    Verify TOTP setup by validating first code
    Confirms the user has successfully configured their authenticator
    """
    body = await request.json()
    code = body.get("code", "").strip()

    if not code:
        return Response({"error": "Code required"}, status=400)

    user_id = request.state.user["id"]

    # Get user's encrypted TOTP secret
    result = (
        await request.env.DB.prepare("SELECT totp_secret FROM users WHERE id = ?")
        .bind(user_id)
        .first()
    )

    if not result or not result["totp_secret"]:
        return Response({"error": "TOTP not configured"}, status=400)

    # Decrypt and verify
    secret = decrypt_totp_secret(result["totp_secret"], request.env)

    if not verify_code(secret, code):
        return Response({"error": "Invalid code"}, status=401)

    # Mark TOTP as verified
    await (
        request.env.DB.prepare("""
        UPDATE users
        SET totp_verified = true, totp_verified_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """)
        .bind(user_id)
        .run()
    )

    return {"success": True, "message": "TOTP successfully configured and verified"}


# ============================================
# SESSION ELEVATION ENDPOINTS
# ============================================


@app.post("/auth/totp/step-up")
@require_auth
async def step_up_authentication(request):
    """
    Elevate session with TOTP verification
    Required for sensitive operations like payments, account changes, etc.
    """
    body = await request.json()
    code = body.get("code", "").strip()

    if not code:
        return Response({"error": "Code required"}, status=400)

    user = request.state.user
    user_id = user["id"]

    # Get user's TOTP configuration
    result = (
        await request.env.DB.prepare(
            "SELECT totp_secret, totp_enabled FROM users WHERE id = ?"
        )
        .bind(user_id)
        .first()
    )

    if not result or not result["totp_enabled"]:
        return Response(
            {"error": "TOTP not enabled", "setup_url": "/auth/totp/setup"}, status=400
        )

    # Verify TOTP code
    secret = decrypt_totp_secret(result["totp_secret"], request.env)

    if not verify_code(secret, code):
        # Log failed attempt for security monitoring
        await (
            request.env.DB.prepare("""
            INSERT INTO auth_logs (user_id, action, success, ip_address)
            VALUES (?, 'totp_verify', false, ?)
        """)
            .bind(user_id, request.cf.ip)
            .run()
        )

        return Response({"error": "Invalid code"}, status=401)

    # Create elevated JWT with additional claims
    elevated_token = create_elevated_jwt(
        user_id=user_id,
        claims={**user["claims"], "elevated": True, "elevation_time": int(time.time())},
        secret=request.env.JWT_SECRET,
        expires_in=900,  # 15 minutes
    )

    # Log successful elevation
    await (
        request.env.DB.prepare("""
        INSERT INTO auth_logs (user_id, action, success, ip_address)
        VALUES (?, 'totp_verify', true, ?)
    """)
        .bind(user_id, request.cf.ip)
        .run()
    )

    return {
        "success": True,
        "token": elevated_token,
        "elevated": True,
        "expires_in": 900,
        "message": "Session elevated for 15 minutes",
    }


# ============================================
# PROTECTED ENDPOINTS REQUIRING ELEVATION
# ============================================


@app.post("/account/delete")
@require_elevated_session  # Requires TOTP verification
async def delete_account(request):
    """
    Permanently delete user account
    Requires elevated session (TOTP verification)
    """
    user_id = request.state.user["id"]

    # Perform account deletion
    await (
        request.env.DB.prepare(
            "UPDATE users SET deleted = true, deleted_at = CURRENT_TIMESTAMP WHERE id = ?"
        )
        .bind(user_id)
        .run()
    )

    return {"success": True, "message": "Account scheduled for deletion"}


@app.post("/payment/withdraw")
@require_elevated_session
async def withdraw_funds(request):
    """
    Withdraw account balance
    Requires elevated session for security
    """
    body = await request.json()
    amount = body.get("amount", 0)
    destination = body.get("destination", "")

    if amount <= 0:
        return Response({"error": "Invalid amount"}, status=400)

    user_id = request.state.user["id"]

    # Process withdrawal (simplified)
    await (
        request.env.DB.prepare("""
        INSERT INTO withdrawals (user_id, amount, destination, status)
        VALUES (?, ?, ?, 'pending')
    """)
        .bind(user_id, amount, destination)
        .run()
    )

    return {"success": True, "withdrawal_id": generate_id(), "status": "pending"}


@app.put("/publisher/payout-settings")
@require_elevated_claim("publisher", True)  # Must be publisher AND elevated
async def update_payout_settings(request):
    """
    Update publisher payout configuration
    Requires:
    1. Publisher claim in JWT
    2. Elevated session (TOTP verified)
    """
    body = await request.json()
    user_id = request.state.user["id"]

    # Update payout settings
    await (
        request.env.DB.prepare("""
        UPDATE publisher_settings
        SET payout_method = ?, payout_details = ?, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
    """)
        .bind(body.get("method"), body.get("details"), user_id)
        .run()
    )

    return {"success": True, "message": "Payout settings updated"}


# ============================================
# ADMIN ENDPOINTS
# ============================================


@app.post("/admin/disable-totp/{user_id}")
@require_elevated_claim("admin", True)
async def admin_disable_totp(request):
    """
    Admin endpoint to disable TOTP for a user
    Used for support cases when user loses authenticator
    """
    target_user_id = request.path_param("user_id")
    admin_id = request.state.user["id"]

    # Disable TOTP for target user
    await (
        request.env.DB.prepare("""
        UPDATE users
        SET totp_secret = NULL, totp_enabled = false, totp_verified = false
        WHERE id = ?
    """)
        .bind(target_user_id)
        .run()
    )

    # Log admin action
    await (
        request.env.DB.prepare("""
        INSERT INTO admin_logs (admin_id, action, target_user_id, details)
        VALUES (?, 'disable_totp', ?, 'Support request')
    """)
        .bind(admin_id, target_user_id)
        .run()
    )

    return {"success": True, "message": f"TOTP disabled for user {target_user_id}"}


# ============================================
# DEVELOPMENT HELPERS
# ============================================


@app.get("/auth/totp/test-info")
async def get_test_info(request):
    """
    Development endpoint showing TOTP configuration
    Only available when TOTP_ENABLED=false
    """
    totp_enabled = getattr(request.env, "TOTP_ENABLED", "true").lower() == "true"

    if totp_enabled:
        return Response({"error": "Not available in production"}, status=403)

    return {
        "environment": getattr(request.env, "ENVIRONMENT", "unknown"),
        "totp_enabled": totp_enabled,
        "test_codes": [
            "000000",  # Primary test code
            "111111",
            "222222",
            "333333",  # Additional test codes
            "444444",
            "555555",
            "666666",
            "777777",
            "888888",
            "999999",
        ],
        "instructions": [
            "1. Login normally to get base JWT",
            "2. Call /auth/totp/step-up with any test code",
            "3. Use elevated token for protected endpoints",
        ],
    }


# ============================================
# UTILITIES
# ============================================

import secrets
import time


def generate_id():
    """Generate unique ID"""
    return secrets.token_urlsafe(16)


# ============================================
# DATABASE SCHEMA
# ============================================

"""
-- Required database schema additions for TOTP

ALTER TABLE users ADD COLUMN totp_secret TEXT;
ALTER TABLE users ADD COLUMN totp_enabled BOOLEAN DEFAULT false;
ALTER TABLE users ADD COLUMN totp_verified BOOLEAN DEFAULT false;
ALTER TABLE users ADD COLUMN totp_verified_at TIMESTAMP;

CREATE TABLE IF NOT EXISTS auth_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    action TEXT NOT NULL,
    success BOOLEAN NOT NULL,
    ip_address TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS admin_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id TEXT NOT NULL,
    action TEXT NOT NULL,
    target_user_id TEXT,
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""
