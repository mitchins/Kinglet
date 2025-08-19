# Binary Upload Utilities

Kinglet provides utilities for handling binary uploads to Cloudflare R2, automatically converting Python bytes to JavaScript ArrayBuffer formats.

## Quick Start

```python
from kinglet import r2_put

# Simple binary upload - automatic conversion
await r2_put(bucket, "file.jpg", file_bytes)

# With metadata
await r2_put(bucket, "document.pdf", pdf_bytes, {
    "content-type": "application/pdf",
    "filename": "document.pdf"
})
```

## Functions

### `r2_put(bucket, key, content, metadata=None)`

Enhanced R2 upload with automatic binary conversion.

- Automatically converts Python bytes to ArrayBuffer for Workers
- Passes through strings and other data unchanged
- Works in local development (no JS runtime needed)

### `bytes_to_arraybuffer(data)`

Convert Python bytes to JavaScript ArrayBuffer.

```python
from kinglet import bytes_to_arraybuffer

upload_data = bytes_to_arraybuffer(file_bytes)
await bucket.put("file.bin", upload_data)
```

### `arraybuffer_to_bytes(array_buffer)`

Convert JavaScript ArrayBuffer back to Python bytes.

```python
from kinglet import arraybuffer_to_bytes

r2_object = await bucket.get("file.bin")
file_bytes = arraybuffer_to_bytes(r2_object.arrayBuffer())
```

## Error Handling

All functions handle environment differences automatically:
- In Workers: Full ArrayBuffer conversion
- In local dev: Returns original data
- Raises `ValueError` on conversion failures

## Migration

Replace manual ArrayBuffer conversion:

```python
# Before
from js import ArrayBuffer, Uint8Array
array_buffer = ArrayBuffer.new(len(file_bytes))
uint8_array = Uint8Array.new(array_buffer)
for i, byte in enumerate(file_bytes):
    uint8_array[i] = byte
await bucket.put("file.jpg", array_buffer)

# After
from kinglet import r2_put
await r2_put(bucket, "file.jpg", file_bytes)
```