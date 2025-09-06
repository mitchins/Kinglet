"""
Kinglet Micro-ORM - Compute-optimized database abstraction for Cloudflare D1

Key differences from Peewee/SQLAlchemy:
- Optimized for Cloudflare Workers compute constraints (CPU/memory limits)
- D1-specific optimizations (prepared statements, batch operations)
- Minimal reflection/introspection to reduce startup time
- Schema migrations via wrangler CLI or secure endpoint
- Lean query building with SQL error prevention
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncGenerator, Coroutine
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from .orm_errors import (
    D1ErrorClassifier,
    DoesNotExistError,
    MultipleObjectsReturnedError,
    UniqueViolationError,
    ValidationError,
    get_constraint_registry,
)
from .storage import d1_unwrap, d1_unwrap_results

# Safe SQL identifier validation and quoting
_IDENT = re.compile(r"^[A-Za-z_]\w*$")

# Error message constants for reuse
_FIELD_NOT_EXIST_MSG = "Field '{field_name}' does not exist on {model_name}"
_LIMIT_POSITIVE_MSG = "Limit must be positive"
_LIMIT_EXCEED_MSG = "Limit cannot exceed 10000 (D1 safety limit)"


def _qi(name: str) -> str:
    """Quote and validate SQL identifier to prevent injection"""
    if not _IDENT.fullmatch(name):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return f'"{name}"'  # SQLite identifier quoting


class Field:
    """Base field class for model attributes"""

    def __init__(self, default=None, null=True, unique=False, primary_key=False):
        self.default = default
        self.null = null
        self.unique = unique
        self.primary_key = primary_key
        self.name = None  # Set by ModelMeta

    def to_python(self, value: Any) -> Any:
        """Convert database value to Python value"""
        return value

    def to_db(self, value: Any) -> Any:
        """Convert Python value to database value"""
        return value

    def get_sql_type(self) -> str:
        """Get SQL column type for CREATE TABLE"""
        return "TEXT"

    def validate(self, value: Any) -> Any:
        """Validate and convert field value"""
        if value is None:
            if not self.null:
                raise ValidationError(self.name, "Field cannot be null", value)
            return None
        return self.to_python(value)


class StringField(Field):
    """Text field with optional max length"""

    def __init__(self, max_length: int | None = None, index: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.max_length = max_length
        self.index = index  # Explicit indexing for performance-critical string fields

    def validate(self, value: Any) -> str | None:
        value = super().validate(value)
        if value is None:
            return None

        value = str(value)
        if self.max_length and len(value) > self.max_length:
            raise ValidationError(
                self.name, f"String too long: {len(value)} > {self.max_length}", value
            )
        return value

    def get_sql_type(self) -> str:
        if self.max_length:
            return f"VARCHAR({self.max_length})"
        return "TEXT"


class IntegerField(Field):
    """Integer field with optional index"""

    def __init__(self, index: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.index = index  # Explicit indexing control

    def to_python(self, value: Any) -> int | None:
        if value is None:
            return None
        return int(value)

    def get_sql_type(self) -> str:
        return "INTEGER"


class BooleanField(Field):
    """Boolean field stored as INTEGER (0/1) in D1"""

    def to_python(self, value: Any) -> bool | None:
        if value is None:
            return None
        return bool(int(value))

    def to_db(self, value: Any) -> int | None:
        if value is None:
            return None
        return 1 if value else 0

    def get_sql_type(self) -> str:
        return "INTEGER"


class FloatField(Field):
    """Float/decimal field stored as REAL in D1"""

    def to_python(self, value: Any) -> float | None:
        if value is None:
            return None
        return float(value)

    def to_db(self, value: Any) -> float | None:
        # Reuse to_python to avoid duplication
        return self.to_python(value)

    def get_sql_type(self) -> str:
        return "REAL"

    def validate(self, value: Any) -> float | None:
        """Validate and convert field value"""
        if value is None:
            if not self.null:
                raise ValueError("Field cannot be null")
            return None

        try:
            return float(value)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Invalid float value: {value}") from e


class DateTimeField(Field):
    """DateTime field stored as INTEGER timestamp"""

    def __init__(self, auto_now=False, auto_now_add=False, index=False, **kwargs):
        super().__init__(**kwargs)
        self.auto_now = auto_now
        self.auto_now_add = auto_now_add
        self.index = index  # Explicit indexing control

    def to_python(self, value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        # Handle string datetime format from D1
        if isinstance(value, str):
            try:
                # Try parsing as ISO format datetime string
                return datetime.fromisoformat(value.replace(" ", "T"))
            except ValueError:
                # If that fails, try as Unix timestamp string
                try:
                    return datetime.fromtimestamp(int(value))
                except ValueError:
                    return None
        # Assume Unix timestamp
        try:
            return datetime.fromtimestamp(int(value))
        except (ValueError, TypeError):
            return None

    def to_db(self, value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return int(value.timestamp())
        return int(value)

    def get_sql_type(self) -> str:
        return "INTEGER"


class JSONField(Field):
    """JSON field stored as TEXT"""

    def to_python(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            return json.loads(value)
        return value

    def to_db(self, value: Any) -> str | None:
        if value is None:
            return None
        return json.dumps(value)

    def get_sql_type(self) -> str:
        return "TEXT"


class QuerySet:
    """
    Compute-optimized query builder for D1

    - Pre-builds SQL to minimize CPU during request
    - Uses prepared statements for D1 optimization
    - Validates SQL structure to prevent errors
    """

    def __init__(self, model_class: type[Model], db):
        self.model_class = model_class
        self.db = db
        self._where_conditions = []
        self._order_by = []
        self._limit_count = None
        self._offset_count = None
        self._only_fields = None  # For projection - specific fields to SELECT
        self._values_fields = (
            None  # For values() - return dicts instead of model instances
        )
        # Cache field names for validation
        self._field_names = set(model_class._fields.keys())

    def filter(self, **kwargs) -> QuerySet:
        """Add WHERE conditions with field validation"""
        new_qs = self._clone()
        for key, value in kwargs.items():
            if "__" in key:
                field_name, lookup = key.split("__", 1)
                # Validate field exists to prevent SQL errors
                if field_name not in self._field_names:
                    raise ValueError(
                        _FIELD_NOT_EXIST_MSG.format(
                            field_name=field_name, model_name=self.model_class.__name__
                        )
                    )
                condition = new_qs._build_lookup_condition(field_name, lookup, value)
            else:
                # Validate field exists
                if key not in self._field_names:
                    raise ValueError(
                        _FIELD_NOT_EXIST_MSG.format(
                            field_name=key, model_name=self.model_class.__name__
                        )
                    )
                condition = f"{key} = ?"
            new_qs._where_conditions.append((condition, value))
        return new_qs

    def exclude(self, **kwargs) -> QuerySet:
        """Add WHERE NOT conditions with field validation (opposite of filter)"""
        new_qs = self._clone()
        for key, value in kwargs.items():
            if "__" in key:
                field_name, lookup = key.split("__", 1)
                # Validate field exists to prevent SQL errors
                if field_name not in self._field_names:
                    raise ValueError(
                        _FIELD_NOT_EXIST_MSG.format(
                            field_name=field_name, model_name=self.model_class.__name__
                        )
                    )
                condition = new_qs._build_lookup_condition(field_name, lookup, value)
                # Wrap in NOT for exclude behavior
                condition = f"NOT ({condition})"
            else:
                # Validate field exists
                if key not in self._field_names:
                    raise ValueError(
                        _FIELD_NOT_EXIST_MSG.format(
                            field_name=key, model_name=self.model_class.__name__
                        )
                    )
                condition = f"NOT ({key} = ?)"
            new_qs._where_conditions.append((condition, value))
        return new_qs

    def order_by(self, *fields) -> QuerySet:
        """Add ORDER BY clause with field validation"""
        new_qs = self._clone()
        for field in fields:
            field_name = field[1:] if field.startswith("-") else field
            # Validate field exists
            if field_name not in self._field_names:
                raise ValueError(
                    _FIELD_NOT_EXIST_MSG.format(
                        field_name=field_name, model_name=self.model_class.__name__
                    )
                )

            if field.startswith("-"):
                new_qs._order_by.append(f"{_qi(field_name)} DESC")
            else:
                new_qs._order_by.append(f"{_qi(field_name)} ASC")
        return new_qs

    def limit(self, count: int) -> QuerySet:
        """
        Add LIMIT clause with safety checks

        Enforces maximum limit to prevent expensive queries.
        """
        if count <= 0:
            raise ValueError(_LIMIT_POSITIVE_MSG)
        if count > 10000:  # D1 safety limit
            raise ValueError(_LIMIT_EXCEED_MSG)

        new_qs = self._clone()
        new_qs._limit_count = count
        return new_qs

    def offset(self, count: int) -> QuerySet:
        """
        Add OFFSET clause with safety checks

        Requires ORDER BY for predictable pagination.
        """
        if count < 0:
            raise ValueError("Offset cannot be negative")
        if count > 100000:  # Prevent expensive deep pagination
            raise ValueError("Offset cannot exceed 100000 (performance limit)")

        new_qs = self._clone()
        new_qs._offset_count = count
        return new_qs

    def only(self, *field_names) -> QuerySet:
        """
        Select only specific fields - D1 cost optimization

        D1 Cost Optimization: Reduces columns read per row.
        Instead of SELECT *, only reads requested fields.

        Example:
            # BAD: SELECT * FROM users (all columns charged)
            users = await User.objects.all()

            # GOOD: SELECT email, name FROM users (only 2 columns charged)
            users = await User.objects.only('email', 'name').all()
        """
        # Validate field names
        for field_name in field_names:
            if field_name not in self._field_names:
                raise ValueError(
                    _FIELD_NOT_EXIST_MSG.format(
                        field_name=field_name, model_name=self.model_class.__name__
                    )
                )

        new_qs = self._clone()
        new_qs._only_fields = list(field_names)
        new_qs._values_fields = None  # Clear values mode
        return new_qs

    def values(self, *field_names) -> QuerySet:
        """
        Return dictionaries instead of model instances - D1 cost optimization

        D1 Cost Optimization: Reduces columns read + avoids object instantiation.
        Perfect for API endpoints that only need specific fields.

        Example:
            # Return dicts with only email field
            emails = await User.objects.values('email').all()
            # Returns: [{'email': 'user1@example.com'}, {'email': 'user2@example.com'}]
        """
        if not field_names:
            field_names = list(self._field_names)

        # Validate field names
        for field_name in field_names:
            if field_name not in self._field_names:
                raise ValueError(
                    _FIELD_NOT_EXIST_MSG.format(
                        field_name=field_name, model_name=self.model_class.__name__
                    )
                )

        new_qs = self._clone()
        new_qs._values_fields = list(field_names)
        new_qs._only_fields = None  # Clear only mode
        return new_qs

    async def all(self) -> list[Model]:
        """
        Execute query and return all results

        D1 Optimization: Uses .all() for batch retrieval, same as raw SQL:
        SELECT * FROM table WHERE conditions

        Safety: Automatically applies default limit if none specified.
        """
        # Validate pagination safety
        self._validate_pagination_safety()

        # Apply default limit if none specified (prevent runaway queries)
        if self._limit_count is None:
            limited_qs = self.limit(1000)  # Default safety limit
            sql, params = limited_qs._build_sql()
        else:
            sql, params = self._build_sql()

        try:
            result = await self.db.prepare(sql).bind(*params).all()
            rows = d1_unwrap_results(result)

            # Handle values() mode - return dicts instead of model instances
            if self._values_fields:
                return [
                    {field: row.get(field) for field in self._values_fields}
                    for row in rows
                ]

            # Handle only() mode or normal model instances
            return [self.model_class._from_db(row) for row in rows]
        except Exception as e:
            raise D1ErrorClassifier.classify_error(e) from e

    async def first(self) -> Model | dict[str, Any] | None:
        """
        Execute query and return first result

        D1 Optimization: Uses .first() method, equivalent to:
        SELECT * FROM table WHERE conditions LIMIT 1
        """
        sql, params = self._build_sql()
        # Don't add LIMIT 1 if already present to avoid double-limiting
        if "LIMIT" not in sql.upper():
            sql += " LIMIT 1"
        try:
            result = await self.db.prepare(sql).bind(*params).first()
            if not result:
                return None
            row = d1_unwrap(result)

            # Handle values() mode - return dict instead of model instance
            if self._values_fields:
                return {field: row.get(field) for field in self._values_fields}

            # Handle only() mode or normal model instance
            return self.model_class._from_db(row)
        except Exception as e:
            raise D1ErrorClassifier.classify_error(e) from e

    async def get(self) -> Model:
        """
        Get single object matching query conditions

        Raises:
            DoesNotExistError: If no object matches
            MultipleObjectsReturnedError: If multiple objects match
        """
        # First check if multiple objects exist
        limited_qs = self.limit(2)  # Only need to check if > 1
        results = await limited_qs.all()

        if len(results) == 0:
            # Build lookup kwargs for error message
            lookup_kwargs = {}
            for condition, value in self._where_conditions:
                # Extract field name from condition (simple cases)
                if " = ?" in condition:
                    field_name = condition.split(" = ?")[0]
                    lookup_kwargs[field_name] = value
            raise DoesNotExistError(self.model_class.__name__, **lookup_kwargs)
        elif len(results) > 1:
            raise MultipleObjectsReturnedError(self.model_class.__name__, len(results))
        else:
            return results[0]

    async def count(self) -> int:
        """
        Return count of matching records

        D1 Optimization: Single COUNT(*) query, same as raw SQL:
        SELECT COUNT(*) FROM table WHERE conditions
        No additional overhead vs raw SQL
        """
        table = _qi(self.model_class._meta.table_name)
        base_sql = f"SELECT COUNT(*) as count FROM {table}"  # nosec B608: identifier validated+quoted; values parameterized
        where_clause, params = self._build_where_clause()
        if where_clause:
            sql = f"{base_sql} WHERE {where_clause}"
        else:
            sql = base_sql

        try:
            result = await self.db.prepare(sql).bind(*params).first()
            if result:
                return d1_unwrap(result).get("count", 0)
            return 0
        except Exception as e:
            raise D1ErrorClassifier.classify_error(e) from e

    async def exists(self) -> bool:
        """
        Check if any records match the query - D1 cost optimized

        D1 Cost Optimization: Uses SELECT 1 ... LIMIT 1 instead of COUNT(*)
        Stops at first matching row instead of scanning entire table.

        Cost: 1 row read maximum vs full table scan
        """
        where_clause, params = self._build_where_clause()
        table = _qi(self.model_class._meta.table_name)
        base_sql = f"SELECT 1 FROM {table}"  # nosec B608: identifier validated+quoted; values parameterized

        if where_clause:
            sql = f"{base_sql} WHERE {where_clause} LIMIT 1"
        else:
            sql = f"{base_sql} LIMIT 1"

        try:
            result = await self.db.prepare(sql).bind(*params).first()
            return result is not None
        except Exception as e:
            raise D1ErrorClassifier.classify_error(e) from e

    def _clone(self) -> QuerySet:
        """Create a copy of this QuerySet"""
        new_qs = QuerySet(self.model_class, self.db)
        new_qs._where_conditions = self._where_conditions.copy()
        new_qs._order_by = self._order_by.copy()
        new_qs._limit_count = self._limit_count
        new_qs._offset_count = self._offset_count
        new_qs._only_fields = self._only_fields.copy() if self._only_fields else None
        new_qs._values_fields = (
            self._values_fields.copy() if self._values_fields else None
        )
        return new_qs

    def _build_lookup_condition(self, field_name: str, lookup: str, value: Any) -> str:
        """Build SQL condition for field lookups"""
        op_map = {
            "gt": ">",
            "gte": ">=",
            "lt": "<",
            "lte": "<=",
            "ne": "!=",
        }
        if lookup in op_map:
            return f"{field_name} {op_map[lookup]} ?"
        if lookup == "contains":
            return f"{field_name} LIKE ?"
        if lookup == "icontains":
            return f"LOWER({field_name}) LIKE LOWER(?)"
        if lookup == "startswith":
            return f"{field_name} LIKE ?"
        if lookup == "endswith":
            return f"{field_name} LIKE ?"
        if lookup == "in":
            placeholders = ",".join(["?" for _ in value])
            return f"{field_name} IN ({placeholders})"
        raise ValueError(f"Unsupported lookup: {lookup}")

    def _normalize_like_value(self, cond: str, val: Any) -> Any:
        """Normalize LIKE values for SQL wildcard patterns"""
        if "LIKE" not in cond:
            return val

        s = str(val)

        if self._is_startswith_condition(cond):
            return self._ensure_ends_with_percent(s)

        if "endswith" in cond:
            return self._ensure_starts_with_percent(s)

        if self._is_contains_condition(cond):
            return self._ensure_surrounded_with_percent(s)

        return val

    def _is_startswith_condition(self, cond: str) -> bool:
        """Check if condition is for startswith matching"""
        return "startswith" in cond or cond.endswith("LIKE ?")

    def _is_contains_condition(self, cond: str) -> bool:
        """Check if condition is for contains matching"""
        return "contains" in cond or "icontains" in cond

    def _ensure_ends_with_percent(self, s: str) -> str:
        """Ensure string ends with % for prefix matching"""
        return s if s.endswith("%") else f"{s}%"

    def _ensure_starts_with_percent(self, s: str) -> str:
        """Ensure string starts with % for suffix matching"""
        return s if s.startswith("%") else f"%{s}"

    def _ensure_surrounded_with_percent(self, s: str) -> str:
        """Ensure string is surrounded with % for substring matching"""
        return s if (s.startswith("%") or s.endswith("%")) else f"%{s}%"

    def _build_where_clause(self) -> tuple[str, list[Any]]:
        """Build WHERE clause and parameters with LIKE value normalization"""
        if not self._where_conditions:
            return "", []

        conditions: list[str] = []
        params: list[Any] = []

        for condition, value in self._where_conditions:
            conditions.append(condition)
            if isinstance(value, list | tuple) and "IN" in condition:
                params.extend(value)
            else:
                params.append(self._normalize_like_value(condition, value))

        return " AND ".join(conditions), params

    def _build_sql(self) -> tuple[str, list[Any]]:
        """Build complete SQL query with D1 cost optimization"""
        # D1 Cost Optimization: Use projection instead of SELECT *
        if self._values_fields:
            # values() mode - only select specified fields
            select_fields = ", ".join(_qi(f) for f in self._values_fields)
        elif self._only_fields:
            # only() mode - only select specified fields
            select_fields = ", ".join(_qi(f) for f in self._only_fields)
        else:
            # Default: select all fields (but this should be rare in optimized code)
            select_fields = ", ".join(_qi(f) for f in self.model_class._fields.keys())

        table = _qi(self.model_class._meta.table_name)
        sql = f"SELECT {select_fields} FROM {table}"  # nosec B608: identifier validated+quoted; values parameterized
        params = []

        # WHERE clause
        where_clause, where_params = self._build_where_clause()
        if where_clause:
            sql += f" WHERE {where_clause}"
            params.extend(where_params)

        # ORDER BY clause
        if self._order_by:
            sql += f" ORDER BY {', '.join(self._order_by)}"  # nosec B608: field names already validated+quoted in order_by()

        # LIMIT clause
        if self._limit_count:
            sql += f" LIMIT {self._limit_count}"

        # OFFSET clause
        if self._offset_count:
            sql += f" OFFSET {self._offset_count}"

        return sql, params

    def _validate_pagination_safety(self) -> None:
        """Validate safe pagination practices"""
        if self._offset_count is not None and self._offset_count > 0:
            if not self._order_by:
                raise ValueError(
                    "OFFSET requires ORDER BY for predictable pagination. "
                    "Add .order_by() to your query."
                )

    async def delete(self) -> int:
        """
        Delete all matching records

        D1 Optimization: Single DELETE with WHERE clause, same as raw SQL:
        DELETE FROM table WHERE conditions
        Returns count of deleted rows
        """
        table = _qi(self.model_class._meta.table_name)
        base_sql = f"DELETE FROM {table}"  # nosec B608: identifier validated+quoted; values parameterized
        where_clause, params = self._build_where_clause()

        if where_clause:
            sql = f"{base_sql} WHERE {where_clause}"
        else:
            # Prevent accidental deletion of all records
            raise ValueError(
                "DELETE without WHERE clause not allowed. Use Model.objects.all(db).delete() if you really want to delete all records."
            )

        result = await self.db.prepare(sql).bind(*params).run()
        return getattr(result, "changes", 0)

    def _build_update_set(self, kwargs: dict[str, Any]) -> tuple[list[str], list[Any]]:
        """Validate fields and build SET clauses and params for UPDATE"""
        set_clauses: list[str] = []
        set_params: list[Any] = []
        for field_name, value in kwargs.items():
            if field_name not in self._field_names:
                raise ValueError(
                    _FIELD_NOT_EXIST_MSG.format(
                        field_name=field_name, model_name=self.model_class.__name__
                    )
                )
            field = self.model_class._fields[field_name]
            if field.primary_key:
                raise ValueError(f"Cannot update primary key field '{field_name}'")
            validated_value = field.validate(value)
            db_value = field.to_db(validated_value)
            set_clauses.append(f"{_qi(field_name)} = ?")
            set_params.append(db_value)
        return set_clauses, set_params

    async def update(self, **kwargs) -> int:
        """
        Update all matching records

        D1 Optimization: Single UPDATE with WHERE clause, same as raw SQL:
        UPDATE table SET field1=?, field2=? WHERE conditions
        Returns count of updated rows
        """
        if not kwargs:
            return 0

        # Validate fields and prepare values
        set_clauses, set_params = self._build_update_set(kwargs)

        # Build complete query
        table = _qi(self.model_class._meta.table_name)
        base_sql = f"UPDATE {table} SET {', '.join(set_clauses)}"  # nosec B608: identifier validated+quoted; values parameterized
        where_clause, where_params = self._build_where_clause()

        if where_clause:
            sql = f"{base_sql} WHERE {where_clause}"
            params = set_params + where_params
        else:
            # Prevent accidental update of all records
            raise ValueError(
                "UPDATE without WHERE clause not allowed. Use Model.objects.all(db).update() if you really want to update all records."
            )

        result = await self.db.prepare(sql).bind(*params).run()
        return getattr(result, "changes", 0)


class Manager:
    """Model manager for database operations"""

    def __init__(self, model_class: type[Model]):
        self.model_class = model_class

    def get_queryset(self, db) -> QuerySet:
        """Get base queryset for this model"""
        return QuerySet(self.model_class, db)

    async def create(self, db, **kwargs) -> Model:
        """
        Create and save a new model instance

        D1 Optimization: Single INSERT, same as raw SQL
        """
        instance = self.model_class(**kwargs)
        await instance.save(db)
        return instance

    def _validate_bulk_instances(self, instances: list[Model]) -> None:
        """Validate all instances are the same model type"""
        if not instances:
            return
        first_model = instances[0]
        if not all(isinstance(inst, first_model.__class__) for inst in instances):
            raise ValueError("All instances must be of the same model type")

    def _prepare_field_data(self, instance: Model) -> dict[str, Any]:
        """Prepare field data for a single instance"""
        field_data = {}
        for field_name, field in instance._fields.items():
            value = getattr(instance, field_name, None)

            # Handle auto fields
            if isinstance(field, DateTimeField):
                if field.auto_now_add and not instance._state["saved"]:
                    value = datetime.now()
                    setattr(instance, field_name, value)

            # Validate and convert
            validated_value = field.validate(value)
            db_value = field.to_db(validated_value)
            field_data[field_name] = db_value

        # Skip auto-increment ID fields
        pk_field = instance._get_pk_field()
        if pk_field.name == "id" and getattr(instance, pk_field.name, None) is None:
            field_data.pop("id", None)

        return field_data

    def _prepare_bulk_data(
        self, instances: list[Model]
    ) -> tuple[list[str], list[list[Any]]]:
        """Prepare field names and values for bulk insert"""
        field_names = []
        all_values = []

        for instance in instances:
            field_data = self._prepare_field_data(instance)

            if not field_names:
                field_names = list(field_data.keys())

            values = [field_data.get(name) for name in field_names]
            all_values.append(values)

        return field_names, all_values

    def _create_batch_statements(
        self, db, field_names: list[str], all_values: list[list[Any]]
    ) -> list:
        """Create batch INSERT statements"""
        placeholders = ["?" for _ in field_names]
        table = _qi(self.model_class._meta.table_name)
        quoted_fields = ", ".join(_qi(field) for field in field_names)
        base_sql = (
            f"INSERT INTO {table} ({quoted_fields}) VALUES ({', '.join(placeholders)})"  # nosec B608: identifier validated+quoted; values parameterized
        )

        statements = []
        for values in all_values:
            stmt = db.prepare(base_sql).bind(*values)
            statements.append(stmt)
        return statements

    def _update_instances_with_ids(self, instances: list[Model], results: list) -> None:
        """Update instances with generated primary key IDs"""
        for instance, result in zip(instances, results, strict=False):
            pk_field = instance._get_pk_field()
            if (
                pk_field.name == "id"
                and hasattr(result, "meta")
                and hasattr(result.meta, "last_row_id")
            ):
                instance.id = result.meta.last_row_id
            instance._state["saved"] = True

    async def bulk_create(self, db, instances: list[Model]) -> list[Model]:
        """
        Create multiple instances in a single batch

        D1 Optimization: Single batch INSERT using D1's batch API
        Much more efficient than individual INSERTs for bulk operations
        """
        if not instances:
            return []

        self._validate_bulk_instances(instances)
        field_names, all_values = self._prepare_bulk_data(instances)
        statements = self._create_batch_statements(db, field_names, all_values)

        try:
            results = await db.batch(statements)
            self._update_instances_with_ids(instances, results)
            return instances
        except Exception as e:
            raise D1ErrorClassifier.classify_error(e) from e

    async def get(self, db, **kwargs) -> Model:
        """
        Get single model instance matching the given lookup parameters

        Raises:
            DoesNotExistError: If no object matches the lookup parameters
            MultipleObjectsReturnedError: If multiple objects match
        """
        return await self.get_queryset(db).filter(**kwargs).get()

    async def get_or_create(self, db, defaults=None, **kwargs) -> tuple[Model, bool]:
        """
        Get existing instance or create new one - D1 cost optimized

        D1 Cost Optimization: Try INSERT first, catch errors, no pre-checks.
        Eliminates expensive pre-check SELECT queries.

        Pattern:
        1. Try INSERT (1 row write)
        2. If UniqueViolationError: SELECT existing (1 row read)
        3. Total: 1-2 operations vs 2-3 operations
        """
        create_kwargs = kwargs.copy()
        if defaults:
            create_kwargs.update(defaults)

        try:
            # Try to create first - fail fast on conflicts
            instance = await self.create(db, **create_kwargs)
            return instance, True

        except UniqueViolationError:
            # Only on conflict, fetch the existing record
            instance = await self.get(db, **kwargs)
            if instance:
                return instance, False
            else:
                # Race condition: record was deleted between INSERT and SELECT
                # Retry the INSERT once
                instance = await self.create(db, **create_kwargs)
                return instance, True

    def _collect_unique_fields_from_kwargs(self, kwargs: dict[str, Any]) -> list[str]:
        uniques: list[str] = []
        for fname, f in self.model_class._fields.items():
            if (f.unique or f.primary_key) and fname in kwargs:
                uniques.append(fname)
        return uniques

    def _prepare_validated_data_for_create(self, create_data: dict) -> dict:
        validated: dict = {}
        for fname, f in self.model_class._fields.items():
            if fname in create_data:
                val = create_data[fname]
                if isinstance(f, DateTimeField) and f.auto_now_add and val is None:
                    val = datetime.now()
                v = f.validate(val)
                validated[fname] = f.to_db(v)
        # Skip auto id when not provided
        pk = self.model_class._get_pk_field_static()
        if pk.name == "id" and pk.name not in create_data:
            validated.pop("id", None)
        return validated

    def _build_upsert_sql(self, data: dict) -> tuple[str, list]:
        cols = list(data.keys())
        vals = list(data.values())
        value_exprs: list[str] = []
        bind_vals: list = []
        for v in vals:
            if v is None:
                value_exprs.append("NULL")
            else:
                value_exprs.append("?")
                bind_vals.append(v)
        returning_fields = list(self.model_class._fields.keys())
        sql = f"""
            INSERT OR REPLACE INTO {self.model_class._meta.table_name}
            ({', '.join(cols)}) VALUES ({', '.join(value_exprs)})
            RETURNING {', '.join(returning_fields)}
        """
        return sql, bind_vals

    async def _run_upsert_returning(
        self, db, sql: str, bind_values: list, kwargs: dict[str, Any]
    ) -> tuple[Model, bool]:
        result = await (
            db.prepare(sql).bind(*bind_values) if bind_values else db.prepare(sql)
        ).first()
        if not result:
            raise ValueError("INSERT OR REPLACE with RETURNING returned no rows")
        row_data = d1_unwrap(result)
        instance = self.model_class._from_db(row_data)
        pk_field = self.model_class._get_pk_field_static()
        created = pk_field.name not in kwargs or kwargs.get(pk_field.name) is None
        return instance, created

    def create_or_update(
        self, db, defaults=None, **kwargs
    ) -> Coroutine[Any, Any, tuple[Model, bool]]:
        """
        Create or update using ON CONFLICT DO UPDATE (upsert)

        D1 Optimization: Single upsert statement for idempotent writes.
        Perfect for event-driven Workers where duplicate events may occur.

        Args:
            db: Database connection
            defaults: Fields to update if record exists
            **kwargs: Fields for both create and conflict resolution

        Returns:
            (instance, created) where created=True if new record
        """
        # Perform synchronous validation so callers can catch without awaiting
        unique_fields = self._collect_unique_fields_from_kwargs(kwargs)
        if not unique_fields:
            raise ValueError(
                "create_or_update requires at least one unique field in kwargs"
            )

        async def _inner():
            create_data = kwargs.copy()
            if defaults:
                create_data.update(defaults)

            validated_data = self._prepare_validated_data_for_create(create_data)
            sql, bind_values = self._build_upsert_sql(validated_data)

            try:
                return await self._run_upsert_returning(db, sql, bind_values, kwargs)
            except Exception as e:
                raise D1ErrorClassifier.classify_error(e) from e

        return _inner()

    async def upsert(self, db, **kwargs) -> Model:
        """
        Convenient upsert that returns just the instance

        Alias for create_or_update()[0] for simpler event-driven flows:

        Example:
            # Idempotent event processing
            user = await User.objects.upsert(
                db,
                email="user@example.com",
                name="Updated Name",
                last_seen=datetime.now()
            )
        """
        instance, _ = await self.create_or_update(db, **kwargs)
        return instance

    def filter(self, db, **kwargs) -> QuerySet:
        """Filter model instances"""
        return self.get_queryset(db).filter(**kwargs)

    def all(self, db) -> QuerySet:
        """Get all model instances"""
        return self.get_queryset(db)

    async def exists(self, db, **kwargs) -> bool:
        """
        Check if any instances exist - D1 cost optimized

        D1 Cost Optimization: Uses SELECT 1 ... LIMIT 1
        Stops at first matching row instead of counting all rows.

        Example:
            if await User.objects.exists(db, email="test@example.com"):
                # User exists
        """
        return await self.filter(db, **kwargs).exists()

    def only(self, db, *field_names) -> QuerySet:
        """
        Select only specific fields - D1 cost optimization

        Example:
            users = await User.objects.only(db, 'email', 'name').all()
        """
        return self.get_queryset(db).only(*field_names)

    def values(self, db, *field_names) -> QuerySet:
        """
        Return dictionaries instead of model instances - D1 cost optimization

        Example:
            emails = await User.objects.values(db, 'email').all()
        """
        return self.get_queryset(db).values(*field_names)


class ModelMeta(type):
    """Metaclass for Model to set up fields and metadata"""

    def __new__(cls, name, bases, attrs):
        # Don't process the Model base class itself
        if name == "Model":
            return super().__new__(cls, name, bases, attrs)

        # Process model fields and metadata
        fields = cls._extract_fields(attrs)
        meta_attrs = cls._create_meta_attrs(attrs, name)

        # Set up model attributes
        attrs["_meta"] = type("Meta", (), meta_attrs)
        attrs["_fields"] = fields
        attrs["objects"] = Manager(None)  # Will be set after class creation

        new_class = super().__new__(cls, name, bases, attrs)
        new_class.objects = Manager(new_class)

        # Add model-specific exception and register constraints
        cls._add_model_exception(new_class)
        cls._register_model_constraints(new_class)

        return new_class

    @staticmethod
    def _extract_fields(attrs):
        """Extract and process field definitions from class attributes"""
        fields = {}

        # Add auto-generated ID field first if not present
        has_primary_key = any(
            isinstance(v, Field) and getattr(v, "primary_key", False)
            for v in attrs.values()
        )
        if not has_primary_key:
            id_field = IntegerField(primary_key=True)
            id_field.name = "id"
            fields["id"] = id_field
            attrs["id"] = id_field

        # Process field definitions
        for key, value in attrs.items():
            if isinstance(value, Field):
                value.name = key
                fields[key] = value

        return fields

    @staticmethod
    def _create_meta_attrs(attrs, class_name):
        """Create meta attributes dictionary from Meta class"""
        meta_attrs = {}

        if "Meta" in attrs:
            for attr_name in dir(attrs["Meta"]):
                if not attr_name.startswith("_"):
                    meta_attrs[attr_name] = getattr(attrs["Meta"], attr_name)

        # Set default table name if not specified
        if "table_name" not in meta_attrs:
            meta_attrs["table_name"] = class_name.lower() + "s"
        # Validate table name to avoid unsafe identifiers in SQL
        from .sql import safe_ident

        table_name = meta_attrs.get("table_name")
        safe_ident(table_name or "")

        return meta_attrs

    @staticmethod
    def _add_model_exception(new_class):
        """Add model-specific DoesNotExist exception class"""

        class DoesNotExist(DoesNotExistError):
            """Model-specific DoesNotExist exception"""

            pass

        new_class.DoesNotExist = DoesNotExist

    @staticmethod
    def _register_model_constraints(model_class):
        """Auto-register model constraints with the global constraint registry"""
        registry = get_constraint_registry()
        table_name = model_class._meta.table_name
        constraints = {}

        # Register unique field constraints
        for field_name, field in model_class._fields.items():
            if field.unique and not field.primary_key:
                constraint_name = f"uq_{table_name}_{field_name}"
                constraints[constraint_name] = [field_name]

        # Register NOT NULL constraints for required fields
        for field_name, field in model_class._fields.items():
            if not field.null and not field.primary_key:
                constraint_name = f"nn_{table_name}_{field_name}"
                constraints[constraint_name] = [field_name]

        # Register primary key constraint
        for field_name, field in model_class._fields.items():
            if field.primary_key:
                constraint_name = f"pk_{table_name}_{field_name}"
                constraints[constraint_name] = [field_name]

        if constraints:
            registry.register_table(table_name, constraints)


class Model(metaclass=ModelMeta):
    """Base model class for ORM"""

    def __init__(self, **kwargs):
        self._state = {"saved": False}

        # Set field values
        for field_name, field in self._fields.items():
            if field_name in kwargs:
                value = kwargs[field_name]
            else:
                value = field.default() if callable(field.default) else field.default

            # Handle auto fields
            if isinstance(field, DateTimeField):
                if field.auto_now_add and value is None:
                    value = datetime.now()

            setattr(self, field_name, value)

    @classmethod
    def _from_db(cls, row_data: dict[str, Any]) -> Model:
        """Create model instance from database row"""
        instance = cls.__new__(cls)
        instance._state = {"saved": True}

        for field_name, field in cls._fields.items():
            raw_value = row_data.get(field_name)
            if raw_value is not None:
                value = field.to_python(raw_value)
            else:
                value = None
            setattr(instance, field_name, value)

        return instance

    def _prepare_save_field_data(self) -> dict[str, Any]:
        """Prepare and validate field data for saving"""
        field_data = {}
        for field_name, field in self._fields.items():
            value = getattr(self, field_name, None)

            # Handle auto fields
            if isinstance(field, DateTimeField):
                if field.auto_now or (field.auto_now_add and not self._state["saved"]):
                    value = datetime.now()
                    setattr(self, field_name, value)

            # Validate and convert
            validated_value = field.validate(value)
            db_value = field.to_db(validated_value)
            field_data[field_name] = db_value
        return field_data

    def _build_update_sql(self, field_data: dict[str, Any]) -> tuple[str, list[Any]]:
        """Build UPDATE SQL with explicit NULL handling"""
        pk_field = self._get_pk_field()
        pk_value = getattr(self, pk_field.name)

        set_clauses = []
        bind_values = []

        for field_name, value in field_data.items():
            if field_name != pk_field.name:  # Don't update primary key
                if value is None:
                    set_clauses.append(f"{_qi(field_name)} = NULL")
                else:
                    set_clauses.append(f"{_qi(field_name)} = ?")
                    bind_values.append(value)

        if not set_clauses:  # No fields to update
            return None, []

        bind_values.append(pk_value)
        table = _qi(self._meta.table_name)
        pk_col = _qi(pk_field.name)
        sql = f"UPDATE {table} SET {', '.join(set_clauses)} WHERE {pk_col} = ?"  # nosec B608: identifier validated+quoted; values parameterized
        return sql, bind_values

    def _build_insert_sql(self, field_data: dict[str, Any]) -> tuple[str, list[Any]]:
        """Build INSERT SQL with explicit NULL handling"""
        pk_field = self._get_pk_field()

        # For auto-increment primary keys, don't include them in INSERT
        if pk_field.name == "id" and getattr(self, pk_field.name, None) is None:
            field_data.pop("id", None)

        columns = list(field_data.keys())
        values = list(field_data.values())

        # Build SQL with explicit NULL for None values to avoid JavaScript undefined conversion
        value_expressions = []
        bind_values = []

        for value in values:
            if value is None:
                value_expressions.append("NULL")
            else:
                value_expressions.append("?")
                bind_values.append(value)

        table = _qi(self._meta.table_name)
        quoted_columns = ", ".join(_qi(col) for col in columns)
        sql = f"INSERT INTO {table} ({quoted_columns}) VALUES ({', '.join(value_expressions)})"  # nosec B608: identifier validated+quoted; values parameterized
        return sql, bind_values

    async def _execute_update(self, db, sql: str, bind_values: list[Any]) -> None:
        """Execute UPDATE statement"""
        try:
            await db.prepare(sql).bind(*bind_values).run()
        except Exception as e:
            raise D1ErrorClassifier.classify_error(e) from e

    async def _execute_insert(self, db, sql: str, bind_values: list[Any]) -> None:
        """Execute INSERT statement and handle auto-generated ID"""
        try:
            if bind_values:
                result = await db.prepare(sql).bind(*bind_values).run()
            else:
                result = await db.prepare(sql).run()

            # Set the auto-generated ID from D1 response
            pk_field = self._get_pk_field()
            if (
                pk_field.name == "id"
                and hasattr(result, "meta")
                and hasattr(result.meta, "last_row_id")
            ):
                self.id = result.meta.last_row_id

            self._state["saved"] = True
        except Exception as e:
            raise D1ErrorClassifier.classify_error(e) from e

    async def save(self, db) -> None:
        """
        Save model instance to database

        D1 Optimization: Single write operation, same as raw SQL:
        - INSERT: INSERT INTO table (...) VALUES (...)
        - UPDATE: UPDATE table SET ... WHERE id = ?
        No additional row reads/writes vs raw SQL
        """
        field_data = self._prepare_save_field_data()

        if self._state["saved"]:
            # UPDATE existing record
            sql, bind_values = self._build_update_sql(field_data)
            if sql:  # Only execute if there are fields to update
                await self._execute_update(db, sql, bind_values)
        else:
            # INSERT new record
            sql, bind_values = self._build_insert_sql(field_data)
            await self._execute_insert(db, sql, bind_values)

    async def delete(self, db) -> None:
        """
        Delete model instance from database

        D1 Optimization: Single DELETE operation, same as raw SQL:
        DELETE FROM table WHERE id = ?
        No additional row reads/writes vs raw SQL
        """
        if not self._state["saved"]:
            return

        pk_field = self._get_pk_field()
        pk_value = getattr(self, pk_field.name)

        table = _qi(self._meta.table_name)
        pk_col = _qi(pk_field.name)
        sql = f"DELETE FROM {table} WHERE {pk_col} = ?"  # nosec B608: identifier validated+quoted; values parameterized
        try:
            await db.prepare(sql).bind(pk_value).run()
            self._state["saved"] = False
        except Exception as e:
            raise D1ErrorClassifier.classify_error(e) from e

    def _get_pk_field(self) -> Field:
        """Get the primary key field"""
        for field in self._fields.values():
            if field.primary_key:
                return field
        raise ValueError("No primary key field found")

    @classmethod
    def _get_pk_field_static(cls) -> Field:
        """Get the primary key field (class method)"""
        for field in cls._fields.values():
            if field.primary_key:
                return field
        raise ValueError("No primary key field found")

    def to_dict(self) -> dict[str, Any]:
        """Convert model instance to dictionary"""
        result = {}
        for field_name, field in self._fields.items():
            value = getattr(self, field_name, None)
            if value is not None:
                # Convert datetime to ISO format for JSON serialization
                if isinstance(field, DateTimeField) and isinstance(value, datetime):
                    value = value.isoformat()
                elif isinstance(field, JSONField):
                    # JSON fields are already in the correct format
                    pass
                else:
                    value = field.to_python(value)
            result[field_name] = value
        return result

    @classmethod
    async def create_table(cls, db) -> None:
        """Create table for this model - D1 optimized with named constraints"""
        columns = []
        constraints = []
        table_name = cls._meta.table_name

        for field_name, field in cls._fields.items():
            column_def = f"{field_name} {field.get_sql_type()}"

            if field.primary_key:
                if isinstance(field, IntegerField) and field_name == "id":
                    column_def += " PRIMARY KEY AUTOINCREMENT"
                else:
                    constraint_name = f"pk_{table_name}_{field_name}"
                    constraints.append(
                        f"CONSTRAINT {constraint_name} PRIMARY KEY ({field_name})"
                    )

            elif not field.null:
                column_def += " NOT NULL"

            columns.append(column_def)

            # Add named UNIQUE constraints separately
            if field.unique and not field.primary_key:
                constraint_name = f"uq_{table_name}_{field_name}"
                constraints.append(
                    f"CONSTRAINT {constraint_name} UNIQUE ({field_name})"
                )

        # Combine columns and constraints
        all_definitions = columns + constraints
        sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(all_definitions)})"

        try:
            await db.exec(sql)
        except Exception as e:
            raise D1ErrorClassifier.classify_error(e) from e

    @classmethod
    def get_create_sql(cls) -> str:
        """Get CREATE TABLE SQL for offline deployment with named constraints"""
        columns = []
        constraints = []
        table_name = cls._meta.table_name

        for field_name, field in cls._fields.items():
            column_def = f"{field_name} {field.get_sql_type()}"

            if field.primary_key:
                if isinstance(field, IntegerField) and field_name == "id":
                    column_def += " PRIMARY KEY AUTOINCREMENT"
                else:
                    constraint_name = f"pk_{table_name}_{field_name}"
                    constraints.append(
                        f"CONSTRAINT {constraint_name} PRIMARY KEY ({field_name})"
                    )

            elif not field.null:
                column_def += " NOT NULL"

            columns.append(column_def)

            # Add named UNIQUE constraints separately
            if field.unique and not field.primary_key:
                constraint_name = f"uq_{table_name}_{field_name}"
                constraints.append(
                    f"CONSTRAINT {constraint_name} UNIQUE ({field_name})"
                )

        # Combine columns and constraints
        all_definitions = columns + constraints
        return (
            f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(all_definitions)});"
        )

    def __repr__(self):
        pk_field = self._get_pk_field()
        pk_value = getattr(self, pk_field.name, None)
        return f"<{self.__class__.__name__}: {pk_value}>"


class D1Transaction:
    """
    Transaction context for D1 batch operations

    D1 doesn't have traditional transactions, but we can batch operations
    for atomicity within the D1 batch API constraints.
    """

    def __init__(self, db):
        self.db = db
        self.statements = []
        self.executed = False

    async def add_statement(self, sql: str, params: list[Any] = None) -> None:
        """Add a statement to the transaction batch"""
        if self.executed:
            raise RuntimeError("Transaction already executed")
        stmt = await self.db.prepare(sql)
        if params:
            stmt = stmt.bind(*params)
        self.statements.append(stmt)

    async def execute(self) -> list[Any]:
        """Execute all statements as a batch"""
        if self.executed:
            raise RuntimeError("Transaction already executed")
        self.executed = True

        if not self.statements:
            return []

        # Use D1's batch API for atomicity
        return await self.db.batch(self.statements)

    def rollback(self) -> None:
        """Rollback (clear statements without executing)"""
        self.statements.clear()
        self.executed = True


@asynccontextmanager
async def transaction(db) -> AsyncGenerator[D1Transaction, None]:
    """
    Transaction context manager for D1

    Groups operations into a single D1 batch for better atomicity.
    Note: D1 batch operations have some atomicity but not full ACID.

    Usage:
        async with transaction(db) as txn:
            await txn.add_statement("INSERT INTO games (...) VALUES (?)", [...])
            await txn.add_statement("UPDATE users SET ... WHERE id = ?", [...])
            # Both execute together in D1 batch
    """
    txn = D1Transaction(db)
    try:
        yield txn
        if txn.statements and not txn.executed:
            await txn.execute()
    except Exception:
        await txn.rollback()
        raise


class BatchOperations:
    """
    Batch operation builder for efficient multi-statement execution

    Collects operations and executes them as a single D1 batch.
    More efficient than individual operations for bulk work.
    """

    def __init__(self, db):
        self.db = db
        self.operations = []

    def add_create(self, model_class: type[Model], **kwargs) -> BatchOperations:
        """Add a create operation to the batch"""
        # Prepare and validate data
        validated_data = {}
        for field_name, field in model_class._fields.items():
            if field_name in kwargs:
                value = kwargs[field_name]
                if (
                    isinstance(field, DateTimeField)
                    and field.auto_now_add
                    and value is None
                ):
                    value = datetime.now()
                validated_value = field.validate(value)
                db_value = field.to_db(validated_value)
                validated_data[field_name] = db_value

        # Skip auto-increment ID
        pk_field = model_class._get_pk_field_static()
        if pk_field.name == "id" and validated_data.get("id") is None:
            validated_data.pop("id", None)

        columns = list(validated_data.keys())
        placeholders = ["?" for _ in columns]
        values = list(validated_data.values())

        table = _qi(model_class._meta.table_name)
        quoted_columns = ", ".join(_qi(col) for col in columns)
        sql = (
            f"INSERT INTO {table} ({quoted_columns}) VALUES ({', '.join(placeholders)})"  # nosec B608: identifier validated+quoted; values parameterized
        )

        self.operations.append(
            {
                "type": "create",
                "model_class": model_class,
                "sql": sql,
                "params": values,
                "data": kwargs,
            }
        )
        return self

    def add_update(self, instance: Model) -> BatchOperations:
        """Add an update operation to the batch"""
        # Validate all fields
        field_data = {}
        for field_name, field in instance._fields.items():
            value = getattr(instance, field_name, None)

            if isinstance(field, DateTimeField) and field.auto_now:
                value = datetime.now()
                setattr(instance, field_name, value)

            validated_value = field.validate(value)
            db_value = field.to_db(validated_value)
            field_data[field_name] = db_value

        # Build UPDATE
        pk_field = instance._get_pk_field()
        pk_value = getattr(instance, pk_field.name)

        set_clauses = []
        params = []
        for field_name, value in field_data.items():
            if field_name != pk_field.name:
                set_clauses.append(f"{_qi(field_name)} = ?")
                params.append(value)

        if not set_clauses:
            return self  # Nothing to update

        params.append(pk_value)
        table = _qi(instance._meta.table_name)
        pk_col = _qi(pk_field.name)
        sql = f"UPDATE {table} SET {', '.join(set_clauses)} WHERE {pk_col} = ?"  # nosec B608: identifier validated+quoted; values parameterized

        self.operations.append(
            {"type": "update", "instance": instance, "sql": sql, "params": params}
        )
        return self

    def add_delete(self, instance: Model) -> BatchOperations:
        """Add a delete operation to the batch"""
        pk_field = instance._get_pk_field()
        pk_value = getattr(instance, pk_field.name)

        table = _qi(instance._meta.table_name)
        pk_col = _qi(pk_field.name)
        sql = f"DELETE FROM {table} WHERE {pk_col} = ?"  # nosec B608: identifier validated+quoted; values parameterized

        self.operations.append(
            {"type": "delete", "instance": instance, "sql": sql, "params": [pk_value]}
        )
        return self

    async def execute(self) -> list[Any]:
        """Execute all batched operations"""
        if not self.operations:
            return []

        # Prepare statements
        statements = []
        for op in self.operations:
            stmt = await self.db.prepare(op["sql"])
            stmt = stmt.bind(*op["params"])
            statements.append(stmt)

        # Execute as D1 batch
        results = await self.db.batch(statements)

        # Update instance states for successful operations
        for _i, (op, _result) in enumerate(zip(self.operations, results, strict=False)):
            if op["type"] == "delete":
                op["instance"]._state["saved"] = False

        return results


@asynccontextmanager
async def batch(db) -> AsyncGenerator[BatchOperations, None]:
    """
    Batch operations context manager

    Groups multiple model operations into a single D1 batch for efficiency.

    Usage:
        async with batch(db) as b:
            b.add_create(Game, title="Game 1", score=100)
            b.add_create(Game, title="Game 2", score=200)
            b.add_update(existing_game)
            # All execute together efficiently
    """
    batch_ops = BatchOperations(db)
    try:
        yield batch_ops
        await batch_ops.execute()
    except Exception:
        # Clear operations on error
        batch_ops.operations.clear()
        raise


# Simple migration system
class SchemaManager:
    """Minimal schema management for D1 migrations"""

    @staticmethod
    def generate_schema_sql(models: list[type[Model]]) -> str:
        """Generate SQL for all models - for wrangler deployment"""
        sql_statements = []
        for model in models:
            sql_statements.append(model.get_create_sql())
        return "\n\n".join(sql_statements)

    @staticmethod
    async def migrate_all(db, models: list[type[Model]]) -> dict[str, bool]:
        """Create all tables - simple migration endpoint"""
        results = {}
        for model in models:
            try:
                await model.create_table(db)
                results[model.__name__] = True
            except Exception as e:
                results[model.__name__] = f"Error: {e}"
        return results
