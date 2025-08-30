from types import SimpleNamespace

import pytest

from kinglet.utils import cache_aside_d1


class _Req:
    def __init__(self):
        self.url = "https://example.com/api"
        self.method = "GET"
        self.headers = {}


class RequestWrapper:
    def __init__(self):
        self._raw = _Req()
        self.env = SimpleNamespace(DB=object())
        self.url = self._raw.url
        self._parsed_url = type("P", (), {"path": "/api", "query": ""})()
        self.method = "GET"
        self._headers = {}

    def header(self, name, default=None):
        return default


class FakeCacheService:
    def __init__(self, db, ttl, track_hits=False):  # match constructor
        self.db = db
        self.ttl = ttl
        self.track_hits = track_hits

    async def get_or_generate(self, cache_key, generator):
        return {"_cached_at": 1, "_cache_hit": True, "ok": True, "key": cache_key}


@pytest.mark.asyncio
async def test_cache_aside_d1_hits_cache(monkeypatch):
    # Monkeypatch D1CacheService to our fake
    import kinglet.cache_d1 as cache_d1_mod

    monkeypatch.setattr(cache_d1_mod, "D1CacheService", FakeCacheService)

    @cache_aside_d1()
    async def handler(req: RequestWrapper):
        return {"ok": False}

    out = await handler(RequestWrapper())
    assert out.get("_cache_hit") is True
    assert out.get("ok") is True
