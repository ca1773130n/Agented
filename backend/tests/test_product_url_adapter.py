"""Tests for ProductUrlAdapter — the keyless content-change watcher for the
``product_url`` kind (the default lane for any pasted product/marketing URL).

The adapter CRAWLS the product site (seed + same-site feature/pricing/docs pages)
and hashes the COMBINED visible text. Covers the contract:
  * First poll (watermark NULL) over a 200 HTML body -> ``changed``; watermark ==
    sha256 of the COMBINED page text (``_combine_pages``); raw_ref is the
    (non-empty) extracted text the summarizer reads; content_hash == watermark.
  * A second fetch of the SAME body, watermark already preset to that hash ->
    ``unchanged`` (no write).
  * ``304`` -> ``unchanged`` (defensive; the seed is no longer conditional-GET).
  * ``403`` -> ``throttled``; ``500`` -> ``error`` (no raise).
  * A body that strips to empty text -> ``skipped``.
  * Crawl: same-site gather, link prioritize/filter/dedup, page cap, sub-page
    failure non-fatal, a sub-page redirect to an internal IP is skipped, and a
    sub-page-only content change moves the combined watermark.

HTTP is mocked by monkeypatching ``product_url.httpx.get`` — NO network. No DB is
needed: ``fetch`` is a pure read over the passed ``source`` dict.
"""

from __future__ import annotations

import hashlib

import httpx

from app.services.competitor_source_service import KIND_PRODUCT_URL
from app.services.source_adapters import product_url
from app.services.source_adapters.product_url import (
    ProductUrlAdapter,
    _combine_pages,
    _extract_text,
    _select_links,
)


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
    url = "https://ex.com/p"
    result = adapter.fetch({"id": "s1", "url": url, "watermark": None})

    # No links in _HTML -> crawl finds nothing -> combined is just the seed page.
    expected_combined = _combine_pages([(url, _extract_text(_HTML))])
    expected_hash = hashlib.sha256(expected_combined.encode("utf-8")).hexdigest()

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
    url = "https://ex.com/p"
    preset = hashlib.sha256(
        _combine_pages([(url, _extract_text(_HTML))]).encode("utf-8")
    ).hexdigest()
    result = adapter.fetch({"id": "s1", "url": url, "watermark": preset})
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


# --- Crawl: gather feature/pricing/docs pages, not just the landing page -------


def _patch_router(monkeypatch, routes, *, public=lambda host: True):
    """Patch httpx.get to route by URL substring, and _host_is_public to ``public``.
    Unmatched URLs return 404. ``routes`` is checked longest-key-first so a more
    specific path wins over a prefix."""
    ordered = sorted(routes.items(), key=lambda kv: -len(kv[0]))

    def fake_get(url, **kwargs):
        for frag, resp in ordered:
            if frag in url:
                return resp
        return _FakeResponse(404)

    monkeypatch.setattr(product_url.httpx, "get", fake_get)
    monkeypatch.setattr(product_url, "_host_is_public", public)


_HTML_TYPE = {"Content-Type": "text/html"}


def test_crawls_same_site_feature_pages(monkeypatch):
    home = (
        "<html><body><h1>Acme</h1>"
        '<a href="/features">Features</a>'
        '<a href="https://other.com/x">offsite</a>'
        "</body></html>"
    )
    feat = "<html><body>Acme features: realtime sync, export, SSO</body></html>"
    _patch_router(
        monkeypatch,
        {
            "https://ex.com/home": _FakeResponse(200, text=home, headers={"ETag": '"v1"'}),
            "https://ex.com/features": _FakeResponse(200, text=feat, headers=_HTML_TYPE),
        },
    )
    result = ProductUrlAdapter().fetch(
        {"id": "s1", "url": "https://ex.com/home", "watermark": None}
    )
    assert result.outcome == "changed"
    assert "Acme" in result.raw_ref  # seed page
    assert "realtime sync, export, SSO" in result.raw_ref  # crawled feature page
    assert "[/features]" in result.raw_ref  # page is path-tagged
    # The off-site link was filtered at selection — its content was never fetched.
    assert "other.com" not in result.raw_ref


