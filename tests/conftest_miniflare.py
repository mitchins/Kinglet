"""
Miniflare integration for CloudFlare Workers testing
"""

import asyncio
import os
import subprocess
import time
from pathlib import Path

import httpx
import pytest

from . import _version_guard  # noqa: F401


class MiniflareManager:
    """Manages Miniflare lifecycle for tests"""

    def __init__(self):
        self.process = None
        self.port = None
        self.base_url = None

    async def start(self, port=8787):
        """Start Miniflare with D1, R2, and KV bindings"""
        self.port = port
        self.base_url = f"http://localhost:{port}"

        # Create temporary wrangler.toml for testing
        config = {
            "name": "kinglet-test",
            "main": "test_worker.js",
            "compatibility_date": "2024-01-01",
            "d1_databases": [
                {
                    "binding": "DB",
                    "database_name": "kinglet_test_db",
                    "database_id": "test-db-id",
                }
            ],
            "r2_buckets": [{"binding": "BUCKET", "bucket_name": "kinglet-test-bucket"}],
            "kv_namespaces": [{"binding": "CACHE", "id": "test-cache-namespace"}],
            "vars": {
                "ENVIRONMENT": "test",
                "JWT_SECRET": "test-secret-key-for-jwt-signing",
                "TOTP_SECRET_KEY": "test-totp-encryption-key-32-chars",
                "TOTP_ENABLED": "true",
            },
        }

        config_path = Path("wrangler.test.toml")
        with open(config_path, "w") as f:
            # Convert to TOML format
            lines = [
                f'name = "{config["name"]}"',
                f'main = "{config["main"]}"',
                f'compatibility_date = "{config["compatibility_date"]}"',
                "",
                "[[d1_databases]]",
                f'binding = "{config["d1_databases"][0]["binding"]}"',
                f'database_name = "{config["d1_databases"][0]["database_name"]}"',
                f'database_id = "{config["d1_databases"][0]["database_id"]}"',
                "",
                "[[r2_buckets]]",
                f'binding = "{config["r2_buckets"][0]["binding"]}"',
                f'bucket_name = "{config["r2_buckets"][0]["bucket_name"]}"',
                "",
                "[[kv_namespaces]]",
                f'binding = "{config["kv_namespaces"][0]["binding"]}"',
                f'id = "{config["kv_namespaces"][0]["id"]}"',
                "",
                "[vars]",
            ]
            for key, value in config["vars"].items():
                lines.append(f'{key} = "{value}"')

            f.write("\n".join(lines))

        # Create minimal test worker
        worker_js = """
export default {
    async fetch(request, env) {
        // Simple echo endpoint for testing
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

        // Proxy to Python test handler
        return new Response('Test Worker Running', { status: 200 });
    }
};
        """

        with open("test_worker.js", "w") as f:
            f.write(worker_js)

        try:
            # Start wrangler dev (includes Miniflare)
            cmd = [
                "npx",
                "wrangler",
                "dev",
                "--config",
                str(config_path),
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
            # Capture process output for debugging
            process_output = ""
            if self.process:
                try:
                    stdout, stderr = self.process.communicate(timeout=1)
                    process_output = f"\nSTDOUT: {stdout}\nSTDERR: {stderr}"
                except subprocess.TimeoutExpired:
                    pass
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

        # Get process output for debugging
        process_info = ""
        if self.process:
            if self.process.poll() is not None:
                try:
                    stdout, stderr = self.process.communicate(timeout=1)
                    process_info = f"\nProcess exited with code: {self.process.returncode}\nSTDOUT: {stdout}\nSTDERR: {stderr}"
                except subprocess.TimeoutExpired:
                    process_info = (
                        f"\nProcess exited with code: {self.process.returncode}"
                    )
            else:
                process_info = "\nProcess is still running but not responding"

        raise RuntimeError(
            f"Miniflare failed to start within {timeout}s timeout. Last HTTP error: {last_error}{process_info}"
        )

    async def stop(self):
        """Stop Miniflare and cleanup"""
        if self.process:
            self.process.terminate()
            self.process.wait()
            self.process = None

        # Cleanup temp files
        for file in ["wrangler.test.toml", "test_worker.js"]:
            try:
                os.unlink(file)
            except FileNotFoundError:
                pass

    async def reset_data(self):
        """Reset all data stores for clean test state"""
        # This would reset D1, R2, and KV data
        # Implementation depends on Miniflare's reset capabilities
        pass


@pytest.fixture(scope="session")
async def miniflare():
    """Session-scoped Miniflare instance"""
    manager = MiniflareManager()

    try:
        await manager.start()
        yield manager
    finally:
        await manager.stop()


@pytest.fixture
async def clean_miniflare(miniflare):
    """Function-scoped fixture that resets data between tests"""
    await miniflare.reset_data()
    yield miniflare


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
