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

import kinglet.totp as totp
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


class _FakeJsException(Exception):
    pass


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


def _fake_workers_webcrypto_modules(*, can_run_sync=True):
    js_module = ModuleType("js")
    js_module.Array = _FakeArray
    js_module.Object = _FakeObject
    js_module.Uint8Array = _FakeUint8Array
    js_module.crypto = SimpleNamespace(subtle=_FakeSubtleCrypto())

    pyodide_module = ModuleType("pyodide")
    ffi_module = ModuleType("pyodide.ffi")
    ffi_module.JsException = _FakeJsException
    webloop_module = ModuleType("pyodide.webloop")
    webloop_module.can_run_sync = lambda: can_run_sync
    webloop_module.run_sync = lambda value: value
    pyodide_module.ffi = ffi_module
    pyodide_module.webloop = webloop_module

    return {
        "js": js_module,
        "pyodide": pyodide_module,
        "pyodide.ffi": ffi_module,
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


def test_cryptography_backend_probe_caches_missing_backend():
    original_aesgcm = totp.AESGCM
    original_invalid_tag = totp.InvalidTag
    try:
        totp.AESGCM = None
        totp.InvalidTag = None

        with patch.object(totp.importlib, "import_module", side_effect=ImportError):
            assert totp._cryptography_aead_available() is False
            assert totp.AESGCM is False
            assert totp.InvalidTag is False
    finally:
        totp.AESGCM = original_aesgcm
        totp.InvalidTag = original_invalid_tag


def test_load_cryptography_aead_requires_backend():
    with patch.object(totp, "_cryptography_aead_available", return_value=False):
        with pytest.raises(RuntimeError, match="optional 'cryptography' package"):
            totp._load_cryptography_aead()


def test_webcrypto_backend_import_failure_raises_optional_crypto_error():
    with patch.dict(
        sys.modules,
        {"js": None, "pyodide": None, "pyodide.ffi": None, "pyodide.webloop": None},
        clear=False,
    ):
        with pytest.raises(RuntimeError, match="optional 'cryptography' package"):
            totp._webcrypto_aesgcm_encrypt(b"0" * 32, b"0" * 12, b"payload")


def test_workers_webcrypto_backend_rejects_non_sync_runtime():
    env = SimpleNamespace(TOTP_ENCRYPTION_KEY="totp-secret-value")

    with patch.object(totp, "_cryptography_aead_available", return_value=False), patch.dict(
        sys.modules, _fake_workers_webcrypto_modules(can_run_sync=False), clear=False
    ):
        with pytest.raises(RuntimeError, match="optional 'cryptography' package"):
            encrypt_totp_secret("JBSWY3DPEHPK3PXP", env)


def test_workers_webcrypto_backend_translates_js_exception():
    env = SimpleNamespace(TOTP_ENCRYPTION_KEY="totp-secret-value")

    class _ExplodingSubtleCrypto(_FakeSubtleCrypto):
        def encrypt(self, params, crypto_key, data):
            raise _FakeJsException("boom")

    modules = _fake_workers_webcrypto_modules()
    modules["js"].crypto = SimpleNamespace(subtle=_ExplodingSubtleCrypto())

    with patch.object(totp, "_cryptography_aead_available", return_value=False), patch.dict(
        sys.modules, modules, clear=False
    ):
        with pytest.raises(RuntimeError, match="optional 'cryptography' package"):
            encrypt_totp_secret("JBSWY3DPEHPK3PXP", env)


def test_workers_webcrypto_backend_translates_js_exception_on_decrypt():
    env = SimpleNamespace(TOTP_ENCRYPTION_KEY="totp-secret-value")
    encrypted = encrypt_totp_secret("JBSWY3DPEHPK3PXP", env)

    class _ExplodingSubtleCrypto(_FakeSubtleCrypto):
        def decrypt(self, params, crypto_key, data):
            raise _FakeJsException("boom")

    modules = _fake_workers_webcrypto_modules()
    modules["js"].crypto = SimpleNamespace(subtle=_ExplodingSubtleCrypto())

    with patch.object(totp, "_cryptography_aead_available", return_value=False), patch.dict(
        sys.modules, modules, clear=False
    ), patch.object(totp, "_decrypt_totp_secret_legacy", return_value="not-a-secret"):
        with pytest.raises(ValueError, match="Failed to decrypt TOTP secret"):
            decrypt_totp_secret(encrypted, env)


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


def test_decrypt_totp_secret_rejects_too_short_ciphertext():
    env = SimpleNamespace(TOTP_ENCRYPTION_KEY="totp-secret-value")

    with pytest.raises(ValueError, match="Failed to decrypt TOTP secret"):
        decrypt_totp_secret("AAAA", env)


def test_decrypt_totp_secret_rejects_invalid_envelope_payload():
    env = SimpleNamespace(TOTP_ENCRYPTION_KEY="totp-secret-value")
    key_bytes = hashlib.sha256(env.TOTP_ENCRYPTION_KEY.encode()).digest()
    nonce = b"0123456789ab"
    ciphertext = AESGCM(key_bytes).encrypt(nonce, b"not-a-secret", None)
    encrypted = base64.b64encode(nonce + ciphertext).decode()

    with patch.object(totp, "_decrypt_totp_secret_legacy", return_value="not-a-secret"):
        with pytest.raises(ValueError, match="Failed to decrypt TOTP secret"):
            decrypt_totp_secret(encrypted, env)


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
