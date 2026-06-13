"""
Pytest configuration and fixtures for Kinglet tests

This file provides centralized test fixtures to reduce boilerplate
across the test suite, particularly for D1 database mocking and Miniflare integration.
"""

import asyncio
import shutil
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from . import _version_guard  # noqa: F401
from .mock_d1 import MockD1Database, d1_unwrap, d1_unwrap_results


def _resolve_wrangler_command() -> list[str]:
    """Prefer a globally installed wrangler binary, fallback to npx."""
    if shutil.which("wrangler"):
        return ["wrangler"]
    if shutil.which("npx"):
        return ["npx", "wrangler"]
    raise FileNotFoundError("Neither wrangler nor npx is available")


@pytest.fixture(autouse=True)
def _route_policy_default(request, monkeypatch):
    """Relax the default-deny route policy for tests that are not about it.

    Kinglet 2.0 defaults to enforce_route_policy=True: every route must be
    explicitly public or carry an access-control marker. The bulk of the suite
    exercises routing/response/middleware/ORM mechanics and registers plain
    routes; annotating each adds no value. This fixture relaxes the *default*
    for those tests only.

    Tests that verify the policy itself (and the production default) carry
    @pytest.mark.route_policy and are left untouched, so they see the real
    enforce-on default that ships and that the scanner evaluates.

    Timing constraint: this patches Kinglet/Router __init__, so an app only
    benefits when it is constructed *inside* the test function (or a fixture
    that runs after this one). Apps built at module import time register their
    routes before the patch is installed and will still see enforce-on.
    """
    if request.node.get_closest_marker("route_policy"):
        return

    import warnings

    import kinglet.core as core
    from kinglet.decorators import RoutePolicyWarning

    for cls in (core.Kinglet, core.Router):
        original_init = cls.__init__

        def patched_init(self, *args, _orig=original_init, **kwargs):
            kwargs.setdefault("enforce_route_policy", False)
            # This relaxation is intentional for mechanics tests; silence the
            # opt-out warning so it does not spam the suite. Tests that probe
            # the opt-out behavior are marked @pytest.mark.route_policy and run
            # without this patch, so they still observe the warning.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RoutePolicyWarning)
                _orig(self, *args, **kwargs)

        monkeypatch.setattr(cls, "__init__", patched_init)


@pytest.fixture(autouse=True)
def d1_patches():
    """
    Auto-patch D1 unwrap functions for all tests

    This fixture automatically applies patches to d1_unwrap and d1_unwrap_results
    across all modules that use them, eliminating the need for manual patching
    in individual test methods.

    Patches applied:
    - kinglet.orm.d1_unwrap -> mock_d1.d1_unwrap
    - kinglet.orm.d1_unwrap_results -> mock_d1.d1_unwrap_results
    - kinglet.orm_migrations.d1_unwrap -> mock_d1.d1_unwrap
    - kinglet.orm_migrations.d1_unwrap_results -> mock_d1.d1_unwrap_results
    """
    patches = [
        patch("kinglet.orm.d1_unwrap", d1_unwrap),
        patch("kinglet.orm.d1_unwrap_results", d1_unwrap_results),
        patch("kinglet.orm_migrations.d1_unwrap", d1_unwrap),
        patch("kinglet.orm_migrations.d1_unwrap_results", d1_unwrap_results),
    ]

    # Start all patches
    for p in patches:
        p.start()

    yield

    # Stop all patches
    for p in patches:
        p.stop()


@pytest.fixture
def mock_db():
    """
    Provide a fresh MockD1Database instance for tests

    Returns:
        MockD1Database: A clean in-memory SQLite database instance
                       that mimics D1's API for testing
    """
    return MockD1Database()


