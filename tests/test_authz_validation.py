import pytest

from kinglet.authz import d1_load_owner_public


class _DummyD1:
    async def prepare(self, _sql):
        raise AssertionError("should not prepare when table name invalid")


@pytest.mark.asyncio
async def test_d1_load_owner_public_rejects_invalid_table_name():
    with pytest.raises(ValueError):
        # invalid: space in identifier
        await d1_load_owner_public(_DummyD1(), "bad table", "rid")
