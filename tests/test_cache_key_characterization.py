"""Characterization tests for generate_cache_key().

These pin the EXACT deployed cache-key hashes for representative inputs.
They must pass unchanged before AND after the complexity refactor:
any hash change here means deployed cache keys were invalidated and the
refactor introduced a behavior change. Run before touching kinglet/cache_d1.py.
"""

from kinglet.cache_d1 import generate_cache_key


class StubRequest:
    """Minimal request double for cache-key fingerprinting (local copy)."""

    def __init__(self, method="GET", query_string="", path_params=None, headers=None):
        self.method = method
        self.query_string = query_string
        self.path_params = path_params or {}
        self._headers = {k.lower(): v for k, v in (headers or {}).items()}

    def header(self, name, default=None):
        return self._headers.get(name.lower(), default)


class TestCacheKeyCharacterization:
    def test_path_only(self):
        assert (
            generate_cache_key("/api/games/action")
            == "cache:1726d4813befe01b52d0bbbdf3c8a3c7"
        )

    def test_explicit_method(self):
        assert (
            generate_cache_key("/api/games/action", method="post")
            == "cache:19cf8a4b53ad8224afda26edcf7bb4d0"
        )

    def test_request_derived_method(self):
        assert (
            generate_cache_key("/p", request=StubRequest(method="post"))
            == "cache:9424fb0823d621c22b2723083bc90513"
        )

    def test_query_params_with_ordering(self):
        assert (
            generate_cache_key("/p", query_params={"b": "2", "a": "1"})
            == "cache:30c39cb247593e554b9a34a391ff538e"
        )
        # Insertion order must not matter: sorted before hashing.
        assert (
            generate_cache_key("/p", query_params={"a": "1", "b": "2"})
            == "cache:30c39cb247593e554b9a34a391ff538e"
        )

    def test_request_query_string(self):
        assert (
            generate_cache_key("/p", request=StubRequest(query_string="a=1&b=2"))
            == "cache:7cc7d9baa539d1020274e410519d7bb3"
        )

    def test_path_params(self):
        assert (
            generate_cache_key(
                "/p", request=StubRequest(path_params={"id": "7", "org": "acme"})
            )
            == "cache:91e66c3180e08e137e7376dd3b7ab6ee"
        )

    def test_extra_params(self):
        assert (
            generate_cache_key("/p", extra_params={"user_id": "u1", "z": "9"})
            == "cache:5927d83ccf491970d89021443b767fe4"
        )

    def test_default_vary_headers(self):
        assert (
            generate_cache_key(
                "/p", request=StubRequest(headers={"Authorization": "Bearer x"})
            )
            == "cache:b68b9d2020ef36c69679a2c37d30b146"
        )

    def test_explicitly_supplied_headers(self):
        assert (
            generate_cache_key("/p", headers={"X-Tenant-Id": "t1"})
            == "cache:dfe63afc01afb61f3ca83a1afbbe4486"
        )

    def test_empty_and_none_headers_match_bare_path(self):
        bare_with_slash = generate_cache_key("/p")
        assert generate_cache_key("/p", headers={}) == bare_with_slash
        assert generate_cache_key("/p", headers=None) == bare_with_slash
        assert bare_with_slash == "cache:00d74baf14ea415c6164614838c91f83"

    def test_string_body(self):
        assert (
            generate_cache_key("/p", body='{"a": 1}')
            == "cache:365a7e620f8e93a2dca3b449a18ae0d6"
        )

    def test_binary_body(self):
        assert (
            generate_cache_key("/p", body=b"\x00\x01abc")
            == "cache:84a2e63b566d630170eb49d441b63477"
        )

    def test_combination_of_everything(self):
        assert (
            generate_cache_key(
                "/api/items/",
                method="get",
                query_params={"b": "2", "a": "1"},
                extra_params={"user_id": "u1"},
                headers={"X-Tenant-Id": "t1", "Authorization": ""},
                body='{"a": 1}',
            )
            == "cache:b318aca736c3e87f998ed8c21bb40ce1"
        )

    def test_keys_differ_across_dimensions(self):
        base = generate_cache_key("/p")
        assert generate_cache_key("/p", method="get") != base
        assert generate_cache_key("/p", query_params={"a": "1"}) != base
        assert generate_cache_key("/p", extra_params={"u": "1"}) != base
        assert generate_cache_key("/p", body="x") != base
