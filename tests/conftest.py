"""
Pytest configuration and fixtures for Kinglet tests

This file provides centralized test fixtures to reduce boilerplate
across the test suite, particularly for D1 database mocking and Miniflare integration.
"""

import asyncio
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

import pytest

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

from .mock_d1 import MockD1Database, d1_unwrap, d1_unwrap_results


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

    def __init__(self):
        self.process = None
        self.port = None
        self.base_url = None
        self.config_file = None
        self.worker_file = None

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
                "npx",
                "wrangler",
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
            await self.stop()
            raise RuntimeError(f"Failed to start Miniflare: {e}") from e

    async def _wait_for_startup(self, timeout=10):
        """Wait for Miniflare to be ready"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                if HAS_HTTPX:
                    async with httpx.AsyncClient() as client:
                        response = await client.get(
                            f"{self.base_url}/health", timeout=1
                        )
                        if response.status_code == 200:
                            return
                else:
                    # Fallback without httpx - just wait a bit
                    await asyncio.sleep(2)
                    return
            except Exception:
                pass
            await asyncio.sleep(0.1)

        raise RuntimeError("Miniflare failed to start within timeout")

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


# Miniflare integration - no fallbacks, no hedging
@pytest.fixture(scope="session")
async def miniflare():
    """Session-scoped Miniflare instance - REQUIRES wrangler"""
    manager = MiniflareManager()
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
