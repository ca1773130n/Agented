"""Tests for ``url_summarizer.fetch_and_summarize``.

Uses ``httpx.MockTransport`` so no real network is touched. Each
test clears the in-process cache to stay independent of execution
order.
"""

from __future__ import annotations

import httpx
import pytest

from app.services import url_summarizer
from app.services.url_summarizer import (
    UrlSummary,
    _summarize_html,
    fetch_and_summarize,
)


@pytest.fixture(autouse=True)
def _clean_cache():
    url_summarizer._clear_cache_for_tests()
    yield
    url_summarizer._clear_cache_for_tests()


def _install_transport(monkeypatch, handler):
    """Patch httpx.Client to use a MockTransport with ``handler``."""
    transport = httpx.MockTransport(handler)
    original_init = httpx.Client.__init__

    def patched_init(self, *args, **kwargs):
        kwargs.pop("transport", None)
        original_init(self, *args, transport=transport, **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", patched_init)


# -----------------------------------------------------------------
# Pure helpers
# -----------------------------------------------------------------


def test_summarize_html_extracts_title_and_strips_scripts():
    html = (
        b"<html><head><title>Spec</title></head>"
        b"<body><script>evil()</script><p>Hello world</p></body></html>"
    )
    title, text = _summarize_html(html)
    assert title == "Spec"
    assert text == "Hello world"


def test_summarize_html_handles_malformed_input():
    html = b"<html><body><p>unterminated"
    title, text = _summarize_html(html)
    assert "unterminated" in text


# -----------------------------------------------------------------
# fetch_and_summarize
# -----------------------------------------------------------------


def test_fetch_returns_summary_for_html(monkeypatch):
    def handler(request):
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"<html><head><title>Page</title></head>"
            b"<body><p>Body text</p></body></html>",
        )

    _install_transport(monkeypatch, handler)
    summary = fetch_and_summarize("https://example.com/p")
    assert summary.title == "Page"
    assert "Body text" in summary.text
    assert summary.error is None


def test_fetch_404_records_error(monkeypatch):
    def handler(request):
        return httpx.Response(404, content=b"missing")

    _install_transport(monkeypatch, handler)
    summary = fetch_and_summarize("https://example.com/missing")
    assert summary.error == "HTTP 404"
    assert summary.text == ""


def test_fetch_network_error_records_error(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("connection refused")

    _install_transport(monkeypatch, handler)
    summary = fetch_and_summarize("https://example.com/down")
    assert summary.error
    assert "connection refused" in summary.error or "request error" in summary.error


def test_fetch_file_scheme_blocked():
    summary = fetch_and_summarize("file:///etc/passwd")
    assert summary.error == "scheme not allowed"


def test_fetch_is_cached(monkeypatch):
    call_count = {"n": 0}

    def handler(request):
        call_count["n"] += 1
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"<title>X</title>",
        )

    _install_transport(monkeypatch, handler)
    first = fetch_and_summarize("https://example.com/cache")
    second = fetch_and_summarize("https://example.com/cache")
    assert call_count["n"] == 1
    assert first == second


def test_fetch_truncates_large_bodies(monkeypatch):
    huge = b"<html><body>" + (b"<p>line</p>" * 50000) + b"</body></html>"

    def handler(request):
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=huge,
        )

    _install_transport(monkeypatch, handler)
    summary = fetch_and_summarize("https://example.com/big")
    assert len(summary.text) <= 5000  # cap is 4 KB + truncation marker
    assert "truncated" in summary.text
