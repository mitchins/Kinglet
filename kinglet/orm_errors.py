"""
Kinglet ORM Error Taxonomy

Normalized exception hierarchy for predictable error handling.
Maps D1/SQLite errors to semantic ORM exceptions.
"""

import re
from typing import Optional, Dict, List, Set


class ConstraintRegistry:
    """
    Registry for table constraints to enable bulletproof error classification
    
    Stores mapping of constraint names to fields, allowing precise error field
    extraction even when database error messages are inconsistent.
    
    Usage:
        # Register constraints during model registration or migration
        registry = ConstraintRegistry()
        registry.register_table("users", {
            "uq_users_email": ["email"],
            "uq_users_username": ["username"], 
            "uq_users_email_tenant": ["email", "tenant_id"],
            "fk_users_tenant": ["tenant_id"]
        })
        
        # Later, classifier uses registry for precise field extraction
        error_info = registry.get_constraint_info("users", "uq_users_email")
        # Returns: {"fields": ["email"], "type": "unique"}
    """
    
    def __init__(self):
        # table_name -> constraint_name -> constraint_info
        self._constraints: Dict[str, Dict[str, Dict]] = {}
        
    def register_table(self, table_name: str, constraints: Dict[str, List[str]]) -> None:
        """
        Register constraints for a table
        
        Args:
            table_name: Name of the table
            constraints: Dict mapping constraint names to field lists
                        
        Example:
            registry.register_table("users", {
                "uq_users_email": ["email"],
                "fk_users_tenant": ["tenant_id"], 
                "ck_users_age": ["age"]
            })
        """
        if table_name not in self._constraints:
            self._constraints[table_name] = {}
            
        for constraint_name, fields in constraints.items():
            constraint_type = self._infer_constraint_type(constraint_name)
            self._constraints[table_name][constraint_name] = {
                "fields": fields,
                "type": constraint_type,
                "table": table_name
            }
            
    def register_constraint(
        self, 
        table_name: str, 
        constraint_name: str, 
        fields: List[str],
        constraint_type: Optional[str] = None
    ) -> None:
        """
        Register a single constraint
        
        Args:
            table_name: Name of the table
            constraint_name: Name of the constraint  
            fields: List of field names involved in constraint
            constraint_type: Type hint (unique, foreign_key, check, not_null)
        """
        if table_name not in self._constraints:
            self._constraints[table_name] = {}
            
        if constraint_type is None:
            constraint_type = self._infer_constraint_type(constraint_name)
            
        self._constraints[table_name][constraint_name] = {
            "fields": fields,
            "type": constraint_type,
            "table": table_name
        }
        
    def get_constraint_info(self, table_name: str, constraint_name: str) -> Optional[Dict]:
        """
        Get constraint information by table and constraint name
        
        Returns:
            Dict with fields, type, table info or None if not found
        """
        return self._constraints.get(table_name, {}).get(constraint_name)
        
    def find_constraint_by_fields(self, table_name: str, fields: List[str]) -> Optional[Dict]:
        """
        Find constraint by matching field list
        
        Useful when you know the fields involved but not the constraint name.
        """
        table_constraints = self._constraints.get(table_name, {})
        fields_set = set(fields)
        
        for constraint_info in table_constraints.values():
            if set(constraint_info["fields"]) == fields_set:
                return constraint_info
                
        return None
        
    def get_table_constraints(self, table_name: str) -> Dict[str, Dict]:
        """Get all constraints for a table"""
        return self._constraints.get(table_name, {})
        
    def list_tables(self) -> List[str]:
        """List all registered tables"""
        return list(self._constraints.keys())
        
    def _infer_constraint_type(self, constraint_name: str) -> str:
        """
        Infer constraint type from naming convention
        
        Conventions:
        - uq_* or *_unique -> unique
        - fk_* or *_fkey -> foreign_key  
        - ck_* or *_check -> check
        - nn_* or *_not_null -> not_null
        - pk_* or *_pkey -> primary_key
        """
        name_lower = constraint_name.lower()
        
        if name_lower.startswith('uq_') or '_unique' in name_lower:
            return "unique"
        elif name_lower.startswith('fk_') or '_fkey' in name_lower or '_foreign' in name_lower:
            return "foreign_key"
        elif name_lower.startswith('ck_') or '_check' in name_lower:
            return "check"
        elif name_lower.startswith('nn_') or '_not_null' in name_lower:
            return "not_null"
        elif name_lower.startswith('pk_') or '_pkey' in name_lower or '_primary' in name_lower:
            return "primary_key"
        else:
            return "unknown"


