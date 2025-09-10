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
    """Test that media_url falls back gracefully when no CDN_BASE_URL is set"""
    import os

    # Test that media_url works even with no environment variable set
    original_cdn = os.environ.get("CDN_BASE_URL")
    try:
        if "CDN_BASE_URL" in os.environ:
            del os.environ["CDN_BASE_URL"]

        # Should fall back to default
        assert utils.media_url("abc") == "/api/media/abc"

    finally:
        # Restore original environment
        if original_cdn:
            os.environ["CDN_BASE_URL"] = original_cdn
