from kinglet.orm_errors import (
    ForeignKeyViolationError,
    MultipleObjectsReturnedError,
    NotNullViolationError,
    UniqueViolationError,
    ValidationError,
    to_problem_json,
)


def test_to_problem_json_various_errors():
    # Validation
    v = ValidationError("field", "msg", "bad")
    p = to_problem_json(v, status=400, title="t")
    assert p.get("validation_type") == "field_validation"

    # Unique
    u = UniqueViolationError("field", "dup")
    p = to_problem_json(u, status=409, title="t")
    assert p.get("constraint_type") == "unique"

    # Not null
    n = NotNullViolationError("field")
    p = to_problem_json(n, status=400, title="t")
    assert p.get("constraint_type") == "not_null"

    # Foreign key
    f = ForeignKeyViolationError("field", "fk")
    p = to_problem_json(f, status=409, title="t")
    assert p.get("constraint_type") == "foreign_key"

    # Multiple objects
    m = MultipleObjectsReturnedError("Model", 2)
    p = to_problem_json(m, status=409, title="t")
    assert p.get("count") == 2
