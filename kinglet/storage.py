"""
Kinglet Storage Helpers - D1 Database and R2 Storage utilities
"""

def d1_unwrap(obj):
    """
    Unwrap D1 database objects to Python native types
    
    Handles the conversion from Cloudflare Workers' D1 response format
    to Python dictionaries and values.
    """
    if obj is None:
        return {}

    # Handle dict-like results from D1 queries
    if hasattr(obj, 'to_py'):
        try:
            return obj.to_py()
        except Exception as e:
            raise ValueError(f"Failed to unwrap D1 object via .to_py(): {e}")

    # Handle dict access pattern
    if hasattr(obj, 'keys'):
        try:
            return {key: obj[key] for key in obj.keys()}
        except Exception as e:
            raise ValueError(f"Failed to unwrap dict-like object: {e}")

    # Handle known dict type
    if isinstance(obj, dict):
        return obj

    # Raise error for unsupported types
    raise ValueError(f"Cannot unwrap D1 object of type {type(obj).__name__}")

def d1_unwrap_results(results):
    """
    Unwrap D1 query results to list of Python objects
    
    Args:
        results: D1 query results object
        
    Returns:
        List of unwrapped Python objects
    """
    if results is None:
        return []

    # Handle results with .results array
    if hasattr(results, 'results'):
        return [d1_unwrap(row) for row in results.results]

    # Handle direct list of results
    if isinstance(results, list):
        return [d1_unwrap(row) for row in results]

    # Single result
    return [d1_unwrap(results)]

def r2_get_metadata(obj, path, default=None):
    """
    Extract metadata from R2 objects using dot notation.
    
    Args:
        obj: R2 object from get() operation
        path: Dot-separated path to metadata field (e.g., "size", "httpMetadata.contentType")
        default: Default value if path not found
        
    Returns:
        Value at path or default
    """
    if obj is None:
        return default

    current = obj
    for part in path.split('.'):
        if current is None:
            return default

        # Try attribute access first (most common)
        if hasattr(current, part):
            current = getattr(current, part)
            # Check for JavaScript undefined immediately after getattr
            try:
                import js
                if current is js.undefined:
                    return default
            except (ImportError, AttributeError):
                if str(current) == "undefined":
                    return default
        # Then dict access
        elif isinstance(current, dict):
            current = current.get(part)
        # Then JS object bracket access
        else:
            try:
                current = current[part]
            except (KeyError, TypeError, AttributeError):
                return default

    result = current if current is not None else default

    # Check for JavaScript undefined before stringifying
    try:
        import js
        if result is js.undefined:
            return default
    except (ImportError, AttributeError):
        # Fallback: check string representation
        if str(result) == "undefined":
            return default

    return result

def r2_get_content_info(obj):
    """
    Extract common R2 object metadata.
    
    Args:
        obj: R2 object from get() operation
        
    Returns:
        Dict with content_type, size, etag, etc.
    """
    result = {
        'content_type': r2_get_metadata(obj, "httpMetadata.contentType", "application/octet-stream"),
        'size': r2_get_metadata(obj, "size", None),
        'etag': r2_get_metadata(obj, "httpEtag", None),
        'last_modified': r2_get_metadata(obj, "uploaded", None),
        'custom_metadata': r2_get_metadata(obj, "customMetadata", {})
    }

    # Ensure no undefined values leak through
    for key, value in result.items():
        if str(value) == "undefined":
            if key == 'content_type':
                result[key] = "application/octet-stream"
            elif key == 'custom_metadata':
                result[key] = {}
            else:
                result[key] = None

    return result

def bytes_to_arraybuffer(data):
    """
    Convert Python bytes to JavaScript ArrayBuffer for R2/Worker API compatibility
    
    This utility handles the conversion from Python bytes (common in file uploads,
    image processing, etc.) to JavaScript ArrayBuffer format required by
    Cloudflare Workers R2 API.
    
    Args:
        data: Python bytes, bytearray, or already-converted ArrayBuffer
        
    Returns:
        JavaScript ArrayBuffer suitable for R2 uploads
        
    Example:
        # Direct usage:
        upload_data = bytes_to_arraybuffer(file_bytes)
        await bucket.put("path/file.jpg", upload_data)
        
        # Or use enhanced r2_put which calls this automatically:
        await r2_put(bucket, "path/file.jpg", file_bytes)
    """
    # Return early if already an ArrayBuffer or similar JS object
    if not isinstance(data, (bytes, bytearray)):
        return data
    
    try:
        # Import JavaScript types
        from js import Uint8Array, ArrayBuffer
        
        # Create ArrayBuffer of correct size
        array_buffer = ArrayBuffer.new(len(data))
        
        # Create Uint8Array view of the ArrayBuffer
        uint8_array = Uint8Array.new(array_buffer)
        
        # Copy bytes efficiently
        for i, byte in enumerate(data):
            uint8_array[i] = byte
            
        return array_buffer
        
    except ImportError:
        # Not in a Workers environment - return data as-is for local development
        return data
    except Exception as e:
        raise ValueError(f"Failed to convert bytes to ArrayBuffer: {e}")

