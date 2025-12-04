"""
Mock R2 Storage for Unit Testing

This module re-exports the MockR2Bucket implementation from kinglet.testing
for backward compatibility and convenience.

Why a re-export?
    The canonical implementation lives in kinglet.testing so it can be
    imported directly via `from kinglet import MockR2Bucket`. This re-export
    allows existing tests using `from tests.mock_r2 import MockR2Bucket`
    to continue working, and provides a convenient location for test-only
    extensions if needed in the future.

Provides an in-memory R2 bucket implementation that mimics
Cloudflare Workers R2 API for testing without requiring actual
Cloudflare Workers environment or Miniflare.

Usage:
    from tests.mock_r2 import MockR2Bucket
    # or
    from kinglet import MockR2Bucket

    bucket = MockR2Bucket()
    await bucket.put("my-key", b"hello world", {"httpMetadata": {"contentType": "text/plain"}})
    obj = await bucket.get("my-key")
    content = await obj.text()
"""

# Re-export from kinglet.testing for backward compatibility
from kinglet.testing import (
    MockR2Bucket,
    MockR2MultipartUpload,
    MockR2Object,
    MockR2ObjectBody,
    MockR2Objects,
    MockR2UploadedPart,
    MockReadableStream,
    MockStreamReader,
    R2Checksums,
    R2HTTPMetadata,
    R2MockError,
    R2MultipartAbortedError,
    R2MultipartCompletedError,
    R2MultipartUploadError,
    R2PartNotFoundError,
    R2Range,
    R2TooManyKeysError,
)

__all__ = [
    "MockR2Bucket",
    "MockR2Object",
    "MockR2ObjectBody",
    "MockR2Objects",
    "MockR2MultipartUpload",
    "MockR2UploadedPart",
    "MockReadableStream",
    "MockStreamReader",
    "R2HTTPMetadata",
    "R2Checksums",
    "R2Range",
    "R2MockError",
    "R2MultipartAbortedError",
    "R2MultipartCompletedError",
    "R2MultipartUploadError",
    "R2PartNotFoundError",
    "R2TooManyKeysError",
]