# Global constraint registry instance
_global_constraint_registry = ConstraintRegistry()


def get_constraint_registry() -> ConstraintRegistry:
    """Get the global constraint registry instance"""
    return _global_constraint_registry


class ORMError(Exception):
    """Base exception for all ORM-related errors"""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error


class ValidationError(ORMError):
    """Field validation failed"""
    
    def __init__(self, field_name: str, message: str, value=None):
        self.field_name = field_name
        self.value = value
        super().__init__(f"Validation failed for field '{field_name}': {message}")


class IntegrityError(ORMError):
    """Database integrity constraint violation"""
    pass


class UniqueViolationError(IntegrityError):
    """UNIQUE constraint violation"""
    
    def __init__(self, field_name: Optional[str] = None, message: str = None, original_error: Optional[Exception] = None):
        self.field_name = field_name
        if message is None:
            if field_name:
                message = f"Unique constraint violation on field '{field_name}'"
            else:
                message = "Unique constraint violation"
        super().__init__(message, original_error)


class NotNullViolationError(IntegrityError):
    """NOT NULL constraint violation"""
    
    def __init__(self, field_name: Optional[str] = None, message: str = None, original_error: Optional[Exception] = None):
        self.field_name = field_name
        if message is None:
            if field_name:
                message = f"NOT NULL constraint violation on field '{field_name}'"
            else:
                message = "NOT NULL constraint violation"
        super().__init__(message, original_error)


class ForeignKeyViolationError(IntegrityError):
    """FOREIGN KEY constraint violation"""
    
    def __init__(self, field_name: Optional[str] = None, message: str = None, original_error: Optional[Exception] = None):
        self.field_name = field_name
        if message is None:
            if field_name:
                message = f"Foreign key constraint violation on field '{field_name}'"
            else:
                message = "Foreign key constraint violation"
        super().__init__(message, original_error)


class CheckViolationError(IntegrityError):
    """CHECK constraint violation"""
    pass


class QueryError(ORMError):
    """Query execution failed"""
    pass


class DoesNotExistError(ORMError):
    """Requested object does not exist"""
    
    def __init__(self, model_name: str, **kwargs):
        self.model_name = model_name
        self.lookup_kwargs = kwargs
        
        if kwargs:
            lookup_str = ", ".join(f"{k}={v}" for k, v in kwargs.items())
            message = f"{model_name} matching {lookup_str} does not exist"
        else:
            message = f"{model_name} does not exist"
            
        super().__init__(message)


class MultipleObjectsReturnedError(ORMError):
    """Query returned multiple objects when one was expected"""
    
    def __init__(self, model_name: str, count: int):
        self.model_name = model_name
        self.count = count
        super().__init__(f"Query returned {count} {model_name} objects, expected 1")


class RetryableError(ORMError):
    """Transient error that may succeed on retry"""
    
    def __init__(self, message: str, retry_after: Optional[float] = None, original_error: Optional[Exception] = None):
        self.retry_after = retry_after  # Suggested retry delay in seconds
        super().__init__(message, original_error)


class DeadlockError(RetryableError):
    """Database deadlock detected"""
    
    def __init__(self, message: str = None, original_error: Optional[Exception] = None):
        if message is None:
            message = "Database deadlock detected - retry recommended"
        super().__init__(message, retry_after=0.1, original_error=original_error)


