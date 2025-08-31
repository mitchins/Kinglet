from types import SimpleNamespace

from kinglet import utils
from kinglet.http import Request


def test_asset_url_falls_back_on_exception(monkeypatch):
    # Force _get_cdn_url to raise to exercise exception path
    monkeypatch.setattr(
        utils,
        "_get_cdn_url",
        lambda *_args, **_kw: (_ for _ in ()).throw(Exception("boom")),
    )

    class _Raw:
        url = "https://example.com/"
        method = "GET"

        class _Headers(dict):
            def items(self):
                return []

        headers = _Headers()

    req = Request(_Raw(), env=SimpleNamespace())
    result = utils.asset_url(req, "uid123", asset_type="media")
    assert result == "/api/media/uid123"


def test_media_url_falls_back_on_exception():
    class _Raw:
        url = "https://example.com/"
        method = "GET"

        class _Headers:
            def items(self):
                return []

        headers = _Headers()

    class _Req(Request):
        def header(self, *_args, **_kw):  # break header access
            raise Exception("bad header")

    req = _Req(_Raw(), env=SimpleNamespace())
    assert utils.media_url(req, "abc") == "/api/media/abc"
