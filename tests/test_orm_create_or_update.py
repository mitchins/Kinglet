from datetime import datetime

import pytest

from kinglet.orm import DateTimeField, Model, StringField


class User(Model):
    email = StringField(unique=True)
    name = StringField()
    created_at = DateTimeField(auto_now_add=True)

    class Meta:
        table_name = "users"


class _Stmt:
    def __init__(self, sql, bind_vals):
        self.sql = sql
        self.bind_vals = bind_vals

    def bind(self, *vals):
        self.bind_vals = vals
        return self

    async def first(self):
        # Simulate D1 returning the row via RETURNING clause
        return {
            "id": 1,
            "email": "u@example.com",
            "name": "New Name",
            "created_at": int(datetime.now().timestamp()),
        }


class _DB:
    def __init__(self):
        self.last_sql = None
        self.last_vals = None

    def prepare(self, sql):  # prepare is sync in our ORM usage
        self.last_sql = sql
        return _Stmt(sql, None)


@pytest.mark.asyncio
async def test_create_or_update_builds_sql_and_returns_instance():
    db = _DB()
    mgr = User.objects
    # Have a unique field in kwargs to pass validation
    inst, created = await mgr.create_or_update(
        db, defaults={"name": None}, email="u@example.com"
    )
    assert inst.email == "u@example.com"
    # created flag true (no pk provided)
    assert created is True
    # Ensure SQL contains INSERT OR REPLACE and RETURNING
    assert "INSERT OR REPLACE" in db.last_sql
    assert "RETURNING" in db.last_sql


def test_create_or_update_requires_unique_field():
    db = _DB()
    with pytest.raises(ValueError):
        # No unique field in kwargs
        User.objects.create_or_update(db, name="n")
