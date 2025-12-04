"""
Tests for MockR2Bucket implementation

Verifies that the mock R2 bucket behaves like the real Cloudflare R2 Workers API.
"""

import json
from datetime import UTC, datetime

import pytest

from .mock_r2 import (
    MockR2Bucket,
    MockR2Object,
    MockR2ObjectBody,
    MockR2Objects,
    R2MultipartAbortedError,
    R2MultipartCompletedError,
    R2TooManyKeysError,
)


class TestMockR2BucketBasicOperations:
    """Test basic put/get/head/delete operations"""

    @pytest.fixture
    def bucket(self):
        return MockR2Bucket()

    @pytest.mark.asyncio
    async def test_put_and_get_bytes(self, bucket):
        """Test storing and retrieving bytes"""
        data = b"Hello, World!"
        result = await bucket.put("test-key", data)

        assert result is not None
        assert result.key == "test-key"
        assert result.size == len(data)
        assert result.etag is not None

        obj = await bucket.get("test-key")
        assert obj is not None
        assert isinstance(obj, MockR2ObjectBody)

        content = await obj.text()
        assert content == "Hello, World!"

    @pytest.mark.asyncio
    async def test_put_and_get_string(self, bucket):
        """Test storing and retrieving strings"""
        data = "Hello from string!"
        result = await bucket.put("string-key", data)

        assert result is not None
        assert result.size == len(data.encode("utf-8"))

        obj = await bucket.get("string-key")
        content = await obj.text()
        assert content == data

    @pytest.mark.asyncio
    async def test_put_with_http_metadata(self, bucket):
        """Test storing with HTTP metadata"""
        data = b"image data"
        options = {
            "httpMetadata": {
                "contentType": "image/png",
                "cacheControl": "max-age=3600",
            }
        }
        result = await bucket.put("image.png", data, options)

        assert result is not None
        assert result.httpMetadata.contentType == "image/png"
        assert result.httpMetadata.cacheControl == "max-age=3600"

        obj = await bucket.get("image.png")
        assert obj.httpMetadata.contentType == "image/png"

    @pytest.mark.asyncio
    async def test_put_with_custom_metadata(self, bucket):
        """Test storing with custom metadata"""
        data = b"document"
        options = {
            "customMetadata": {
                "author": "Test User",
                "version": "1.0",
            }
        }
        result = await bucket.put("doc.txt", data, options)

        assert result.customMetadata["author"] == "Test User"
        assert result.customMetadata["version"] == "1.0"

    @pytest.mark.asyncio
    async def test_get_nonexistent_key(self, bucket):
        """Test getting a key that doesn't exist"""
        obj = await bucket.get("nonexistent")
        assert obj is None

    @pytest.mark.asyncio
    async def test_head_operation(self, bucket):
        """Test head() returns metadata only"""
        data = b"Some content"
        await bucket.put("head-test", data)

        obj = await bucket.head("head-test")
        assert obj is not None
        assert isinstance(obj, MockR2Object)
        assert not isinstance(obj, MockR2ObjectBody)
        assert obj.key == "head-test"
        assert obj.size == len(data)

    @pytest.mark.asyncio
    async def test_head_nonexistent_key(self, bucket):
        """Test head() on nonexistent key returns None"""
        obj = await bucket.head("nonexistent")
        assert obj is None

    @pytest.mark.asyncio
    async def test_delete_single_key(self, bucket):
        """Test deleting a single key"""
        await bucket.put("to-delete", b"data")
        assert await bucket.get("to-delete") is not None

        await bucket.delete("to-delete")
        assert await bucket.get("to-delete") is None

    @pytest.mark.asyncio
    async def test_delete_multiple_keys(self, bucket):
        """Test deleting multiple keys at once"""
        await bucket.put("key1", b"data1")
        await bucket.put("key2", b"data2")
        await bucket.put("key3", b"data3")

        await bucket.delete(["key1", "key2"])

        assert await bucket.get("key1") is None
        assert await bucket.get("key2") is None
        assert await bucket.get("key3") is not None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_key(self, bucket):
        """Test deleting nonexistent key doesn't raise"""
        # Should not raise
        await bucket.delete("nonexistent")

    @pytest.mark.asyncio
    async def test_delete_max_keys_limit(self, bucket):
        """Test delete() rejects more than 1000 keys"""
        keys = [f"key-{i}" for i in range(1001)]

        with pytest.raises(
            R2TooManyKeysError, match="Cannot delete more than 1000 keys"
        ):
            await bucket.delete(keys)


