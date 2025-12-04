"""
Kinglet Testing Utilities - TestClient and Mock classes

This module provides testing utilities for Kinglet applications:
- TestClient: Simple sync wrapper for testing without HTTP overhead
- MockR2Bucket: In-memory R2 storage for unit testing
- MockDatabase: Simple D1 mock for basic testing
"""

import builtins
import hashlib
import io
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


class TestClient:
    """Simple sync wrapper for testing Kinglet apps without HTTP/Wrangler overhead"""

    __test__ = False  # Tell pytest this is not a test class

    def __init__(self, app, base_url="https://testserver", env=None):
        self.app = app
        self.base_url = base_url.rstrip("/")
        self.env = env or {}

        # Enable test mode on the app if it's a Kinglet instance
        if hasattr(app, "test_mode"):
            app.test_mode = True

    def request(
        self, method: str, path: str, json_data=None, data=None, headers=None, **kwargs
    ):
        """Make a test request and return (status, headers, body)"""
        import asyncio

        return asyncio.run(
            self._async_request(method, path, json_data, data, headers, **kwargs)
        )

    def _prepare_request_data(self, json_data, data, headers, kwargs):
        """Prepare request headers and body content"""
        # Handle 'json' keyword argument (common in test APIs)
        if "json" in kwargs and json_data is None:
            json_data = kwargs.pop("json")

        # Prepare headers
        test_headers = {"content-type": "application/json"} if json_data else {}
        if headers:
            test_headers.update({k.lower(): v for k, v in headers.items()})

        # Prepare body
        body_content = ""
        if json_data is not None:
            body_content = json.dumps(json_data)
            test_headers["content-type"] = "application/json"
        elif data is not None:
            body_content = str(data)

        return test_headers, body_content

    def _serialize_response_content(self, content):
        """Serialize response content for test consumption"""
        if isinstance(content, dict | list):
            return json.dumps(content)
        return str(content) if content is not None else ""

    def _handle_kinglet_response(self, response):
        """Handle Kinglet Response objects"""
        if hasattr(response, "status") and hasattr(response, "content"):
            status = response.status
            headers = response.headers
            content = response.content
            body = self._serialize_response_content(content)
            return status, headers, body
        return None

    def _handle_raw_response(self, response):
        """Handle raw response objects (dict, string, etc.)"""
        if isinstance(response, dict):
            return 200, {}, json.dumps(response)
        elif isinstance(response, str):
            return 200, {}, response
        else:
            return 200, {}, str(response)

    async def _async_request(
        self, method: str, path: str, json_data=None, data=None, headers=None, **kwargs
    ):
        """Internal async request handler"""
        test_headers, body_content = self._prepare_request_data(
            json_data, data, headers, kwargs
        )
        url = f"{self.base_url}{path}"

        # Create mock objects
        mock_request = MockRequest(method, url, test_headers, body_content)
        mock_env = MockEnv(self.env)

        try:
            response = await self.app(mock_request, mock_env)

            # Try to handle as Kinglet Response first
            kinglet_result = self._handle_kinglet_response(response)
            if kinglet_result:
                return kinglet_result

            # Handle as raw response
            return self._handle_raw_response(response)

        except Exception as e:
            error_body = json.dumps({"error": str(e)})
            return 500, {}, error_body


class MockRequest:
    """Mock request object for testing that matches Workers request interface"""

    def __init__(self, method: str, url: str, headers: dict, body: str = ""):
        self.method = method
        self.url = url
        self.headers = MockHeaders(headers)
        self._body = body

    async def text(self):
        return self._body

    async def json(self):
        if self._body:
            return json.loads(self._body)
        return None


class MockHeaders:
    """Mock headers object that matches Workers headers interface"""

    def __init__(self, headers_dict):
        self._headers = {k.lower(): v for k, v in (headers_dict or {}).items()}

    def get(self, key, default=None):
        return self._headers.get(key.lower(), default)

    def items(self):
        return self._headers.items()

    def __iter__(self):
        return iter(self._headers.items())


class MockEnv:
    """Mock environment object for testing"""

    def __init__(self, env_dict):
        # Set defaults for common Cloudflare bindings
        self.DB = env_dict.get("DB", MockDatabase())
        self.ENVIRONMENT = env_dict.get("ENVIRONMENT", "test")

        # Add any additional environment variables
        for key, value in env_dict.items():
            setattr(self, key, value)


class MockDatabase:
    """Mock D1 database for testing"""

    def __init__(self):
        self._data = {}

    def prepare(self, sql: str):
        return MockQuery(sql, self._data)


