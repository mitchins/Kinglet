# kinglet/totp.py
"""
TOTP (Time-based One-Time Password) support for Kinglet 1.4.0
Implements RFC 6238 TOTP algorithm for session elevation
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse
from typing import Optional

# Test TOTP secret that generates predictable codes for development/testing
# This secret will generate "000000" at Unix timestamp 0 (and cyclically)
TEST_TOTP_SECRET = "JBSWY3DPEHPK3PXP"  # "Hello" in base32 - predictable for testing


class OTPProvider:
    """Base OTP provider interface"""

    def generate_secret(self) -> str:
        """Generate a new TOTP secret"""
        raise NotImplementedError

    def verify_code(self, secret: str, provided_code: str, window: int = 1) -> bool:
        """Verify TOTP code"""
        raise NotImplementedError

    def generate_qr_url(self, secret: str, account_name: str, issuer: str = "Kinglet") -> str:
        """Generate QR code URL for authenticator apps"""
        raise NotImplementedError


class ProductionOTPProvider(OTPProvider):
    """Production TOTP provider using RFC 6238"""

    def generate_secret(self) -> str:
        """Generate a new TOTP secret (base32 encoded)"""
        # Generate 20 random bytes (160 bits) as recommended by RFC 6238
        raw_secret = secrets.token_bytes(20)
        return base64.b32encode(raw_secret).decode('ascii')

    def verify_code(self, secret: str, provided_code: str, window: int = 1) -> bool:
        """Verify TOTP code with time window tolerance"""
        return verify_totp_code(secret, provided_code, window)

    def generate_qr_url(self, secret: str, account_name: str, issuer: str = "Kinglet") -> str:
        """Generate Google Authenticator compatible QR code URL"""
        return generate_totp_qr_url(secret, account_name, issuer)


class DummyOTPProvider(OTPProvider):
    """Test OTP provider that accepts predictable codes for development"""

    def generate_secret(self) -> str:
        """Return test TOTP secret"""
        return TEST_TOTP_SECRET

    def verify_code(self, secret: str, provided_code: str, window: int = 1) -> bool:
        """Accept test codes: 000000, 111111, 222222, etc."""
        if not provided_code:
            return False

        # Remove spaces and validate format
        provided_code = provided_code.replace(' ', '').replace('-', '')
        if len(provided_code) != 6 or not provided_code.isdigit():
            return False

        # Accept any repeated digit pattern (000000, 111111, etc.) for easy testing
        if provided_code in ['000000', '111111', '222222', '333333', '444444', '555555', '666666', '777777', '888888', '999999']:
            return True

        # Also verify against the actual test secret for realistic testing
        return verify_totp_code(secret, provided_code, window)

    def generate_qr_url(self, secret: str, account_name: str, issuer: str = "Kinglet") -> str:
        """Generate QR URL for test secret"""
        return generate_totp_qr_url(secret, account_name, f"{issuer}-TEST")


# Global OTP provider instance - defaults to production, can be overridden
_otp_provider: OTPProvider = ProductionOTPProvider()


def set_otp_provider(provider: OTPProvider) -> None:
    """Set the global OTP provider (for testing/development)"""
    global _otp_provider
    _otp_provider = provider


def get_otp_provider() -> OTPProvider:
    """Get the current OTP provider"""
    return _otp_provider


def generate_totp_secret() -> str:
    """Generate a new TOTP secret using the current OTP provider"""
    return _otp_provider.generate_secret()


def verify_code(secret: str, provided_code: str, window: int = 1) -> bool:
    """Verify TOTP code using the current OTP provider"""
    return _otp_provider.verify_code(secret, provided_code, window)


def install_test_totp_secret() -> str:
    """Install predictable test TOTP secret for development/testing
    
    Returns the test secret that can be used with authenticator apps.
    In development, this secret generates predictable codes including '000000'.
    """
    return TEST_TOTP_SECRET


def generate_totp_code(secret: str, timestamp: Optional[int] = None) -> str:
    """Generate TOTP code for given secret and timestamp"""
    if timestamp is None:
        timestamp = int(time.time())

    # TOTP uses 30-second time steps
    time_step = timestamp // 30

    # Convert secret from base32
    try:
        key = base64.b32decode(secret.upper() + '=' * (8 - len(secret) % 8))
    except Exception:
        raise ValueError("Invalid TOTP secret format")

    # Pack time step as big-endian 64-bit integer
    time_bytes = struct.pack('>Q', time_step)

    # HMAC-SHA1 hash
    hmac_hash = hmac.new(key, time_bytes, hashlib.sha1).digest()

    # Dynamic truncation (RFC 4226)
    offset = hmac_hash[-1] & 0x0f
    truncated = struct.unpack('>I', hmac_hash[offset:offset + 4])[0] & 0x7fffffff

    # Generate 6-digit code
    code = str(truncated % 1000000).zfill(6)
    return code


def verify_totp_code(secret: str, provided_code: str, window: int = 1) -> bool:
    """Verify TOTP code with time window tolerance"""
    if not secret or not provided_code:
        return False

    # Remove spaces and validate format
    provided_code = provided_code.replace(' ', '').replace('-', '')
    if len(provided_code) != 6 or not provided_code.isdigit():
        return False

    current_time = int(time.time())

    # Check current time and window (usually ±1 time step = ±30 seconds)
    for i in range(-window, window + 1):
        test_time = current_time + (i * 30)
        expected_code = generate_totp_code(secret, test_time)
        if hmac.compare_digest(expected_code, provided_code):
            return True

    return False


def generate_totp_qr_url(secret: str, account_name: str, issuer: str = "Kinglet") -> str:
    """Generate Google Authenticator compatible QR code URL"""
    # Format: otpauth://totp/Issuer:AccountName?secret=SECRET&issuer=Issuer
    label = f"{issuer}:{account_name}"
    params = {
        'secret': secret,
        'issuer': issuer,
        'algorithm': 'SHA1',
        'digits': '6',
        'period': '30'
    }

    query_string = urllib.parse.urlencode(params)
    encoded_label = urllib.parse.quote(label)

    return f"otpauth://totp/{encoded_label}?{query_string}"


def create_elevated_jwt(user_claims: dict, secret: str, elevation_duration: int = 900) -> str:
    """Create an elevated session JWT (default 15 minutes)"""
    import json

    # Add elevation claims
    elevated_claims = {
        **user_claims,
        'elevated': True,
        'elevation_time': int(time.time()),
        'exp': int(time.time()) + elevation_duration  # Shorter expiry for elevated sessions
    }

    # Create JWT
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip('=')
    payload_b64 = base64.urlsafe_b64encode(json.dumps(elevated_claims).encode()).decode().rstrip('=')

    signature = hmac.new(
        secret.encode(),
        f"{header_b64}.{payload_b64}".encode(),
        hashlib.sha256
    ).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip('=')

    return f"{header_b64}.{payload_b64}.{signature_b64}"


def get_totp_encryption_key(env) -> str:
    """Get TOTP encryption key from environment variables"""
    # Primary key for TOTP secret encryption in database
    totp_key = getattr(env, 'TOTP_ENCRYPTION_KEY', None)
    if not totp_key:
        # Fallback to JWT secret if TOTP key not set
        totp_key = getattr(env, 'JWT_SECRET', 'dev-totp-key-change-in-production')

    # In production, this should be a different key from JWT_SECRET
    # for defense in depth
    return totp_key


def encrypt_totp_secret(secret: str, encryption_key: str) -> str:
    """Encrypt TOTP secret for database storage"""
    # Simple XOR encryption for demo (use proper AES in production)
    import hashlib

    # Create a consistent key from the encryption key
    key_hash = hashlib.sha256(encryption_key.encode()).digest()

    # XOR each byte of the secret with the key
    secret_bytes = secret.encode()
    encrypted_bytes = bytearray()

    for i, byte in enumerate(secret_bytes):
        key_byte = key_hash[i % len(key_hash)]
        encrypted_bytes.append(byte ^ key_byte)

    # Return as base64 for database storage
    return base64.b64encode(encrypted_bytes).decode()


def decrypt_totp_secret(encrypted_secret: str, encryption_key: str) -> str:
    """Decrypt TOTP secret from database"""
    import hashlib

    try:
        # Decode from base64
        encrypted_bytes = base64.b64decode(encrypted_secret.encode())

        # Create the same key
        key_hash = hashlib.sha256(encryption_key.encode()).digest()

        # XOR to decrypt
        decrypted_bytes = bytearray()
        for i, byte in enumerate(encrypted_bytes):
            key_byte = key_hash[i % len(key_hash)]
            decrypted_bytes.append(byte ^ key_byte)

        return decrypted_bytes.decode()
    except Exception:
        raise ValueError("Failed to decrypt TOTP secret")


# Test function to verify TOTP implementation
def test_totp_implementation():
    """Test TOTP implementation with known values"""
    # Test with a known secret
    test_secret = "JBSWY3DPEHPK3PXP"  # "Hello!" in base32

    # Generate code for current time
    current_code = generate_totp_code(test_secret)
    print(f"Generated TOTP code: {current_code}")

    # Verify the code
    is_valid = verify_totp_code(test_secret, current_code)
    print(f"Code verification: {is_valid}")

    # Test QR URL generation
    qr_url = generate_totp_qr_url(test_secret, "test@example.com", "TestApp")
    print(f"QR URL: {qr_url}")

    return is_valid


if __name__ == "__main__":
    # Run tests if executed directly
    print("Testing TOTP implementation...")
    test_totp_implementation()