class TestMockR2BucketBodyMethods:
    """Test R2ObjectBody methods (text, json, arrayBuffer, blob)"""

    @pytest.fixture
    def bucket(self):
        return MockR2Bucket()

    @pytest.mark.asyncio
    async def test_arraybuffer(self, bucket):
        """Test arrayBuffer() method"""
        data = b"\x00\x01\x02\x03"
        await bucket.put("binary", data)

        obj = await bucket.get("binary")
        result = await obj.arrayBuffer()
        assert result == data

    @pytest.mark.asyncio
    async def test_json(self, bucket):
        """Test json() method"""
        data = {"name": "test", "value": 42}
        await bucket.put("data.json", json.dumps(data))

        obj = await bucket.get("data.json")
        result = await obj.json()
        assert result == data

    @pytest.mark.asyncio
    async def test_blob(self, bucket):
        """Test blob() method"""
        data = b"blob data"
        await bucket.put("blob", data)

        obj = await bucket.get("blob")
        result = await obj.blob()
        assert result == data

    @pytest.mark.asyncio
    async def test_body_used_tracking(self, bucket):
        """Test bodyUsed property"""
        await bucket.put("test", b"data")

        obj = await bucket.get("test")
        assert obj.bodyUsed is False

        await obj.text()
        assert obj.bodyUsed is True


class TestMockR2BucketRangeRequests:
    """Test range request functionality"""

    @pytest.fixture
    def bucket(self):
        return MockR2Bucket()

    @pytest.mark.asyncio
    async def test_range_with_offset_and_length(self, bucket):
        """Test range request with offset and length"""
        data = b"0123456789"
        await bucket.put("range-test", data)

        obj = await bucket.get("range-test", {"range": {"offset": 2, "length": 3}})
        content = await obj.arrayBuffer()
        assert content == b"234"
        assert obj.range is not None
        assert obj.range.offset == 2
        assert obj.range.length == 3

    @pytest.mark.asyncio
    async def test_range_with_suffix(self, bucket):
        """Test range request with suffix (last N bytes)"""
        data = b"0123456789"
        await bucket.put("suffix-test", data)

        obj = await bucket.get("suffix-test", {"range": {"suffix": 3}})
        content = await obj.arrayBuffer()
        assert content == b"789"

    @pytest.mark.asyncio
    async def test_range_with_offset_only(self, bucket):
        """Test range request with offset only (to end)"""
        data = b"0123456789"
        await bucket.put("offset-test", data)

        obj = await bucket.get("offset-test", {"range": {"offset": 5}})
        content = await obj.arrayBuffer()
        assert content == b"56789"


class TestMockR2BucketConditionalOperations:
    """Test conditional get/put operations"""

    @pytest.fixture
    def bucket(self):
        return MockR2Bucket()

    @pytest.mark.asyncio
    async def test_conditional_get_etag_matches(self, bucket):
        """Test conditional get with matching etag"""
        result = await bucket.put("cond-test", b"data")
        etag = result.etag

        # Should return full object when etag matches
        obj = await bucket.get("cond-test", {"onlyIf": {"etagMatches": etag}})
        assert isinstance(obj, MockR2ObjectBody)
        assert await obj.text() == "data"

    @pytest.mark.asyncio
    async def test_conditional_get_etag_no_match(self, bucket):
        """Test conditional get with non-matching etag returns None"""
        await bucket.put("cond-test", b"data")

        # Should return None when etag doesn't match (precondition failed)
        obj = await bucket.get("cond-test", {"onlyIf": {"etagMatches": "wrong-etag"}})
        assert obj is None

    @pytest.mark.asyncio
    async def test_conditional_put_etag_matches(self, bucket):
        """Test conditional put with matching etag (update)"""
        result1 = await bucket.put("update-test", b"original")
        etag = result1.etag

        # Should succeed when etag matches
        result2 = await bucket.put(
            "update-test", b"updated", {"onlyIf": {"etagMatches": etag}}
        )
        assert result2 is not None

        obj = await bucket.get("update-test")
        assert await obj.text() == "updated"

    @pytest.mark.asyncio
    async def test_conditional_put_etag_no_match(self, bucket):
        """Test conditional put with non-matching etag fails"""
        await bucket.put("update-test", b"original")

        # Should fail when etag doesn't match
        result = await bucket.put(
            "update-test", b"updated", {"onlyIf": {"etagMatches": "wrong-etag"}}
        )
        assert result is None

        # Original data should be unchanged
        obj = await bucket.get("update-test")
        assert await obj.text() == "original"