class MockQuery:
    """Mock D1 prepared statement"""

    def __init__(self, sql: str, data: dict):
        self.sql = sql
        self.data = data
        self.bindings = []

    def bind(self, *args):
        self.bindings = args
        return self

    async def run(self):
        return MockResult({"changes": 1, "last_row_id": 1})

    async def first(self):
        return MockRow({"id": 1, "name": "Test"})

    async def all(self):
        return MockResult([{"id": 1, "name": "Test"}])


class MockRow:
    """Mock D1 row result with to_py() method"""

    def __init__(self, data):
        self.data = data

    def to_py(self):
        return self.data


class MockResult:
    """Mock D1 query result"""

    def __init__(self, data):
        if isinstance(data, dict):
            self.meta = data
            self.results = []
        else:
            self.results = data
            self.meta = {"changes": len(data)}


# =============================================================================
# R2 Mock Implementation
# =============================================================================


@dataclass
class R2HTTPMetadata:
    """HTTP metadata for R2 objects"""

    contentType: str | None = None
    contentLanguage: str | None = None
    contentDisposition: str | None = None
    contentEncoding: str | None = None
    cacheControl: str | None = None
    cacheExpiry: datetime | None = None


@dataclass
class R2Checksums:
    """Checksums for R2 objects"""

    md5: bytes | None = None
    sha1: bytes | None = None
    sha256: bytes | None = None
    sha384: bytes | None = None
    sha512: bytes | None = None


@dataclass
class R2Range:
    """Range information for partial reads"""

    offset: int = 0
    length: int | None = None
    suffix: int | None = None


class MockR2Object:
    """
    Mock R2Object - metadata only (returned by head() and list())

    Matches the Workers R2Object interface.
    """

    def __init__(
        self,
        key: str,
        size: int,
        etag: str,
        uploaded: datetime,
        http_metadata: R2HTTPMetadata | None = None,
        custom_metadata: dict[str, str] | None = None,
        version: str | None = None,
        checksums: R2Checksums | None = None,
        storage_class: str = "Standard",
    ):
        self.key = key
        self.size = size
        self.etag = etag
        self.httpEtag = f'"{etag}"'
        self.uploaded = uploaded
        self.httpMetadata = http_metadata or R2HTTPMetadata()
        self.customMetadata = custom_metadata or {}
        self.version = version or str(uuid.uuid4())
        self.checksums = checksums or R2Checksums()
        self.storageClass = storage_class
        self.range: R2Range | None = None

    def writeHttpMetadata(self, headers: dict[str, str]) -> None:
        """Write HTTP metadata to headers dict"""
        if self.httpMetadata.contentType:
            headers["Content-Type"] = self.httpMetadata.contentType
        if self.httpMetadata.contentLanguage:
            headers["Content-Language"] = self.httpMetadata.contentLanguage
        if self.httpMetadata.contentDisposition:
            headers["Content-Disposition"] = self.httpMetadata.contentDisposition
        if self.httpMetadata.contentEncoding:
            headers["Content-Encoding"] = self.httpMetadata.contentEncoding
        if self.httpMetadata.cacheControl:
            headers["Cache-Control"] = self.httpMetadata.cacheControl


class MockR2ObjectBody(MockR2Object):
    """
    Mock R2ObjectBody - metadata plus body (returned by get())

    Matches the Workers R2ObjectBody interface with body as ReadableStream.
    """

    def __init__(
        self,
        key: str,
        size: int,
        etag: str,
        uploaded: datetime,
        data: bytes,
        http_metadata: R2HTTPMetadata | None = None,
        custom_metadata: dict[str, str] | None = None,
        version: str | None = None,
        checksums: R2Checksums | None = None,
        storage_class: str = "Standard",
        range_info: R2Range | None = None,
    ):
        super().__init__(
            key=key,
            size=size,
            etag=etag,
            uploaded=uploaded,
            http_metadata=http_metadata,
            custom_metadata=custom_metadata,
            version=version,
            checksums=checksums,
            storage_class=storage_class,
        )
        self._data = data
        self._body_used = False
        self.range = range_info

        # Mock ReadableStream-like body
        self.body = MockReadableStream(data)

    @property
    def bodyUsed(self) -> bool:
        return self._body_used

    async def arrayBuffer(self) -> bytes:
        """Return data as ArrayBuffer (bytes in Python)"""
        self._body_used = True
        return self._data

    async def text(self) -> str:
        """Return data as string"""
        self._body_used = True
        return self._data.decode("utf-8")

    async def json(self) -> Any:
        """Return data as parsed JSON"""
        self._body_used = True
        return json.loads(self._data.decode("utf-8"))

    async def blob(self) -> bytes:
        """Return data as Blob (bytes in Python)"""
        self._body_used = True
        return self._data


