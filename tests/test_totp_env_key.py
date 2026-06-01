import base64
import hashlib
from types import SimpleNamespace

import pytest

from kinglet.totp import (
    decrypt_totp_secret,
    encrypt_totp_secret,
    get_totp_encryption_key,
)


def _encrypt_totp_secret_legacy(secret: str, encryption_key: str) -> str:
    key_hash = hashlib.sha256(encryption_key.encode()).digest()
    encrypted = bytearray()
    for i, byte in enumerate(secret.encode()):
        encrypted.append(byte ^ key_hash[i % len(key_hash)])
    return base64.b64encode(bytes(encrypted)).decode()


def test_get_totp_encryption_key_fallback_to_jwt_secret():
    env = SimpleNamespace(JWT_SECRET="jwt-secret-value")
    assert get_totp_encryption_key(env) == "jwt-secret-value"


def test_get_totp_encryption_key_requires_configured_secret():
    env = SimpleNamespace()

    with pytest.raises(RuntimeError, match="TOTP encryption key not configured"):
        get_totp_encryption_key(env)


def test_get_totp_encryption_key_rejects_prod_jwt_secret():
    env = SimpleNamespace(MODE="prod", JWT_SECRET="jwt-secret-value")

    with pytest.raises(RuntimeError, match="must differ from JWT_SECRET"):
        get_totp_encryption_key(env)


def test_get_totp_encryption_key_supports_dict_env():
    env = {"TOTP_ENCRYPTION_KEY": "totp-secret-value", "MODE": "dev"}
    assert get_totp_encryption_key(env) == "totp-secret-value"


def test_totp_secret_round_trip_accepts_env_object():
    env = SimpleNamespace(TOTP_ENCRYPTION_KEY="totp-secret-value")
    secret = "JBSWY3DPEHPK3PXP"
    encrypted = encrypt_totp_secret(secret, env)
    assert decrypt_totp_secret(encrypted, env) == secret


def test_totp_secret_round_trip_accepts_dict_env():
    env = {"TOTP_ENCRYPTION_KEY": "totp-secret-value"}
    secret = "JBSWY3DPEHPK3PXP"
    encrypted = encrypt_totp_secret(secret, env)
    assert decrypt_totp_secret(encrypted, env) == secret


def test_decrypt_totp_secret_supports_legacy_ciphertext():
    secret = "JBSWY3DPEHPK3PXP"
    legacy_ciphertext = _encrypt_totp_secret_legacy(secret, "totp-secret-value")
    env = SimpleNamespace(TOTP_ENCRYPTION_KEY="totp-secret-value")

    assert decrypt_totp_secret(legacy_ciphertext, env) == secret