class TestMockR2BucketList:
    """Test list() operation with pagination and filtering"""

    @pytest.fixture
    def bucket(self):
        return MockR2Bucket()

    @pytest.mark.asyncio
    async def test_list_all_objects(self, bucket):
        """Test listing all objects"""
        await bucket.put("a", b"1")
        await bucket.put("b", b"2")
        await bucket.put("c", b"3")

        result = await bucket.list()
        assert isinstance(result, MockR2Objects)
        assert len(result.objects) == 3
        assert result.truncated is False

    @pytest.mark.asyncio
    async def test_list_with_prefix(self, bucket):
        """Test listing with prefix filter"""
        await bucket.put("images/cat.jpg", b"cat")
        await bucket.put("images/dog.jpg", b"dog")
        await bucket.put("documents/readme.txt", b"readme")

        result = await bucket.list({"prefix": "images/"})
        assert len(result.objects) == 2
        assert all(obj.key.startswith("images/") for obj in result.objects)

    @pytest.mark.asyncio
    async def test_list_with_limit(self, bucket):
        """Test listing with limit"""
        for i in range(10):
            await bucket.put(f"key-{i:02d}", b"data")

        result = await bucket.list({"limit": 3})
        assert len(result.objects) == 3
        assert result.truncated is True
        assert result.cursor is not None

    @pytest.mark.asyncio
    async def test_list_with_cursor_pagination(self, bucket):
        """Test paginated listing with cursor"""
        for i in range(5):
            await bucket.put(f"key-{i}", b"data")

        # First page
        result1 = await bucket.list({"limit": 2})
        assert len(result1.objects) == 2
        assert result1.truncated is True

        # Second page
        result2 = await bucket.list({"limit": 2, "cursor": result1.cursor})
        assert len(result2.objects) == 2

        # Third page (last)
        result3 = await bucket.list({"limit": 2, "cursor": result2.cursor})
        assert len(result3.objects) == 1
        assert result3.truncated is False

    @pytest.mark.asyncio
    async def test_list_with_delimiter(self, bucket):
        """Test hierarchical listing with delimiter"""
        await bucket.put("photos/2023/jan/pic1.jpg", b"pic1")
        await bucket.put("photos/2023/jan/pic2.jpg", b"pic2")
        await bucket.put("photos/2023/feb/pic3.jpg", b"pic3")
        await bucket.put("photos/readme.txt", b"readme")

        result = await bucket.list({"prefix": "photos/", "delimiter": "/"})

        # Should have one file and one "directory" prefix
        assert len(result.objects) == 1  # readme.txt
        assert result.objects[0].key == "photos/readme.txt"
        assert "photos/2023/" in result.delimitedPrefixes

    @pytest.mark.asyncio
    async def test_list_with_include_metadata(self, bucket):
        """Test listing with metadata inclusion"""
        await bucket.put(
            "with-meta",
            b"data",
            {
                "httpMetadata": {"contentType": "text/plain"},
                "customMetadata": {"author": "test"},
            },
        )

        # Without include - metadata should not have values
        result1 = await bucket.list()
        assert (
            result1.objects[0].httpMetadata is None
            or result1.objects[0].httpMetadata.contentType is None
        )

        # With include - metadata should be present
        result2 = await bucket.list({"include": ["httpMetadata", "customMetadata"]})
        assert result2.objects[0].httpMetadata is not None
        assert result2.objects[0].httpMetadata.contentType == "text/plain"
        assert result2.objects[0].customMetadata["author"] == "test"

    @pytest.mark.asyncio
    async def test_list_empty_bucket(self, bucket):
        """Test listing empty bucket"""
        result = await bucket.list()
        assert len(result.objects) == 0
        assert result.truncated is False

    @pytest.mark.asyncio
    async def test_list_lexicographic_order(self, bucket):
        """Test that list returns objects in lexicographic order"""
        await bucket.put("zebra", b"z")
        await bucket.put("apple", b"a")
        await bucket.put("mango", b"m")

        result = await bucket.list()
        keys = [obj.key for obj in result.objects]
        assert keys == ["apple", "mango", "zebra"]


