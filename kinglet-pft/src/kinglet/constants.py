"""
Constants for the Kinglet framework to eliminate string duplication
and support potential localization in the future.
"""

# Authentication messages
AUTH_REQUIRED = "authentication required"

# Generic status messages
NOT_FOUND = "not found"
CHECK_CONSTRAINT_VIOLATION = "Check constraint violation"

# TOTP authentication paths
TOTP_STEP_UP_PATH = "/auth/totp/step-up"

# File names for schema and migrations
SCHEMA_LOCK_FILE = "schema.lock.json"
MIGRATIONS_FILE = "migrations.json"

# CLI help messages
PYTHON_MODULE_HELP = "Python module containing models"

# Error codes and types
ERROR_TYPES = {
    "NOT_FOUND": "not_found",
    "AUTHENTICATION_REQUIRED": "authentication_required",
    "CONSTRAINT_VIOLATION": "constraint_violation",
}

# HTTP status codes (commonly used)
HTTP_STATUS = {
    "OK": 200,
    "UNAUTHORIZED": 401,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "INTERNAL_SERVER_ERROR": 500,
}
