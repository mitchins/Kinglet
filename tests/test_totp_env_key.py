from types import SimpleNamespace

from kinglet.totp import (
    decrypt_totp_secret,
    encrypt_totp_secret,
    get_totp_encryption_key,
)


def test_get_totp_encryption_key_fallback_to_jwt_secret():
    env = SimpleNamespace(JWT_SECRET="jwt-secret-value")
    assert get_totp_encryption_key(env) == "jwt-secret-value"


def test_totp_secret_round_trip_accepts_env_object():
    env = SimpleNamespace(TOTP_ENCRYPTION_KEY="totp-secret-value")
    secret = "JBSWY3DPEHPK3PXP"
    encrypted = encrypt_totp_secret(secret, env)
    assert decrypt_totp_secret(encrypted, env) == secret
