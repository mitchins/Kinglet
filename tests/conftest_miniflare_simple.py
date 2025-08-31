"""
Simple Miniflare integration for critical CloudFlare Workers testing
"""

import shutil

import pytest


# Simple fixture that provides test environment
@pytest.fixture
def miniflare_env():
    """Provides environment configuration for tests"""
    return {
        "base_url": "http://localhost:8787",
        "db_binding": "DB",
        "bucket_binding": "BUCKET",
        "cache_binding": "CACHE",
        "jwt_secret": "test-secret-key-for-jwt-signing",
        "totp_secret": "test-totp-encryption-key-32-chars",
    }


# Skip miniflare tests if Node.js not available
miniflare_available = shutil.which("npx") is not None