class TestMockR2MultipartUpload:
    """Test multipart upload functionality"""

    @pytest.fixture
    def bucket(self):
        return MockR2Bucket()

    @pytest.mark.asyncio
    async def test_basic_multipart_upload(self, bucket):
        """Test basic multipart upload flow"""
        upload = bucket.createMultipartUpload("large-file")
        assert upload.key == "large-file"
        assert upload.uploadId is not None

        # Upload parts
        part1 = await upload.uploadPart(1, b"Hello, ")
        part2 = await upload.uploadPart(2, b"World!")

        assert part1.partNumber == 1
        assert part2.partNumber == 2

        # Complete upload
        result = await upload.complete([part1, part2])
        assert result.key == "large-file"

        # Verify object exists
        obj = await bucket.get("large-file")
        content = await obj.text()
        assert content == "Hello, World!"

    @pytest.mark.asyncio
    async def test_multipart_upload_with_metadata(self, bucket):
        """Test multipart upload with metadata"""
        upload = bucket.createMultipartUpload(
            "file-with-meta",
            {
                "httpMetadata": {"contentType": "video/mp4"},
                "customMetadata": {"duration": "120"},
            },
        )

        part = await upload.uploadPart(1, b"video data")
        await upload.complete([part])

        obj = await bucket.get("file-with-meta")
        assert obj.httpMetadata.contentType == "video/mp4"

    @pytest.mark.asyncio
    async def test_multipart_upload_abort(self, bucket):
        """Test aborting multipart upload"""
        upload = bucket.createMultipartUpload("abort-test")
        await upload.uploadPart(1, b"data")

        await upload.abort()

        # Trying to upload after abort should fail
        with pytest.raises(R2MultipartAbortedError, match="aborted"):
            await upload.uploadPart(2, b"more data")

    @pytest.mark.asyncio
    async def test_multipart_upload_complete_after_abort_fails(self, bucket):
        """Test that completing aborted upload fails"""
        upload = bucket.createMultipartUpload("abort-complete-test")
        part = await upload.uploadPart(1, b"data")
        await upload.abort()

        with pytest.raises(R2MultipartAbortedError, match="aborted"):
            await upload.complete([part])

    @pytest.mark.asyncio
    async def test_multipart_upload_complete_twice_fails(self, bucket):
        """Test that completing upload twice fails"""
        upload = bucket.createMultipartUpload("double-complete")
        part = await upload.uploadPart(1, b"data")
        await upload.complete([part])

        with pytest.raises(R2MultipartCompletedError, match="already been completed"):
            await upload.complete([part])

    @pytest.mark.asyncio
    async def test_resume_multipart_upload(self, bucket):
        """Test resuming multipart upload"""
        upload = bucket.createMultipartUpload("resume-test")
        upload_id = upload.uploadId

        part1 = await upload.uploadPart(1, b"part1")

        # Resume the upload
        resumed = bucket.resumeMultipartUpload("resume-test", upload_id)
        part2 = await resumed.uploadPart(2, b"part2")

        await resumed.complete([part1, part2])

        obj = await bucket.get("resume-test")
        content = await obj.text()
        assert content == "part1part2"


class TestMockR2BucketUtilities:
    """Test utility methods for testing"""

    @pytest.fixture
    def bucket(self):
        return MockR2Bucket()

    @pytest.mark.asyncio
    async def test_clear(self, bucket):
        """Test clear() removes all objects"""
        await bucket.put("key1", b"1")
        await bucket.put("key2", b"2")

        bucket.clear()

        assert bucket.object_count() == 0
        assert await bucket.get("key1") is None

    @pytest.mark.asyncio
    async def test_get_all_keys(self, bucket):
        """Test get_all_keys() returns all keys"""
        await bucket.put("a", b"1")
        await bucket.put("b", b"2")
        await bucket.put("c", b"3")

        keys = bucket.get_all_keys()
        assert set(keys) == {"a", "b", "c"}

    @pytest.mark.asyncio
    async def test_object_count(self, bucket):
        """Test object_count() returns correct count"""
        assert bucket.object_count() == 0

        await bucket.put("key1", b"1")
        assert bucket.object_count() == 1

        await bucket.put("key2", b"2")
        assert bucket.object_count() == 2

        await bucket.delete("key1")
        assert bucket.object_count() == 1