class TimeoutError(RetryableError):
    """Operation timed out"""
    
    def __init__(self, message: str = None, original_error: Optional[Exception] = None):
        if message is None:
            message = "Database operation timed out - retry recommended"
        super().__init__(message, retry_after=1.0, original_error=original_error)


class D1ErrorClassifier:
    """
    Classifies D1/SQLite errors into semantic ORM exceptions with constraint registry
    
    Uses constraint registry first for precise field extraction, then falls back
    to message parsing for backward compatibility.
    """
    
    # SQLite/D1 error patterns (fallback when registry lookup fails)
    UNIQUE_PATTERNS = [
        r"UNIQUE constraint failed: (\w+)\.(\w+)",
        r"column (\w+) is not unique", 
        r"UNIQUE constraint failed"
    ]
    
    NOT_NULL_PATTERNS = [
        r"NOT NULL constraint failed: (\w+)\.(\w+)",
        r"column (\w+) may not be NULL",
        r"NOT NULL constraint failed"
    ]
    
    FOREIGN_KEY_PATTERNS = [
        r"FOREIGN KEY constraint failed",
        r"foreign key constraint failed",
        r"no such table: (\w+)"
    ]
    
    CHECK_PATTERNS = [
        r"CHECK constraint failed: (\w+)",
        r"constraint failed"
    ]
    
    DEADLOCK_PATTERNS = [
        r"database is locked",
        r"deadlock", 
        r"abort due to conflict"
    ]
    
    TIMEOUT_PATTERNS = [
        r"timeout",
        r"operation timed out",
        r"request timeout"
    ]
    
    # Enhanced patterns for constraint registry extraction
    CONSTRAINT_NAME_PATTERNS = [
        r"constraint `([^`]+)` failed",           # Modern SQLite: constraint `uq_users_email` failed
        r"CONSTRAINT\s+(\w+)\s+failed",          # Standard: CONSTRAINT uq_users_email failed  
        r"constraint failed:\s*(\w+)",          # Alternative: constraint failed: uq_users_email
        r"UNIQUE constraint `([^`]+)` failed",   # UNIQUE constraint `uq_users_email` failed
        r"CHECK constraint `([^`]+)` failed",    # CHECK constraint `ck_users_age` failed
    ]
    
    @classmethod
    def classify_error(cls, error: Exception, registry: Optional[ConstraintRegistry] = None) -> ORMError:
        """
        Classify a database error into appropriate ORM exception with constraint registry
        
        Args:
            error: Original database exception
            registry: Optional constraint registry for precise field extraction
            
        Returns:
            Appropriate ORM exception with context
        """
        if registry is None:
            registry = get_constraint_registry()
            
        error_msg = str(error)
        error_msg_lower = error_msg.lower()
        
        # Step 1: Try to extract constraint name from error message
        constraint_info = cls._extract_constraint_info(error_msg, registry)
        
        if constraint_info:
            # Use registry for precise field extraction
            constraint_type = constraint_info["type"]
            fields = constraint_info["fields"]
            
            if constraint_type == "unique":
                # For multiple fields, join them or use primary field
                field_name = fields[0] if len(fields) == 1 else None
                return UniqueViolationError(field_name=field_name, original_error=error)
                
            elif constraint_type == "not_null":
                field_name = fields[0] if fields else None
                return NotNullViolationError(field_name=field_name, original_error=error)
                
            elif constraint_type == "foreign_key":
                field_name = fields[0] if fields else None
                return ForeignKeyViolationError(field_name=field_name, original_error=error)
                
            elif constraint_type == "check":
                return CheckViolationError("Check constraint violation", original_error=error)
                
        # Step 2: Fall back to pattern matching for backward compatibility
        # Check for unique constraint violations
        for pattern in cls.UNIQUE_PATTERNS:
            match = re.search(pattern, error_msg_lower, re.IGNORECASE)
            if match:
                field_name = None
                if match.groups():
                    # Extract field name if available (table.column format)
                    if len(match.groups()) >= 2:
                        field_name = match.group(2)
                    else:
                        field_name = match.group(1)
                return UniqueViolationError(field_name=field_name, original_error=error)
        
        # Check for NOT NULL violations
        for pattern in cls.NOT_NULL_PATTERNS:
            match = re.search(pattern, error_msg_lower, re.IGNORECASE)
            if match:
                field_name = None
                if match.groups():
                    if len(match.groups()) >= 2:
                        field_name = match.group(2)
                    else:
                        field_name = match.group(1)
                return NotNullViolationError(field_name=field_name, original_error=error)
        
        # Check for foreign key violations
        for pattern in cls.FOREIGN_KEY_PATTERNS:
            if re.search(pattern, error_msg_lower, re.IGNORECASE):
                return ForeignKeyViolationError(original_error=error)
        
        # Check for check constraint violations
        for pattern in cls.CHECK_PATTERNS:
            if re.search(pattern, error_msg_lower, re.IGNORECASE):
                return CheckViolationError("Check constraint violation", original_error=error)
        
        # Check for retryable errors
        for pattern in cls.DEADLOCK_PATTERNS:
            if re.search(pattern, error_msg_lower, re.IGNORECASE):
                return DeadlockError(original_error=error)
        
        for pattern in cls.TIMEOUT_PATTERNS:
            if re.search(pattern, error_msg_lower, re.IGNORECASE):
                return TimeoutError(original_error=error)
        
        # Generic query error
        return QueryError(f"Database query failed: {error}", original_error=error)
        
    @classmethod
    def _extract_constraint_info(cls, error_msg: str, registry: ConstraintRegistry) -> Optional[Dict]:
        """
        Extract constraint information from error message using registry
        
        Args:
            error_msg: Database error message
            registry: Constraint registry to lookup constraint info
            
        Returns:
            Constraint info dict or None if not found
        """
        # Try to extract constraint name from error message
        for pattern in cls.CONSTRAINT_NAME_PATTERNS:
            match = re.search(pattern, error_msg, re.IGNORECASE)
            if match:
                constraint_name = match.group(1)
                
                # Search all tables for this constraint name
                for table_name in registry.list_tables():
                    constraint_info = registry.get_constraint_info(table_name, constraint_name)
                    if constraint_info:
                        return constraint_info
                        
        # Try to extract table.column pattern and find matching constraint
        table_column_match = re.search(r"(\w+)\.(\w+)", error_msg)
        if table_column_match:
            table_name = table_column_match.group(1)
            column_name = table_column_match.group(2)
            
            # Look for constraint involving this field
            constraint_info = registry.find_constraint_by_fields(table_name, [column_name])
            if constraint_info:
                return constraint_info
                
        return None
    
    @classmethod
    def wrap_database_call(cls, func):
        """
        Decorator to wrap database calls with error classification
        
        Usage:
            @D1ErrorClassifier.wrap_database_call
            async def some_db_operation():
                # Database code here
                pass
        """
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                # Check if it's already an ORM error
                if isinstance(e, ORMError):
                    raise
                # Classify and re-raise
                orm_error = cls.classify_error(e)
                raise orm_error from e
                
        return wrapper


