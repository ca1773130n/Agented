"""Tests for ProductUrlAdapter — the keyless content-change watcher for the
``product_url`` kind (the default lane for any pasted product/marketing URL).

Covers the adapter contract:
  * First poll (watermark NULL) over a 200 HTML body -> ``changed``; watermark ==
    sha256 of the STRIPPED visible text; raw_ref is the (non-empty) extracted
    text the summarizer reads; content_hash == watermark.
  * A second fetch of the SAME body, watermark already preset to that hash ->
    ``unchanged`` (no write).
  * ``304`` (ETag match) -> ``unchanged`` (the free conditional-GET path).
  * ``403`` -> ``throttled``; ``500`` -> ``error`` (no raise).
  * A body that strips to empty text -> ``skipped``.

HTTP is mocked by monkeypatching ``product_url.httpx.get`` — NO network. No DB is
needed: ``fetch`` is a pure read over the passed ``source`` dict.
"""

from __future__ import annotations

import hashlib

import httpx

from app.services.competitor_source_service import KIND_PRODUCT_URL
from app.services.source_adapters import product_url
from app.services.source_adapters.product_url import ProductUrlAdapter, _extract_text


class _FakeResponse:
    """Minimal stand-in for httpx.Response (only what fetch reads)."""

    def __init__(self, status_code: int, *, text: str = "", headers: dict | None = None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}


def _patch_get(monkeypatch, response=None, *, raises: bool = False):
    """Patch ``product_url.httpx.get`` to return ``response`` (or raise)."""

    def fake_get(url, **kwargs):
        if raises:
            raise httpx.ConnectError("boom")
        return response

    monkeypatch.setattr(product_url.httpx, "get", fake_get)
    # Treat every host as public so these response-shape tests don't hit real DNS;
    # the SSRF host validation is covered by the dedicated tests below.
    monkeypatch.setattr(product_url, "_host_is_public", lambda host: True)


_HTML = "<html><head><style>.x{color:red}</style></head><body><h1>Hi</h1> there</body></html>"


def test_kind_and_keyless():
    adapter = ProductUrlAdapter()
    assert adapter.kind == KIND_PRODUCT_URL
    assert adapter.has_credential() is True


def test_first_poll_no_watermark_is_changed(monkeypatch):
    _patch_get(monkeypatch, _FakeResponse(200, text=_HTML, headers={"ETag": '"v1"'}))
    adapter = ProductUrlAdapter()
    result = adapter.fetch({"id": "s1", "url": "https://ex.com/p", "watermark": None})

    expected_text = _extract_text(_HTML)
    expected_hash = hashlib.sha256(expected_text.encode("utf-8")).hexdigest()

    assert result.outcome == "changed"
    assert result.watermark == expected_hash
    assert result.content_hash == expected_hash
    assert result.raw_ref  # non-empty extracted text
    assert "Hi" in result.raw_ref and "there" in result.raw_ref
    # script/style bodies must not leak into the extracted text.
    assert "color:red" not in result.raw_ref
    assert result.etag == '"v1"'


def test_same_body_with_matching_watermark_is_unchanged(monkeypatch):
    _patch_get(monkeypatch, _FakeResponse(200, text=_HTML))
    adapter = ProductUrlAdapter()
    preset = hashlib.sha256(_extract_text(_HTML).encode("utf-8")).hexdigest()
    result = adapter.fetch({"id": "s1", "url": "https://ex.com/p", "watermark": preset})
    assert result.outcome == "unchanged"


def test_304_is_unchanged(monkeypatch):
    _patch_get(monkeypatch, _FakeResponse(304))
    adapter = ProductUrlAdapter()
    result = adapter.fetch(
        {"id": "s1", "url": "https://ex.com/p", "etag": '"v1"', "watermark": "h"}
    )
    assert result.outcome == "unchanged"


def test_403_is_throttled(monkeypatch):
    _patch_get(monkeypatch, _FakeResponse(403))
    adapter = ProductUrlAdapter()
    result = adapter.fetch({"id": "s1", "url": "https://ex.com/p", "watermark": None})
    assert result.outcome == "throttled"


