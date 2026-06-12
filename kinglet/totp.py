# kinglet/totp.py
"""
TOTP (Time-based One-Time Password) support for Kinglet
Implements RFC 6238 TOTP algorithm for session elevation
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib
import secrets
import struct
import time
import urllib.parse
from typing import Any

AESGCM = None
InvalidTag = None


def _import_cryptography_aead():
    try:
        exc_mod = importlib.import_module("cryptography.exceptions")
        aead_mod = importlib.import_module("cryptography.hazmat.primitives.ciphers.aead")
    except ImportError:
        return None, None

    return aead_mod.AESGCM, exc_mod.InvalidTag


def _cryptography_aead_available() -> bool:
    """Load and cache the cryptography AES-GCM backend if present."""
    global AESGCM, InvalidTag

    if AESGCM is False and InvalidTag is False:
        return False
    if AESGCM is not None and InvalidTag is not None:
        return True

    AESGCM, InvalidTag = _import_cryptography_aead()
    if AESGCM is None or InvalidTag is None:
        AESGCM = InvalidTag = False
        return False
    return True

# Test TOTP secret that generates predictable codes for development/testing
# This secret will generate "000000" at Unix timestamp 0 (and cyclically)
TEST_TOTP_SECRET = "JBSWY3DPEHPK3PXP"  # nosec B105
_TOTP_DIGESTS = {
    # RFC 6238 explicitly permits HMAC-SHA1/SHA256/SHA512 for TOTP. We keep
    # sha1 only for authenticator interoperability and reject arbitrary or
    # weaker algorithms entirely.
    "sha1": hashlib.sha1,
    "sha256": hashlib.sha256,
    "sha512": hashlib.sha512,
}


def _env_get(env_source: Any, key: str, default=None):
    """Read env values from either dict-like or attribute-style bindings."""
    if isinstance(env_source, dict):
        return env_source.get(key, default)
    return getattr(env_source, key, default)


def _is_pyodide_js_exception(exc: Exception) -> bool:
    try:
        from pyodide.ffi import JsException
    except ImportError:
        return False
    return isinstance(exc, JsException)


def _load_cryptography_aead():
    """Return AES-GCM helpers if the runtime provides cryptography."""
    if _cryptography_aead_available():
        return AESGCM, InvalidTag

    raise RuntimeError(
        "TOTP secret encryption requires the optional "
        "'cryptography' package"
    )


def _looks_like_totp_secret(secret: str) -> bool:
    """Validate that a decrypted value still looks like a base32 TOTP secret."""
    normalized = secret.replace(" ", "").replace("-", "").strip().upper()
    if not normalized:
        return False

    padding_needed = (8 - len(normalized) % 8) % 8
    try:
        base64.b32decode(normalized + "=" * padding_needed)
        return True
    except Exception:
        return False


class OTPProvider:
    """Base OTP provider interface"""

    def generate_secret(self) -> str:
        """Generate a new TOTP secret"""
        raise NotImplementedError

    def verify_code(self, secret: str, provided_code: str, window: int = 1) -> bool:
        """Verify TOTP code"""
        raise NotImplementedError

    def generate_qr_url(
        self, secret: str, account_name: str, issuer: str = "Kinglet"
    ) -> str:
        """Generate QR code URL for authenticator apps"""
        raise NotImplementedError


class ProductionOTPProvider(OTPProvider):
    """Production TOTP provider using RFC 6238"""

    def generate_secret(self) -> str:
        """Generate a new TOTP secret (base32 encoded)"""
        # Generate 20 random bytes (160 bits) as recommended by RFC 6238
        raw_secret = secrets.token_bytes(20)
        return base64.b32encode(raw_secret).decode("ascii")

    def verify_code(
        self, secret: str, provided_code: str, window: int = 1, algorithm: str = "sha1"
    ) -> bool:
        """Verify TOTP code with time window tolerance and configurable algorithm"""
        return verify_totp_code(secret, provided_code, window, algorithm)

    def generate_qr_url(
        self,
        secret: str,
        account_name: str,
        issuer: str = "Kinglet",
        algorithm: str = "sha1",
    ) -> str:
        """Generate TOTP QR code URL with configurable algorithm"""
        return generate_totp_qr_url(secret, account_name, issuer, algorithm)


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
        provided_code = provided_code.replace(" ", "").replace("-", "")
        if len(provided_code) != 6 or not provided_code.isdigit():
            return False

        # Accept any repeated digit pattern (000000, 111111, etc.) for easy testing
        if provided_code in [
            "000000",
            "111111",
            "222222",
            "333333",
            "444444",
            "555555",
            "666666",
            "777777",
            "888888",
            "999999",
        ]:
            return True

        # Also verify against the actual test secret for realistic testing
        return verify_totp_code(secret, provided_code, window, "sha1")

    def generate_qr_url(
        self, secret: str, account_name: str, issuer: str = "Kinglet"
    ) -> str:
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


def generate_totp_code(
    secret: str, timestamp: int | None = None, algorithm: str = "sha1"
) -> str:
    """
    Generate TOTP code for given secret and timestamp

    Args:
        secret: Base32-encoded TOTP secret
        timestamp: Unix timestamp (defaults to current time)
        algorithm: Hash algorithm - 'sha1' (default), 'sha256', or 'sha512'
                  Note: this is the RFC 6238 HMAC digest. Google
                  Authenticator only supports sha1; use sha256/sha512 only
                  with compatible apps.
    """
    if timestamp is None:
        timestamp = int(time.time())

    # TOTP uses 30-second time steps
    time_step = timestamp // 30

    # Convert secret from base32
    try:
        # Add correct padding (only if needed)
        padding_needed = (8 - len(secret) % 8) % 8
        key = base64.b32decode(secret.upper() + "=" * padding_needed)
    except Exception as e:
        raise ValueError("Invalid TOTP secret format") from e

    # Pack time step as big-endian 64-bit integer
    time_bytes = struct.pack(">Q", time_step)

    digest = _TOTP_DIGESTS.get(str(algorithm).lower())
    if digest is None:
        raise ValueError(
            "Invalid algorithm. Supported values: 'sha1', 'sha256', 'sha512'"
        )
    hmac_hash = hmac.new(key, time_bytes, digest).digest()

    # Dynamic truncation (RFC 4226)
    offset = hmac_hash[-1] & 0x0F
    truncated = struct.unpack(">I", hmac_hash[offset : offset + 4])[0] & 0x7FFFFFFF

    # Generate 6-digit code
    code = str(truncated % 1000000).zfill(6)
    return code


def verify_totp_code(
    secret: str, provided_code: str, window: int = 1, algorithm: str = "sha1"
) -> bool:
    """
    Verify TOTP code with time window tolerance

    Args:
        secret: Base32-encoded TOTP secret
        provided_code: 6-digit TOTP code to verify
        window: Time window tolerance (±N * 30 seconds)
        algorithm: Hash algorithm - 'sha1' (default), 'sha256', or 'sha512'
    """
    if not secret or not provided_code:
        return False

    # Remove spaces and validate format
    provided_code = provided_code.replace(" ", "").replace("-", "")
    if len(provided_code) != 6 or not provided_code.isdigit():
        return False

    current_time = int(time.time())

    # Check current time and window (usually ±1 time step = ±30 seconds)
    for i in range(-window, window + 1):
        test_time = current_time + (i * 30)
        expected_code = generate_totp_code(secret, test_time, algorithm)
        if hmac.compare_digest(expected_code, provided_code):
            return True

    return False


def generate_totp_qr_url(
    secret: str, account_name: str, issuer: str = "Kinglet", algorithm: str = "sha1"
) -> str:
    """
    Generate Google Authenticator compatible QR code URL

    Args:
        secret: Base32-encoded TOTP secret
        account_name: User account name
        issuer: Service name
        algorithm: Hash algorithm - 'sha1' (default), 'sha256', or 'sha512'
                  Note: Google Authenticator only supports SHA1
    """
    # Format: otpauth://totp/Issuer:AccountName?secret=SECRET&issuer=Issuer
    label = f"{issuer}:{account_name}"
    params = {
        "secret": secret,
        "issuer": issuer,
        "algorithm": algorithm.upper(),
        "digits": "6",
        "period": "30",
    }

    query_string = urllib.parse.urlencode(params)
    encoded_label = urllib.parse.quote(label)

    return f"otpauth://totp/{encoded_label}?{query_string}"


def create_elevated_jwt(
    user_claims: dict, secret: str, elevation_duration: int = 900
) -> str:
    """Create an elevated session JWT (default 15 minutes)"""
    import json

    # Add elevation claims
    elevated_claims = {
        **user_claims,
        "elevated": True,
        "elevation_time": int(time.time()),
        "exp": int(time.time())
        + elevation_duration,  # Shorter expiry for elevated sessions
    }

    # Create JWT
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = (
        base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    )
    payload_b64 = (
        base64.urlsafe_b64encode(json.dumps(elevated_claims).encode())
        .decode()
        .rstrip("=")
    )

    signature = hmac.new(
        secret.encode(), f"{header_b64}.{payload_b64}".encode(), hashlib.sha256
    ).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")

    return f"{header_b64}.{payload_b64}.{signature_b64}"


def get_totp_encryption_key(env) -> str:
    """Get TOTP encryption key from environment variables"""
    # Primary key for TOTP secret encryption in database
    totp_key = _env_get(env, "TOTP_ENCRYPTION_KEY", None)
    if not totp_key:
        # Fallback to JWT secret if TOTP key not set
        totp_key = _env_get(env, "JWT_SECRET", None)

    if not totp_key:
        raise RuntimeError(
            "TOTP encryption key not configured: set TOTP_ENCRYPTION_KEY or JWT_SECRET"
        )

    totp_key = str(totp_key)

    # In production, this should be a different key from JWT_SECRET
    # for defense in depth
    mode = str(_env_get(env, "MODE", "")).strip().lower()
    jwt_secret = _env_get(env, "JWT_SECRET", None)
    if jwt_secret is not None:
        jwt_secret = str(jwt_secret)
    if mode == "prod" and totp_key == jwt_secret:
        raise RuntimeError("TOTP_ENCRYPTION_KEY must differ from JWT_SECRET in prod")

    return totp_key


def _resolve_totp_encryption_key(encryption_key_or_env: str | Any) -> str:
    if isinstance(encryption_key_or_env, str):
        return encryption_key_or_env
    return get_totp_encryption_key(encryption_key_or_env)


def _derive_totp_aead_key(encryption_key: str) -> bytes:
    """Derive a stable 256-bit AEAD key from the configured secret."""
    return hashlib.sha256(str(encryption_key).encode()).digest()


def _decrypt_totp_secret_legacy(encrypted_bytes: bytes, encryption_key: str) -> str:
    """Decrypt legacy XOR-based ciphertexts for backward compatibility."""
    key_hash = hashlib.sha256(str(encryption_key).encode()).digest()
    decrypted_bytes = bytearray()
    for i, byte in enumerate(encrypted_bytes):
        key_byte = key_hash[i % len(key_hash)]
        decrypted_bytes.append(byte ^ key_byte)
    return decrypted_bytes.decode()


def _webcrypto_aesgcm_encrypt(key_bytes: bytes, nonce: bytes, plaintext: bytes) -> bytes:
    try:
        from js import Array, Object, Uint8Array, crypto
        from pyodide.webloop import can_run_sync, run_sync
    except ImportError as exc:
        raise RuntimeError(
            "TOTP secret encryption requires the optional "
            "'cryptography' package"
        ) from exc

    if not can_run_sync():
        raise RuntimeError(
            "TOTP secret encryption requires the optional "
            "'cryptography' package"
        )

    algorithm = Object.fromEntries([["name", "AES-GCM"]])
    params = Object.fromEntries([["name", "AES-GCM"], ["iv", Uint8Array.new(nonce)]])
    usages = Array.of("encrypt", "decrypt")
    try:
        crypto_key = run_sync(
            crypto.subtle.importKey(
                "raw",
                Uint8Array.new(key_bytes),
                algorithm,
                False,
                usages,
            )
        )
    except Exception as exc:
        if _is_pyodide_js_exception(exc):
            raise RuntimeError(
                "TOTP secret encryption requires the optional "
                "'cryptography' package"
            ) from exc
        raise
    try:
        encrypted = run_sync(
            crypto.subtle.encrypt(params, crypto_key, Uint8Array.new(plaintext))
        )
    except Exception as exc:
        if _is_pyodide_js_exception(exc):
            raise RuntimeError(
                "TOTP secret encryption requires the optional "
                "'cryptography' package"
            ) from exc
        raise
    return bytes(Uint8Array.new(encrypted).to_py())


def _webcrypto_aesgcm_decrypt(key_bytes: bytes, nonce: bytes, ciphertext: bytes) -> bytes:
    try:
        from js import Array, Object, Uint8Array, crypto
        from pyodide.webloop import can_run_sync, run_sync
    except ImportError as exc:
        raise RuntimeError(
            "TOTP secret encryption requires the optional "
            "'cryptography' package"
        ) from exc

    if not can_run_sync():
        raise RuntimeError(
            "TOTP secret encryption requires the optional "
            "'cryptography' package"
        )

    algorithm = Object.fromEntries([["name", "AES-GCM"]])
    params = Object.fromEntries([["name", "AES-GCM"], ["iv", Uint8Array.new(nonce)]])
    usages = Array.of("encrypt", "decrypt")
    try:
        crypto_key = run_sync(
            crypto.subtle.importKey(
                "raw",
                Uint8Array.new(key_bytes),
                algorithm,
                False,
                usages,
            )
        )
    except Exception as exc:
        if _is_pyodide_js_exception(exc):
            raise RuntimeError(
                "TOTP secret encryption requires the optional "
                "'cryptography' package"
            ) from exc
        raise
    try:
        decrypted = run_sync(
            crypto.subtle.decrypt(params, crypto_key, Uint8Array.new(ciphertext))
        )
    except Exception as exc:
        if _is_pyodide_js_exception(exc):
            raise RuntimeError(
                "TOTP secret encryption requires the optional "
                "'cryptography' package"
            ) from exc
        raise
    return bytes(Uint8Array.new(decrypted).to_py())


def encrypt_totp_secret(secret: str, encryption_key: str | Any) -> str:
    """Encrypt TOTP secret for database storage"""
    key = _resolve_totp_encryption_key(encryption_key)
    key_bytes = _derive_totp_aead_key(key)
    nonce = secrets.token_bytes(12)
    if _cryptography_aead_available():
        ciphertext = AESGCM(key_bytes).encrypt(nonce, secret.encode(), None)
    else:
        ciphertext = _webcrypto_aesgcm_encrypt(key_bytes, nonce, secret.encode())
    return base64.b64encode(nonce + ciphertext).decode()


def decrypt_totp_secret(
    encrypted_secret: str | bytes, encryption_key: str | Any
) -> str:
    """Decrypt TOTP secret from database"""
    try:
        encoded_secret = (
            encrypted_secret.encode()
            if isinstance(encrypted_secret, str)
            else encrypted_secret
        )
        encrypted_bytes = base64.b64decode(encoded_secret)
        if len(encrypted_bytes) < 8:
            raise ValueError("Encrypted TOTP secret is too short")
        key = _resolve_totp_encryption_key(encryption_key)
        key_bytes = _derive_totp_aead_key(key)

        if len(encrypted_bytes) >= 28:
            if _cryptography_aead_available():
                try:
                    nonce, ciphertext = encrypted_bytes[:12], encrypted_bytes[12:]
                    decrypted_bytes = AESGCM(key_bytes).decrypt(nonce, ciphertext, None)
                    decrypted_secret = decrypted_bytes.decode()
                    if _looks_like_totp_secret(decrypted_secret):
                        return decrypted_secret
                except (InvalidTag, ValueError):
                    pass
            else:
                try:
                    nonce, ciphertext = encrypted_bytes[:12], encrypted_bytes[12:]
                    decrypted_bytes = _webcrypto_aesgcm_decrypt(
                        key_bytes, nonce, ciphertext
                    )
                    decrypted_secret = decrypted_bytes.decode()
                    if _looks_like_totp_secret(decrypted_secret):
                        return decrypted_secret
                except (RuntimeError, ValueError, TypeError):
                    pass

        decrypted_secret = _decrypt_totp_secret_legacy(encrypted_bytes, key)
        if _looks_like_totp_secret(decrypted_secret):
            return decrypted_secret
        raise ValueError("Failed to decrypt TOTP secret")
    except (ValueError, RuntimeError, TypeError) as e:
        raise ValueError("Failed to decrypt TOTP secret") from e


# Test function to verify TOTP implementation
def test_totp_implementation():
    """Test TOTP implementation with known values"""
    # Test with a known secret
    test_secret = "JBSWY3DPEHPK3PXP"  # nosec B105

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