def test_select_links_filters_and_prioritizes():
    html = (
        '<a href="/pricing">P</a>'
        '<a href="/blog/post">B</a>'
        '<a href="https://ext.com/y">E</a>'
        '<a href="mailto:x@y.com">M</a>'
        '<a href="/pricing#plans">dup</a>'
        '<a href="https://www.ex.com/about">A</a>'
    )
    links = _select_links(html, "https://ex.com/")
    assert "https://ext.com/y" not in links  # off-site excluded
    assert all("mailto" not in u for u in links)  # mailto excluded
    assert links.count("https://ex.com/pricing") == 1  # deduped (fragment dropped)
    assert "https://www.ex.com/about" in links  # www. treated same-site
    # feature pages (pricing, about) ordered before a generic /blog/post
    assert links.index("https://ex.com/pricing") < links.index("https://ex.com/blog/post")


def test_crawl_respects_page_cap(monkeypatch):
    links = "".join(f'<a href="/feature{i}">f</a>' for i in range(20))
    home = f"<html><body>home {links}</body></html>"
    fetched = []

    def fake_get(url, **kwargs):
        fetched.append(url)
        if url == "https://ex.com/home":
            return _FakeResponse(200, text=home)
        return _FakeResponse(200, text="<html><body>sub content</body></html>", headers=_HTML_TYPE)

    monkeypatch.setattr(product_url.httpx, "get", fake_get)
    monkeypatch.setattr(product_url, "_host_is_public", lambda host: True)
    ProductUrlAdapter().fetch({"id": "s1", "url": "https://ex.com/home", "watermark": None})
    sub_calls = [u for u in fetched if "/feature" in u]
    assert len(sub_calls) == product_url._MAX_CRAWL_PAGES  # capped, not all 20


def test_crawl_subpage_failure_is_not_fatal(monkeypatch):
    # A sub-page that raises (transport error / SSRF redirect) is skipped; the
    # crawl still returns the seed content rather than failing the whole poll.
    home = '<html><body>home page text <a href="/features">F</a></body></html>'

    def fake_get(url, **kwargs):
        if url == "https://ex.com/home":
            return _FakeResponse(200, text=home)
        raise httpx.ConnectError("subpage down")

    monkeypatch.setattr(product_url.httpx, "get", fake_get)
    monkeypatch.setattr(product_url, "_host_is_public", lambda host: True)
    result = ProductUrlAdapter().fetch(
        {"id": "s1", "url": "https://ex.com/home", "watermark": None}
    )
    assert result.outcome == "changed"
    assert "home page text" in result.raw_ref


def test_crawl_subpage_redirect_to_internal_is_skipped(monkeypatch):
    # A same-site sub-page that 302s to a loopback IP must be refused AT the hop by
    # _safe_get; the crawl skips it and keeps the seed content (never fetches it).
    home = '<html><body>home main text <a href="/admin">A</a></body></html>'

    def fake_get(url, **kwargs):
        if url == "https://ex.com/home":
            return _FakeResponse(200, text=home)
        if "ex.com/admin" in url:
            return _FakeResponse(302, headers={"Location": "http://127.0.0.1/secret"})
        raise AssertionError(f"internal target must never be fetched: {url}")

    monkeypatch.setattr(product_url.httpx, "get", fake_get)
    # ex.com public; 127.* is not — so the redirect hop is refused before any GET.
    monkeypatch.setattr(
        product_url, "_host_is_public", lambda host: not str(host).startswith("127.")
    )
    result = ProductUrlAdapter().fetch(
        {"id": "s1", "url": "https://ex.com/home", "watermark": None}
    )
    assert result.outcome == "changed"
    assert "home main text" in result.raw_ref
    assert "secret" not in result.raw_ref  # the internal redirect target never reached


def test_subpage_only_change_moves_watermark(monkeypatch):
    # The seed stays identical; ONLY a crawled feature page changes. The combined
    # watermark must still move (the hash covers the full crawled text).
    home = '<html><body>stable home <a href="/features">F</a></body></html>'

    def routes(feat_text):
        return {
            "https://ex.com/home": _FakeResponse(200, text=home),
            "https://ex.com/features": _FakeResponse(200, text=feat_text, headers=_HTML_TYPE),
        }

    _patch_router(monkeypatch, routes("<html><body>features v1: sync</body></html>"))
    r1 = ProductUrlAdapter().fetch({"id": "s1", "url": "https://ex.com/home", "watermark": None})

    _patch_router(monkeypatch, routes("<html><body>features v2: sync, export, SSO</body></html>"))
    r2 = ProductUrlAdapter().fetch(
        {"id": "s1", "url": "https://ex.com/home", "watermark": r1.watermark}
    )

    assert r1.outcome == "changed"
    assert r2.outcome == "changed"  # sub-page change detected despite an identical home
    assert r2.watermark != r1.watermark
    assert "export, SSO" in r2.raw_ref