class MiniflareManager:
    """Manages Miniflare lifecycle for tests"""

    def __init__(self, wrangler_cmd: list[str]):
        self.process = None
        self.port = None
        self.base_url = None
        self.config_file = None
        self.worker_file = None
        self.wrangler_cmd = wrangler_cmd

    async def start(self, port=8787):
        """Start Miniflare with D1, R2, and KV bindings"""
        self.port = port
        self.base_url = f"http://localhost:{port}"

        # Create temporary wrangler.toml for testing
        self.config_file = Path("wrangler.test.toml")
        wrangler_config = """
name = "kinglet-test"
main = "test_worker.js"
compatibility_date = "2024-01-01"

[[d1_databases]]
binding = "DB"
database_name = "kinglet_test_db"
database_id = "test-db-id"

[[r2_buckets]]
binding = "BUCKET"
bucket_name = "kinglet-test-bucket"

[[kv_namespaces]]
binding = "CACHE"
id = "test-cache-namespace"

[vars]
ENVIRONMENT = "test"
JWT_SECRET = "test-secret-key-for-jwt-signing"
TOTP_SECRET_KEY = "test-totp-encryption-key-32-chars"
TOTP_ENABLED = "true"
"""

        self.config_file.write_text(wrangler_config)

        # Create minimal test worker
        self.worker_file = Path("test_worker.js")
        worker_js = """
export default {
    async fetch(request, env) {
        const url = new URL(request.url);

        if (url.pathname === '/health') {
            return new Response('OK');
        }

        if (url.pathname === '/env') {
            return new Response(JSON.stringify({
                hasDB: !!env.DB,
                hasBucket: !!env.BUCKET,
                hasCache: !!env.CACHE,
                jwtSecret: !!env.JWT_SECRET,
                totpEnabled: env.TOTP_ENABLED
            }), {
                headers: { 'Content-Type': 'application/json' }
            });
        }

        // Echo endpoint for testing
        return new Response('Miniflare Test Worker Running', { status: 200 });
    }
};
"""

        self.worker_file.write_text(worker_js)

        try:
            # Start Miniflare via wrangler dev (Miniflare v3)
            cmd = [
                *self.wrangler_cmd,
                "dev",
                "--config",
                str(self.config_file),
                "--port",
                str(port),
                "--local",
                "--log-level",
                "error",
            ]

            self.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )

            # Wait for startup
            await self._wait_for_startup()

        except Exception as e:
            # Force capture process output for debugging - kill if needed
            process_output = ""
            if self.process:
                try:
                    # First try non-blocking read of available output
                    if self.process.stdout and self.process.stderr:
                        # Give it a moment to produce output
                        await asyncio.sleep(0.1)
                        # Terminate and get output
                        self.process.terminate()
                        stdout, stderr = self.process.communicate(timeout=5)
                        process_output = f"\nSTDOUT: {stdout}\nSTDERR: {stderr}"
                except (subprocess.TimeoutExpired, OSError):
                    # Force kill if needed
                    try:
                        self.process.kill()
                        stdout, stderr = self.process.communicate(timeout=2)
                        process_output = f"\nSTDOUT: {stdout}\nSTDERR: {stderr}"
                    except (subprocess.TimeoutExpired, OSError):
                        process_output = "\nFailed to capture process output"
            await self.stop()
            raise RuntimeError(f"Failed to start Miniflare: {e}{process_output}") from e

    async def _wait_for_startup(self, timeout=30):
        """Wait for Miniflare to be ready"""
        start_time = time.time()
        last_error = None

        while time.time() - start_time < timeout:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{self.base_url}/health", timeout=1)
                    if response.status_code == 200:
                        return
            except Exception as e:
                last_error = e
                pass
            await asyncio.sleep(0.5)

        # FORCE capture process output for debugging - terminate if needed
        process_info = ""
        if self.process:
            try:
                # If process already exited, get output
                if self.process.poll() is not None:
                    stdout, stderr = self.process.communicate(timeout=1)
                    process_info = f"\nProcess exited with code: {self.process.returncode}\nSTDOUT: {stdout}\nSTDERR: {stderr}"
                else:
                    # Process still running - terminate it and get output
                    self.process.terminate()
                    stdout, stderr = self.process.communicate(timeout=5)
                    process_info = f"\nProcess was running, terminated. STDOUT: {stdout}\nSTDERR: {stderr}"
            except (subprocess.TimeoutExpired, OSError):
                # Force kill and try again
                try:
                    self.process.kill()
                    stdout, stderr = self.process.communicate(timeout=2)
                    process_info = (
                        f"\nProcess killed. STDOUT: {stdout}\nSTDERR: {stderr}"
                    )
                except (subprocess.TimeoutExpired, OSError):
                    process_info = f"\nProcess status: {self.process.poll()}, failed to capture output"

        raise RuntimeError(
            f"Miniflare failed to start within {timeout}s timeout. Last HTTP error: {last_error}{process_info}"
        )

    async def stop(self):
        """Stop Miniflare and cleanup"""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.process = None

        # Cleanup temp files
        for file in [self.config_file, self.worker_file]:
            if file and file.exists():
                try:
                    file.unlink()
                except Exception:
                    pass


# Miniflare integration - REQUIRED for complete test suite
@pytest.fixture(scope="session")
async def miniflare():
    """Session-scoped Miniflare instance - FAILS if wrangler unavailable"""
    # Check if wrangler is available - FAIL if not
    try:
        wrangler_cmd = _resolve_wrangler_command()
        result = subprocess.run(
            [*wrangler_cmd, "--version"], capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            details = result.stderr.strip() or result.stdout.strip()
            pytest.fail(
                "Miniflare integration tests require wrangler but it failed to run.\n"
                f"Command: {' '.join(wrangler_cmd)} --version\n"
                f"Details: {details or 'no output'}\n"
                "Install with: npm install -g wrangler\n"
                "Or exclude with: pytest -m 'not miniflare'"
            )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        pytest.fail(
            f"Miniflare integration tests require wrangler but it's not available: {e}\n"
            "Install with: npm install -g wrangler\n"
            "Or exclude with: pytest -m 'not miniflare'"
        )

    manager = MiniflareManager(wrangler_cmd)
    try:
        await manager.start()
        yield manager
    finally:
        await manager.stop()


@pytest.fixture
def miniflare_env(miniflare):
    """Provides environment configuration for tests"""
    return {
        "base_url": miniflare.base_url,
        "db_binding": "DB",
        "bucket_binding": "BUCKET",
        "cache_binding": "CACHE",
        "jwt_secret": "test-secret-key-for-jwt-signing",
        "totp_secret": "test-totp-encryption-key-32-chars",
    }