def test_500_is_error(monkeypatch):
    _patch_get(monkeypatch, _FakeResponse(500))
    adapter = ProductUrlAdapter()
    result = adapter.fetch({"id": "s1", "url": "https://ex.com/p", "watermark": None})
    assert result.outcome == "error"


def test_transport_error_is_error(monkeypatch):
    _patch_get(monkeypatch, raises=True)
    adapter = ProductUrlAdapter()
    result = adapter.fetch({"id": "s1", "url": "https://ex.com/p", "watermark": None})
    assert result.outcome == "error"


def test_empty_text_body_is_skipped(monkeypatch):
    # A pure-script shell with no visible text -> strips to empty -> skipped.
    body = "<html><body><script>var a=1;</script></body></html>"
    assert _extract_text(body) == ""
    _patch_get(monkeypatch, _FakeResponse(200, text=body))
    adapter = ProductUrlAdapter()
    result = adapter.fetch({"id": "s1", "url": "https://ex.com/p", "watermark": None})
    assert result.outcome == "skipped"


def test_blank_url_is_skipped(monkeypatch):
    adapter = ProductUrlAdapter()
    result = adapter.fetch({"id": "s1", "url": "   ", "watermark": None})
    assert result.outcome == "skipped"


# --- SSRF guard ----------------------------------------------------------------
# A server-side fetch of an operator-supplied URL must refuse internal targets.
# IP literals resolve without DNS, so these stay hermetic.


def _patch_get_must_not_be_called(monkeypatch):
    """httpx.get that FAILS the test if called — a blocked URL must never fetch."""

    def fake_get(url, **kwargs):
        raise AssertionError(f"httpx.get must not be called for a blocked URL: {url}")

    monkeypatch.setattr(product_url.httpx, "get", fake_get)


def test_blocks_cloud_metadata_link_local(monkeypatch):
    _patch_get_must_not_be_called(monkeypatch)
    adapter = ProductUrlAdapter()
    result = adapter.fetch(
        {"id": "s1", "url": "http://169.254.169.254/latest/meta-data/", "watermark": None}
    )
    assert result.outcome == "skipped"


def test_blocks_loopback(monkeypatch):
    _patch_get_must_not_be_called(monkeypatch)
    adapter = ProductUrlAdapter()
    result = adapter.fetch({"id": "s1", "url": "http://127.0.0.1:8080/admin", "watermark": None})
    assert result.outcome == "skipped"


def test_blocks_cgnat_shared_address_space(monkeypatch):
    # 100.64.0.0/10 (carrier-grade NAT) is not private/loopback/etc. but is not
    # globally routable — must still be blocked.
    _patch_get_must_not_be_called(monkeypatch)
    adapter = ProductUrlAdapter()
    result = adapter.fetch({"id": "s1", "url": "http://100.64.0.1/", "watermark": None})
    assert result.outcome == "skipped"


def test_blocks_non_http_scheme(monkeypatch):
    _patch_get_must_not_be_called(monkeypatch)
    adapter = ProductUrlAdapter()
    result = adapter.fetch({"id": "s1", "url": "file:///etc/passwd", "watermark": None})
    assert result.outcome == "skipped"


def test_blocks_redirect_to_internal(monkeypatch):
    # A public host that 302s to loopback must be blocked AT the hop, not followed.
    calls = {"n": 0}

    def fake_get(url, **kwargs):
        calls["n"] += 1
        return _FakeResponse(302, headers={"Location": "http://127.0.0.1/internal"})

    monkeypatch.setattr(product_url.httpx, "get", fake_get)
    adapter = ProductUrlAdapter()
    # 93.184.216.34 (example.com) is public — passes the first check; the redirect
    # target is loopback and must NOT be followed.
    result = adapter.fetch({"id": "s1", "url": "http://93.184.216.34/start", "watermark": None})
    assert result.outcome == "skipped"
    assert calls["n"] == 1  # only the first hop fetched; redirect re-validated + refused