class TestMockR2ObjectMetadata:
    """Test R2Object metadata properties"""

    @pytest.fixture
    def bucket(self):
        return MockR2Bucket()

    @pytest.mark.asyncio
    async def test_etag_format(self, bucket):
        """Test etag and httpEtag formats"""
        result = await bucket.put("etag-test", b"data")

        # etag should be raw hash
        assert '"' not in result.etag

        # httpEtag should be quoted for HTTP headers
        assert result.httpEtag.startswith('"')
        assert result.httpEtag.endswith('"')

    @pytest.mark.asyncio
    async def test_uploaded_timestamp(self, bucket):
        """Test uploaded timestamp is set"""
        before = datetime.now(UTC)
        result = await bucket.put("time-test", b"data")
        after = datetime.now(UTC)

        assert result.uploaded is not None
        assert before <= result.uploaded <= after

    @pytest.mark.asyncio
    async def test_version(self, bucket):
        """Test version is unique UUID"""
        result1 = await bucket.put("v-test", b"data1")
        result2 = await bucket.put("v-test", b"data2")

        assert result1.version is not None
        assert result2.version is not None
        assert result1.version != result2.version

    @pytest.mark.asyncio
    async def test_storage_class(self, bucket):
        """Test storage class defaults and custom"""
        result1 = await bucket.put("default-class", b"data")
        assert result1.storageClass == "Standard"

        result2 = await bucket.put(
            "ia-class", b"data", {"storageClass": "InfrequentAccess"}
        )
        assert result2.storageClass == "InfrequentAccess"

    @pytest.mark.asyncio
    async def test_write_http_metadata(self, bucket):
        """Test writeHttpMetadata method"""
        await bucket.put(
            "headers-test",
            b"data",
            {
                "httpMetadata": {
                    "contentType": "application/json",
                    "cacheControl": "no-cache",
                }
            },
        )

        obj = await bucket.get("headers-test")
        headers = {}
        obj.writeHttpMetadata(headers)

        assert headers["Content-Type"] == "application/json"
        assert headers["Cache-Control"] == "no-cache"


class TestMockR2Integration:
    """Integration tests simulating real usage patterns"""

    @pytest.fixture
    def bucket(self):
        return MockR2Bucket()

    @pytest.mark.asyncio
    async def test_file_upload_download_workflow(self, bucket):
        """Test typical file upload/download workflow"""
        # Upload file with metadata
        file_data = b"PDF content here..."
        await bucket.put(
            "documents/report.pdf",
            file_data,
            {
                "httpMetadata": {"contentType": "application/pdf"},
                "customMetadata": {"author": "John Doe", "pages": "10"},
            },
        )

        # Get file info without downloading
        info = await bucket.head("documents/report.pdf")
        assert info.size == len(file_data)
        assert info.httpMetadata.contentType == "application/pdf"

        # Download file
        obj = await bucket.get("documents/report.pdf")
        content = await obj.arrayBuffer()
        assert content == file_data

    @pytest.mark.asyncio
    async def test_image_gallery_workflow(self, bucket):
        """Test image gallery with listing and thumbnails"""
        # Upload multiple images
        for i in range(5):
            await bucket.put(
                f"gallery/image-{i}.jpg",
                f"image-{i}-data".encode(),
                {
                    "httpMetadata": {"contentType": "image/jpeg"},
                    "customMetadata": {"width": "1920", "height": "1080"},
                },
            )

        # List all images
        result = await bucket.list(
            {"prefix": "gallery/", "include": ["httpMetadata", "customMetadata"]}
        )

        assert len(result.objects) == 5
        for obj in result.objects:
            assert obj.httpMetadata.contentType == "image/jpeg"
            assert obj.customMetadata["width"] == "1920"

    @pytest.mark.asyncio
    async def test_cache_with_etag_workflow(self, bucket):
        """Test cache validation using etag"""
        # Initial upload
        result = await bucket.put("cached-data", b"original content")
        etag = result.etag

        # Simulate cache check - etag matches, no need to download body
        # When etagDoesNotMatch condition is met (etag matches), get() returns None
        obj = await bucket.get("cached-data", {"onlyIf": {"etagDoesNotMatch": etag}})
        assert obj is None  # Precondition not met (304 Not Modified equivalent)

        # Update content
        await bucket.put("cached-data", b"new content")

        # Now etag doesn't match - should get full body
        obj2 = await bucket.get("cached-data", {"onlyIf": {"etagDoesNotMatch": etag}})
        assert isinstance(obj2, MockR2ObjectBody)
        assert await obj2.text() == "new content"
