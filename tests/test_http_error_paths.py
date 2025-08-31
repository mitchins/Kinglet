from kinglet.http import Request


class _BadIterableHeaders:
    # No items() or get(), will hit iterable path
    def __iter__(self):
        raise TypeError("not iterable")


class _RawReq:
    def __init__(self):
        self.url = "https://example.com/"
        self.method = "GET"
        self.headers = _BadIterableHeaders()


def test_request_handles_bad_iterable_headers():
    req = Request(_RawReq())
    # Should not raise; header() should return default when nothing parsed
    assert req.header("x-missing", "default") == "default"
