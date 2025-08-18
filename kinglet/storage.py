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

async def r2_put(bucket, key: str, content, metadata: dict = None):
    """
    Put object into R2 bucket with metadata
    
    Args:
        bucket: R2 bucket binding
        key: Object key/path
        content: Content to store
        metadata: Optional custom metadata dict
        
    Returns:
        Result object with etag, etc.
    """
    put_options = {}
    if metadata:
        put_options['customMetadata'] = metadata

    return await bucket.put(key, content, **put_options)

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
