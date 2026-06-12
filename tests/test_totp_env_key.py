import base64
import hashlib
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from kinglet.totp import (
    decrypt_totp_secret,
    encrypt_totp_secret,
    get_totp_encryption_key,
)

ROOT = Path(__file__).resolve().parents[1]


def _encrypt_totp_secret_legacy(secret: str, encryption_key: str) -> str:
    key_hash = hashlib.sha256(encryption_key.encode()).digest()
    encrypted = bytearray()
    for i, byte in enumerate(secret.encode()):
        encrypted.append(byte ^ key_hash[i % len(key_hash)])
    return base64.b64encode(bytes(encrypted)).decode()


class _FakeUint8Array:
    def __init__(self, data):
        if isinstance(data, _FakeUint8Array):
            self._bytes = data._bytes
        elif isinstance(data, (bytes, bytearray, memoryview)):
            self._bytes = bytes(data)
        else:
            self._bytes = bytes(data)

    @classmethod
    def new(cls, data):
        return cls(data)

    def to_py(self):
        return list(self._bytes)


class _FakeArray:
    @staticmethod
    def of(*values):
        return list(values)


class _FakeObject:
    @staticmethod
    def fromEntries(entries):
        return {key: value for key, value in entries}


class _FakeSubtleCrypto:
    def importKey(self, format_name, key_data, algorithm, extractable, usages):
        assert format_name == "raw"
        assert algorithm["name"] == "AES-GCM"
        assert list(usages) == ["encrypt", "decrypt"]
        return bytes(key_data.to_py())

    def encrypt(self, params, crypto_key, data):
        return AESGCM(crypto_key).encrypt(bytes(params["iv"].to_py()), bytes(data.to_py()), None)

    def decrypt(self, params, crypto_key, data):
        return AESGCM(crypto_key).decrypt(bytes(params["iv"].to_py()), bytes(data.to_py()), None)


def _fake_workers_webcrypto_modules():
    js_module = ModuleType("js")
    js_module.Array = _FakeArray
    js_module.Object = _FakeObject
    js_module.Uint8Array = _FakeUint8Array
    js_module.crypto = SimpleNamespace(subtle=_FakeSubtleCrypto())

    pyodide_module = ModuleType("pyodide")
    webloop_module = ModuleType("pyodide.webloop")
    webloop_module.can_run_sync = lambda: True
    webloop_module.run_sync = lambda value: value
    pyodide_module.webloop = webloop_module

    return {
        "js": js_module,
        "pyodide": pyodide_module,
        "pyodide.webloop": webloop_module,
    }


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


def test_standard_python_cryptography_backend_encrypts_and_decrypts_round_trip():
    env = SimpleNamespace(TOTP_ENCRYPTION_KEY="totp-secret-value")
    secret = "JBSWY3DPEHPK3PXP"

    with patch("kinglet.totp._webcrypto_aesgcm_encrypt", side_effect=AssertionError), patch(
        "kinglet.totp._webcrypto_aesgcm_decrypt", side_effect=AssertionError
    ):
        encrypted = encrypt_totp_secret(secret, env)
        assert decrypt_totp_secret(encrypted, env) == secret


def test_workers_webcrypto_backend_encrypts_and_decrypts_round_trip():
    env = SimpleNamespace(TOTP_ENCRYPTION_KEY="totp-secret-value")
    secret = "JBSWY3DPEHPK3PXP"

    with patch(
        "kinglet.totp._cryptography_aead_available", return_value=False
    ), patch.dict(sys.modules, _fake_workers_webcrypto_modules(), clear=False):
        encrypted = encrypt_totp_secret(secret, env)
        assert decrypt_totp_secret(encrypted, env) == secret


def test_totp_ciphertext_envelope_is_base64_nonce_plus_ciphertext():
    env = SimpleNamespace(TOTP_ENCRYPTION_KEY="totp-secret-value")
    secret = "JBSWY3DPEHPK3PXP"

    encrypted = encrypt_totp_secret(secret, env)
    decoded = base64.b64decode(encrypted)

    assert len(decoded) == 12 + len(secret.encode()) + 16
    assert base64.b64encode(decoded).decode() == encrypted


def test_decrypt_totp_secret_supports_legacy_ciphertext():
    secret = "JBSWY3DPEHPK3PXP"
    legacy_ciphertext = _encrypt_totp_secret_legacy(secret, "totp-secret-value")
    env = SimpleNamespace(TOTP_ENCRYPTION_KEY="totp-secret-value")

    assert decrypt_totp_secret(legacy_ciphertext, env) == secret


def test_old_totp_fixture_decrypts_under_1_9_0():
    secret = "JBSWY3DPEHPK3PXP"
    legacy_ciphertext = _encrypt_totp_secret_legacy(secret, "totp-secret-value")
    env = SimpleNamespace(TOTP_ENCRYPTION_KEY="totp-secret-value")

    assert decrypt_totp_secret(legacy_ciphertext, env) == secret


def test_base_import_works_without_cryptography_on_emscripten():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import builtins
import sys

real_import = builtins.__import__

def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "cryptography" or name.startswith("cryptography."):
        raise ImportError("blocked for emscripten import test")
    return real_import(name, globals, locals, fromlist, level)

builtins.__import__ = blocked_import
sys.platform = "emscripten"

import kinglet

print(kinglet.Kinglet.__name__)
""",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "Kinglet"


def test_encrypt_totp_secret_errors_when_no_backend_exists():
    env = SimpleNamespace(TOTP_ENCRYPTION_KEY="totp-secret-value")

    with patch(
        "kinglet.totp._cryptography_aead_available", return_value=False
    ), patch(
        "kinglet.totp._webcrypto_aesgcm_encrypt",
        side_effect=RuntimeError(
            "TOTP secret encryption requires the optional 'cryptography' package"
        ),
    ):
        with pytest.raises(RuntimeError, match="optional 'cryptography' package"):
            encrypt_totp_secret("JBSWY3DPEHPK3PXP", env)


def test_decrypt_legacy_ciphertext_without_cryptography():
    secret = "JBSWY3DPEHPK3PXP"
    legacy_ciphertext = _encrypt_totp_secret_legacy(secret, "totp-secret-value")
    env = SimpleNamespace(TOTP_ENCRYPTION_KEY="totp-secret-value")

    with patch(
        "kinglet.totp._cryptography_aead_available", return_value=False
    ):
        assert decrypt_totp_secret(legacy_ciphertext, env) == secret