class MockReadableStream:
    """Mock ReadableStream for R2 body"""

    def __init__(self, data: bytes):
        self._data = data
        self._stream = io.BytesIO(data)
        self.locked = False

    def getReader(self):
        """Get a reader for the stream"""
        return MockStreamReader(self._stream)

    async def read(self) -> bytes:
        """Read all data from stream"""
        return self._data


class MockStreamReader:
    """Mock stream reader"""

    def __init__(self, stream: io.BytesIO):
        self._stream = stream

    async def read(self) -> dict[str, Any]:
        """Read next chunk"""
        chunk = self._stream.read(8192)
        if chunk:
            return {"value": chunk, "done": False}
        return {"value": None, "done": True}


@dataclass
class MockR2Objects:
    """
    Mock R2Objects - list() result

    Matches the Workers R2Objects interface.
    """

    objects: list[MockR2Object]
    truncated: bool = False
    cursor: str | None = None
    delimitedPrefixes: list[str] = field(default_factory=list)


@dataclass
class MockR2UploadedPart:
    """Represents an uploaded part in multipart upload"""

    partNumber: int
    etag: str


class MockR2MultipartUpload:
    """
    Mock R2MultipartUpload for multipart upload operations

    Supports uploadPart, abort, and complete operations.
    """

    def __init__(
        self,
        bucket: "MockR2Bucket",
        key: str,
        upload_id: str,
        http_metadata: R2HTTPMetadata | None = None,
        custom_metadata: dict[str, str] | None = None,
    ):
        self.key = key
        self.uploadId = upload_id
        self._bucket = bucket
        self._parts: dict[int, bytes] = {}
        self._http_metadata = http_metadata
        self._custom_metadata = custom_metadata
        self._aborted = False
        self._completed = False

    async def uploadPart(
        self, partNumber: int, value: bytes | str
    ) -> MockR2UploadedPart:
        """Upload a part to the multipart upload"""
        if self._aborted:
            raise Exception("Multipart upload has been aborted")
        if self._completed:
            raise Exception("Multipart upload has been completed")

        if isinstance(value, str):
            value = value.encode("utf-8")

        self._parts[partNumber] = value
        etag = hashlib.md5(value).hexdigest()

        return MockR2UploadedPart(partNumber=partNumber, etag=etag)

    async def abort(self) -> None:
        """Abort the multipart upload"""
        self._aborted = True
        self._parts.clear()
        if self.uploadId in self._bucket._multipart_uploads:
            del self._bucket._multipart_uploads[self.uploadId]

    async def complete(self, uploadedParts: list[MockR2UploadedPart]) -> MockR2Object:
        """Complete the multipart upload"""
        if self._aborted:
            raise Exception("Multipart upload has been aborted")
        if self._completed:
            raise Exception("Multipart upload has already been completed")

        sorted_parts = sorted(uploadedParts, key=lambda p: p.partNumber)

        data = b""
        for part in sorted_parts:
            if part.partNumber not in self._parts:
                raise Exception(f"Part {part.partNumber} not found")
            data += self._parts[part.partNumber]

        options = {}
        if self._http_metadata:
            options["httpMetadata"] = {
                "contentType": self._http_metadata.contentType,
            }
        if self._custom_metadata:
            options["customMetadata"] = self._custom_metadata

        result = await self._bucket.put(self.key, data, options)
        self._completed = True

        if self.uploadId in self._bucket._multipart_uploads:
            del self._bucket._multipart_uploads[self.uploadId]

        if result is None:
            raise Exception("Failed to complete multipart upload")
        return result