def arraybuffer_to_bytes(array_buffer):
    """
    Convert JavaScript ArrayBuffer back to Python bytes
    
    This utility handles the reverse conversion from JavaScript ArrayBuffer
    (received from R2 get operations) back to Python bytes for processing.
    
    Args:
        array_buffer: JavaScript ArrayBuffer from R2 or other JS API
        
    Returns:
        Python bytes object
        
    Example:
        r2_object = await bucket.get("path/file.jpg")
        file_bytes = arraybuffer_to_bytes(r2_object.arrayBuffer())
    """
    # Return early if already bytes
    if isinstance(array_buffer, (bytes, bytearray)):
        return bytes(array_buffer)
    
    try:
        # Import JavaScript types  
        from js import Uint8Array
        
        # Create Uint8Array view
        uint8_array = Uint8Array.new(array_buffer)
        
        # Convert to Python bytes
        return bytes([uint8_array[i] for i in range(uint8_array.length)])
        
    except ImportError:
        # Not in Workers environment - assume it's already bytes
        return array_buffer if isinstance(array_buffer, bytes) else bytes(array_buffer)
    except Exception as e:
        raise ValueError(f"Failed to convert ArrayBuffer to bytes: {e}")

async def r2_put(bucket, key: str, content, metadata: dict = None):
    """
    Put object into R2 bucket with metadata and automatic binary conversion
    
    This enhanced r2_put automatically converts Python bytes to JavaScript ArrayBuffer
    for seamless R2 uploads. No more manual conversion needed!
    
    Args:
        bucket: R2 bucket binding
        key: Object key/path
        content: Content to store (bytes automatically converted to ArrayBuffer)
        metadata: Optional custom metadata dict
        
    Returns:
        Result object with etag, etc.
        
    Example:
        # Before (manual conversion required):
        array_buffer = bytes_to_arraybuffer(file_bytes)
        await bucket.put("file.jpg", array_buffer)
        
        # After (automatic conversion):
        await r2_put(bucket, "file.jpg", file_bytes)  # Just works!
    """
    put_options = {}
    if metadata:
        put_options['customMetadata'] = metadata

    # Automatically convert Python bytes to ArrayBuffer for R2 compatibility
    upload_content = bytes_to_arraybuffer(content)
    
    return await bucket.put(key, upload_content, **put_options)

async def r2_delete(bucket, key: str):
    """Delete object from R2 bucket"""
    return await bucket.delete(key)

def r2_list(list_result):
    """
    Convert R2 list result to Python list
    
    Args:
        list_result: Result from bucket.list()
        
    Returns:
        List of object info dicts
    """
    if not list_result or not hasattr(list_result, 'objects'):
        return []

    objects = []
    for obj in list_result.objects:
        obj_info = {
            'key': obj.key,
            'size': getattr(obj, 'size', 0),
            'uploaded': getattr(obj, 'uploaded', None)
        }
        objects.append(obj_info)

    return objects

def _safe_js_object_access(obj, default=None):
    """
    Safely access JavaScript objects that might be undefined
    
    This handles the common case where JavaScript objects need to be
    converted to Python but might have undefined values.
    """
    try:
        # Handle JS undefined
        if hasattr(obj, 'valueOf'):
            result = obj.valueOf()
            if str(result) == "undefined":
                return default

        # Try dict-like access
        if hasattr(obj, 'keys'):
            try:
                return {key: obj[key] for key in obj.keys()}
            except (KeyError, TypeError, AttributeError):
                return default

        # Try direct conversion
        return obj
    except Exception:
        # Fallback: check string representation
        if str(obj) == "undefined":
            return default
        return obj