def to_problem_json(
    error: ORMError, 
    *, 
    status: int,
    type_uri: str = "about:blank",
    title: str,
    instance: Optional[str] = None,
    extra: Optional[dict] = None,
    redact_in_prod: bool = True,
    is_prod: bool = False
) -> dict:
    """
    Convert ORM error to RFC7807 Problem Details JSON format
    
    Args:
        error: ORM exception to convert
        status: HTTP status code
        type_uri: URI identifying the problem type
        title: Human-readable summary of the problem
        instance: URI reference identifying the specific occurrence
        extra: Additional problem-specific fields
        redact_in_prod: Whether to redact sensitive details in production
        is_prod: Whether running in production mode
        
    Returns:
        RFC7807 compliant problem+json dict
    """
    problem = {
        "type": type_uri,
        "title": title,
        "status": status,
        "detail": str(error),
    }
    
    # Add instance URI if provided
    if instance:
        problem["instance"] = instance
        
    # Add error code
    problem["code"] = error.__class__.__name__
    
    # Add contextual fields based on error type (only in dev mode if redacting)
    if not (redact_in_prod and is_prod):
        if isinstance(error, ValidationError):
            problem.update({
                "field": error.field_name,
                "value": error.value,
                "validation_type": "field_validation"
            })
        
        elif isinstance(error, UniqueViolationError):
            if error.field_name:
                problem["field"] = error.field_name
            problem["constraint_type"] = "unique"
        
        elif isinstance(error, NotNullViolationError):
            if error.field_name:
                problem["field"] = error.field_name
            problem["constraint_type"] = "not_null"
            
        elif isinstance(error, ForeignKeyViolationError):
            if error.field_name:
                problem["field"] = error.field_name
            problem["constraint_type"] = "foreign_key"
        
        elif isinstance(error, DoesNotExistError):
            problem.update({
                "model": error.model_name,
                "lookup": error.lookup_kwargs
            })
            
        elif isinstance(error, MultipleObjectsReturnedError):
            problem.update({
                "model": error.model_name,
                "count": error.count
            })
    
    # Add extra fields
    if extra:
        problem.update(extra)
        
    return problem