class MockR2Bucket:
    """
    Mock R2 Bucket for Unit Testing

    Provides an in-memory implementation of the Cloudflare Workers R2 API.
    All operations are async to match the real R2 API.

    Supported operations:
    - head(key) - Get object metadata only
    - get(key, options?) - Get object with body
    - put(key, value, options?) - Store object
    - delete(key | keys[]) - Delete object(s)
    - list(options?) - List objects with pagination
    - createMultipartUpload(key, options?) - Start multipart upload
    - resumeMultipartUpload(key, uploadId) - Resume multipart upload

    Usage:
        from kinglet import MockR2Bucket

        bucket = MockR2Bucket()
        await bucket.put("my-key", b"hello world", {"httpMetadata": {"contentType": "text/plain"}})
        obj = await bucket.get("my-key")
        content = await obj.text()
    """

    def __init__(self):
        self._objects: dict[str, dict[str, Any]] = {}
        self._multipart_uploads: dict[str, MockR2MultipartUpload] = {}

    async def head(self, key: str) -> MockR2Object | None:
        """
        Get object metadata without body

        Args:
            key: Object key

        Returns:
            MockR2Object with metadata, or None if not found
        """
        if key not in self._objects:
            return None

        stored = self._objects[key]
        return MockR2Object(
            key=key,
            size=stored["size"],
            etag=stored["etag"],
            uploaded=stored["uploaded"],
            http_metadata=stored.get("httpMetadata"),
            custom_metadata=stored.get("customMetadata"),
            version=stored.get("version"),
            checksums=stored.get("checksums"),
            storage_class=stored.get("storageClass", "Standard"),
        )

    async def get(
        self, key: str, options: dict[str, Any] | None = None
    ) -> MockR2ObjectBody | None:
        """
        Get object with body

        Args:
            key: Object key
            options: R2GetOptions (onlyIf, range)

        Returns:
            MockR2ObjectBody with body, or None if not found or preconditions not met
        """
        if key not in self._objects:
            return None

        stored = self._objects[key]
        data = stored["data"]
        range_info = None

        # Handle range requests
        if options and "range" in options:
            range_opts = options["range"]
            offset = range_opts.get("offset", 0)
            length = range_opts.get("length")
            suffix = range_opts.get("suffix")

            if suffix is not None:
                data = data[-suffix:]
                offset = max(0, len(stored["data"]) - suffix)
                length = len(data)
            elif length is not None:
                data = data[offset : offset + length]
            else:
                data = data[offset:]

            range_info = R2Range(offset=offset, length=len(data))

        # Handle conditional requests (onlyIf)
        if options and "onlyIf" in options:
            cond = options["onlyIf"]
            if "etagMatches" in cond:
                if stored["etag"] != cond["etagMatches"]:
                    # Precondition failed: return None (like real R2 API for 304/412)
                    return None
            if "etagDoesNotMatch" in cond:
                if stored["etag"] == cond["etagDoesNotMatch"]:
                    # Precondition failed: return None (like real R2 API for 304/412)
                    return None

        return MockR2ObjectBody(
            key=key,
            size=stored["size"],
            etag=stored["etag"],
            uploaded=stored["uploaded"],
            data=data,
            http_metadata=stored.get("httpMetadata"),
            custom_metadata=stored.get("customMetadata"),
            version=stored.get("version"),
            checksums=stored.get("checksums"),
            storage_class=stored.get("storageClass", "Standard"),
            range_info=range_info,
        )

    async def put(
        self,
        key: str,
        value: bytes | str | None,
        options: dict[str, Any] | None = None,
    ) -> MockR2Object | None:
        """
        Store an object

        Args:
            key: Object key
            value: Object data (bytes, string, or None)
            options: R2PutOptions (httpMetadata, customMetadata, checksums, etc.)

        Returns:
            MockR2Object with metadata, or None if conditional put fails
        """
        options = options or {}

        if isinstance(value, str):
            value = value.encode("utf-8")
        elif value is None:
            value = b""

        # Handle conditional put
        if "onlyIf" in options:
            cond = options["onlyIf"]
            existing = self._objects.get(key)

            if "etagMatches" in cond:
                if not existing or existing["etag"] != cond["etagMatches"]:
                    return None
            if "etagDoesNotMatch" in cond:
                if existing and existing["etag"] == cond["etagDoesNotMatch"]:
                    return None

        md5_hash = hashlib.md5(value).hexdigest()
        checksums = R2Checksums(md5=hashlib.md5(value).digest())

        http_metadata = None
        if "httpMetadata" in options:
            hm = options["httpMetadata"]
            http_metadata = R2HTTPMetadata(
                contentType=hm.get("contentType"),
                contentLanguage=hm.get("contentLanguage"),
                contentDisposition=hm.get("contentDisposition"),
                contentEncoding=hm.get("contentEncoding"),
                cacheControl=hm.get("cacheControl"),
            )

        version = str(uuid.uuid4())
        uploaded = datetime.now(UTC)

        self._objects[key] = {
            "data": value,
            "size": len(value),
            "etag": md5_hash,
            "uploaded": uploaded,
            "httpMetadata": http_metadata,
            "customMetadata": options.get("customMetadata", {}),
            "version": version,
            "checksums": checksums,
            "storageClass": options.get("storageClass", "Standard"),
        }

        return MockR2Object(
            key=key,
            size=len(value),
            etag=md5_hash,
            uploaded=uploaded,
            http_metadata=http_metadata,
            custom_metadata=options.get("customMetadata", {}),
            version=version,
            checksums=checksums,
            storage_class=options.get("storageClass", "Standard"),
        )

    async def delete(self, keys: str | list[str]) -> None:
        """
        Delete one or more objects

        Args:
            keys: Single key or list of keys to delete (up to 1000)
        """
        if isinstance(keys, str):
            keys = [keys]

        if len(keys) > 1000:
            raise Exception("Cannot delete more than 1000 keys at once")

        for key in keys:
            if key in self._objects:
                del self._objects[key]

    async def list(self, options: dict[str, Any] | None = None) -> MockR2Objects:
        """
        List objects in the bucket

        Args:
            options: R2ListOptions (limit, prefix, cursor, delimiter, include)

        Returns:
            MockR2Objects with matching objects
        """
        options = options or {}
        limit = min(options.get("limit", 1000), 1000)
        prefix = options.get("prefix", "")
        cursor = options.get("cursor")
        delimiter = options.get("delimiter")
        include = options.get("include", [])

        all_keys = sorted(self._objects.keys())

        if prefix:
            all_keys = [k for k in all_keys if k.startswith(prefix)]

        if cursor:
            start_idx = 0
            for i, k in enumerate(all_keys):
                if k > cursor:
                    start_idx = i
                    break
            all_keys = all_keys[start_idx:]

        delimited_prefixes = []
        if delimiter:
            seen_prefixes = set()
            filtered_keys = []
            for key in all_keys:
                remaining = key[len(prefix) :] if prefix else key
                delim_pos = remaining.find(delimiter)
                if delim_pos >= 0:
                    dir_prefix = prefix + remaining[: delim_pos + 1]
                    if dir_prefix not in seen_prefixes:
                        seen_prefixes.add(dir_prefix)
                        delimited_prefixes.append(dir_prefix)
                else:
                    filtered_keys.append(key)
            all_keys = filtered_keys

        truncated = len(all_keys) > limit
        result_keys = all_keys[:limit]
        next_cursor = result_keys[-1] if truncated and result_keys else None

        objects = []
        for key in result_keys:
            stored = self._objects[key]

            http_metadata = None
            custom_metadata = None
            if "httpMetadata" in include:
                http_metadata = stored.get("httpMetadata")
            if "customMetadata" in include:
                custom_metadata = stored.get("customMetadata")

            objects.append(
                MockR2Object(
                    key=key,
                    size=stored["size"],
                    etag=stored["etag"],
                    uploaded=stored["uploaded"],
                    http_metadata=http_metadata,
                    custom_metadata=custom_metadata,
                )
            )

        return MockR2Objects(
            objects=objects,
            truncated=truncated,
            cursor=next_cursor,
            delimitedPrefixes=sorted(delimited_prefixes),
        )

    def createMultipartUpload(
        self, key: str, options: dict[str, Any] | None = None
    ) -> MockR2MultipartUpload:
        """
        Create a new multipart upload

        Args:
            key: Object key
            options: R2MultipartOptions (httpMetadata, customMetadata, storageClass)

        Returns:
            MockR2MultipartUpload for managing the upload
        """
        options = options or {}
        upload_id = str(uuid.uuid4())

        http_metadata = None
        if "httpMetadata" in options:
            hm = options["httpMetadata"]
            http_metadata = R2HTTPMetadata(
                contentType=hm.get("contentType"),
            )

        upload = MockR2MultipartUpload(
            bucket=self,
            key=key,
            upload_id=upload_id,
            http_metadata=http_metadata,
            custom_metadata=options.get("customMetadata"),
        )

        self._multipart_uploads[upload_id] = upload
        return upload

    def resumeMultipartUpload(self, key: str, uploadId: str) -> MockR2MultipartUpload:
        """
        Resume an existing multipart upload

        Note: Like the real R2 API, this doesn't validate the upload exists.

        Args:
            key: Object key
            uploadId: Upload ID from createMultipartUpload

        Returns:
            MockR2MultipartUpload for managing the upload
        """
        if uploadId in self._multipart_uploads:
            return self._multipart_uploads[uploadId]

        upload = MockR2MultipartUpload(bucket=self, key=key, upload_id=uploadId)
        return upload

    # Utility methods for testing

    def clear(self) -> None:
        """Clear all objects from the bucket (test utility)"""
        self._objects.clear()
        self._multipart_uploads.clear()

    def get_all_keys(self) -> builtins.list[str]:
        """Get all keys in the bucket (test utility)"""
        return list(self._objects.keys())

    def object_count(self) -> int:
        """Get number of objects in the bucket (test utility)"""
        return len(self._objects)
