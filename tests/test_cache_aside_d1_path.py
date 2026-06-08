from types import SimpleNamespace

import pytest

from kinglet.utils import cache_aside_d1


class _Req:
    def __init__(self):
        self.url = "https://example.com/api"
        self.method = "GET"
        self.headers = {}


class RequestWrapper:
    def __init__(self, path="/api", method="GET", headers=None, body="", env=None):
        self._raw = _Req()
        self.env = env or SimpleNamespace(DB=object(), ENVIRONMENT="production")
        self.url = self._raw.url

        if "?" in path:
            path_only, query_string = path.split("?", 1)
        else:
            path_only, query_string = path, ""

        self.path = path_only
        self._parsed_url = type(
            "P", (), {"path": path_only, "query": query_string, "scheme": "https", "netloc": "example.com"}
        )()
        self.method = method
        self.path_params = {}
        self._headers = {k.lower(): v for k, v in (headers or {}).items()}
        self._body = body

    def header(self, name, default=None):
        return self._headers.get(name.lower(), default)

    @property
    def query_string(self):
        return self._parsed_url.query

    async def text(self):
        return self._body


class FakeCacheService:
    seen_keys = []

    def __init__(self, db, ttl, track_hits=False):  # match constructor
        self.db = db
        self.ttl = ttl
        self.track_hits = track_hits

    async def get_or_generate(self, cache_key, generator):
        self.seen_keys.append(cache_key)
        return {"_cached_at": 1, "_cache_hit": True, "ok": True, "key": cache_key}


@pytest.mark.asyncio
async def test_cache_aside_d1_hits_cache(monkeypatch):
    # Monkeypatch D1CacheService to our fake
    import kinglet.cache_d1 as cache_d1_mod

    monkeypatch.setattr(cache_d1_mod, "D1CacheService", FakeCacheService)
    FakeCacheService.seen_keys = []

    @cache_aside_d1()
    async def handler(req: RequestWrapper):
        return {"ok": False}

    out = await handler(RequestWrapper())
    assert out.get("_cache_hit") is True
    assert out.get("ok") is True


@pytest.mark.asyncio
async def test_cache_aside_d1_key_varies_by_query_auth_and_body(monkeypatch):
    # Monkeypatch D1CacheService to our fake
    import kinglet.cache_d1 as cache_d1_mod

    monkeypatch.setattr(cache_d1_mod, "D1CacheService", FakeCacheService)
    FakeCacheService.seen_keys = []

    @cache_aside_d1()
    async def handler(req: RequestWrapper):
        return {"ok": False}

    out1 = await handler(
        RequestWrapper(
            path="/api/search?q=alice", headers={"Authorization": "Bearer alice"}
        )
    )
    out2 = await handler(
        RequestWrapper(
            path="/api/search?q=bob", headers={"Authorization": "Bearer alice"}
        )
    )
    out3 = await handler(
        RequestWrapper(
            path="/api/search?q=alice", headers={"Authorization": "Bearer bob"}
        )
    )
    out4 = await handler(
        RequestWrapper(
            path="/api/search",
            method="POST",
            headers={"Authorization": "Bearer alice"},
            body='{"value":"one"}',
        )
    )
    out5 = await handler(
        RequestWrapper(
            path="/api/search",
            method="POST",
            headers={"Authorization": "Bearer alice"},
            body='{"value":"two"}',
        )
    )

    assert len(FakeCacheService.seen_keys) == 5
    assert len(set(FakeCacheService.seen_keys[:3])) == 3
    assert out4["key"] != out5["key"]
