import pytest

from kinglet.cache_d1 import D1CacheService


def test_d1_cache_service_safe_table_rejects_invalid():
    svc = D1CacheService(db=None)
    svc.table_name = "bad table"
    with pytest.raises(ValueError):
        svc._safe_table()