# RFC7807 Error Type URIs and Status Code Mapping
ERROR_TYPE_MAP = {
    "ValidationError": (422, "https://errors.kinglet.dev/validation", "Validation failed"),
    "UniqueViolationError": (409, "https://errors.kinglet.dev/unique", "Unique constraint violation"),
    "NotNullViolationError": (400, "https://errors.kinglet.dev/not-null", "Missing required field"),  
    "ForeignKeyViolationError": (409, "https://errors.kinglet.dev/foreign-key", "Foreign key violation"),
    "CheckViolationError": (400, "https://errors.kinglet.dev/check", "Check constraint violation"),
    "DoesNotExistError": (404, "https://errors.kinglet.dev/not-found", "Resource not found"),
    "MultipleObjectsReturnedError": (409, "https://errors.kinglet.dev/multiple", "Multiple results returned"),
    "DeadlockError": (503, "https://errors.kinglet.dev/deadlock", "Database deadlock"),
    "TimeoutError": (503, "https://errors.kinglet.dev/timeout", "Operation timed out"),
    "RetryableError": (503, "https://errors.kinglet.dev/retryable", "Please retry"),
    "QueryError": (500, "https://errors.kinglet.dev/query", "Database error"),
    "IntegrityError": (409, "https://errors.kinglet.dev/integrity", "Data integrity violation"),
}


def get_error_mapping(error: ORMError) -> tuple[int, str, str]:
    """
    Get HTTP status, type URI, and title for an ORM error
    
    Returns:
        (status_code, type_uri, title) tuple
    """
    error_name = error.__class__.__name__
    return ERROR_TYPE_MAP.get(error_name, (500, "https://errors.kinglet.dev/internal", "Internal error"))


def orm_problem_response(
    error: ORMError, 
    *,
    instance: Optional[str] = None,
    extra: Optional[dict] = None,
    is_prod: bool = False
) -> tuple[dict, int, dict]:
    """
    Generate RFC7807 problem+json response for ORM errors
    
    Args:
        error: ORM exception
        instance: URI identifying this specific occurrence
        extra: Additional problem-specific fields
        is_prod: Whether running in production (affects field redaction)
        
    Returns:
        (problem_dict, status_code, headers) tuple for Kinglet responses
    """
    status, type_uri, title = get_error_mapping(error)
    
    problem = to_problem_json(
        error,
        status=status,
        type_uri=type_uri,
        title=title,
        instance=instance,
        extra=extra,
        is_prod=is_prod
    )
    
    headers = {"Content-Type": "application/problem+json"}
    
    # Add Retry-After header for retryable errors
    if isinstance(error, RetryableError) and error.retry_after:
        headers["Retry-After"] = str(int(error.retry_after))
        
    return problem, status, headers


