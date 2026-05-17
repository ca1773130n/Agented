"""Tests for ``url_summarizer.fetch_and_summarize``.

Uses ``httpx.MockTransport`` so no real network is touched. Each
test clears the in-process cache to stay independent of execution
order.
"""

from __future__ import annotations

import httpx
import pytest

import ipaddress

from app.services import url_summarizer
from app.services.url_summarizer import (
    UrlSummary,
    _summarize_html,
    fetch_and_summarize,
)


def httpx_safe_public_ip() -> ipaddress.IPv4Address:
    """Return an IPv4 address that ``_is_global_ip`` considers safe.

    ``192.0.2.1`` is in TEST-NET-1 (RFC 5737), reserved for
    documentation — guaranteed not to be a real production target
    but ``is_global`` returns True for it under Python's stdlib.
    Using a documentation block keeps the tests hermetic.
    """
    return ipaddress.ip_address("192.0.2.1")


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


# -----------------------------------------------------------------
# SSRF gate — direct IPs, AWS metadata, redirect chains
# -----------------------------------------------------------------


def test_fetch_blocks_literal_loopback_ipv4():
    summary = fetch_and_summarize("http://127.0.0.1/admin")
    assert summary.error and "non-global address" in summary.error


def test_fetch_blocks_literal_loopback_ipv6():
    summary = fetch_and_summarize("http://[::1]/admin")
    assert summary.error and "non-global address" in summary.error


def test_fetch_blocks_private_rfc1918():
    summary = fetch_and_summarize("http://10.0.0.1/")
    assert summary.error and "non-global address" in summary.error
    summary = fetch_and_summarize("http://192.168.1.1/")
    assert summary.error and "non-global address" in summary.error


def test_fetch_blocks_aws_metadata_endpoint():
    summary = fetch_and_summarize("http://169.254.169.254/latest/meta-data/")
    assert summary.error and "non-global address" in summary.error


def test_fetch_blocks_redirect_to_loopback(monkeypatch):
    """The SSRF gate runs on the original URL AND every redirect hop —
    a 302 to a private IP must be rejected, not followed.
    """

    def handler(request):
        return httpx.Response(
            302,
            headers={"location": "http://127.0.0.1/admin"},
        )

    _install_transport(monkeypatch, handler)
    summary = fetch_and_summarize("https://example.com/safe")
    assert summary.error and "redirect blocked" in summary.error
    assert "non-global address" in summary.error


def test_fetch_blocks_redirect_to_aws_metadata(monkeypatch):
    def handler(request):
        return httpx.Response(
            301,
            headers={"location": "http://169.254.169.254/latest/meta-data/"},
        )

    _install_transport(monkeypatch, handler)
    summary = fetch_and_summarize("https://example.com/innocent")
    assert summary.error and "redirect blocked" in summary.error


def test_fetch_blocks_redirect_to_file_scheme(monkeypatch):
    def handler(request):
        return httpx.Response(
            302,
            headers={"location": "file:///etc/passwd"},
        )

    _install_transport(monkeypatch, handler)
    summary = fetch_and_summarize("https://example.com/safe")
    assert summary.error and "redirect blocked" in summary.error
    assert "scheme" in summary.error


def test_fetch_caps_redirect_hops(monkeypatch):
    """A redirect loop that stays within public IPs (or non-validating
    hops via relative URLs) still has to terminate — otherwise the
    fetch could hang the chat turn. ``_MAX_REDIRECT_HOPS`` enforces it.
    """
    counter = {"n": 0}

    def handler(request):
        counter["n"] += 1
        # Bounce to a fresh public-looking URL each hop so the SSRF
        # gate doesn't reject — we want to test the hop counter.
        return httpx.Response(
            302,
            headers={"location": f"https://example.com/hop{counter['n']}"},
        )

    _install_transport(monkeypatch, handler)
    summary = fetch_and_summarize("https://example.com/start")
    assert summary.error == "too many redirects"


def test_fetch_pins_request_to_resolved_ip(monkeypatch):
    """Defense-in-depth check that httpx is told to connect to the
    pre-validated IP literal (and carries the original hostname in
    ``Host`` + the ``sni_hostname`` extension). Without pinning, an
    adversarial DNS server could return a public IP on the safety
    check and a private IP on httpx's second resolution attempt
    (DNS-rebinding / TOCTOU). The pin makes that attack impossible.
    """
    seen: list[dict] = []

    def handler(request):
        seen.append(
            {
                "url": str(request.url),
                "host_header": request.headers.get("host"),
                "sni": request.extensions.get("sni_hostname"),
            }
        )
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"<html><head><title>P</title></head><body>x</body></html>",
        )

    _install_transport(monkeypatch, handler)
    # Force a known IP so the assertions are deterministic. We
    # patch the resolver to return a single public-looking address.
    fake_ip = httpx_safe_public_ip()
    monkeypatch.setattr(
        url_summarizer,
        "_resolve_safe_ip",
        lambda host: (fake_ip, ""),
    )
    summary = fetch_and_summarize("https://example.com/path?x=1")
    assert summary.error is None
    assert seen, "expected the mock transport to see one request"
    req = seen[0]
    # URL netloc rewritten to the literal IP.
    assert str(fake_ip) in req["url"]
    assert "example.com" not in req["url"]
    # Host header carries the original hostname so the server can
    # route + the certificate can validate.
    assert req["host_header"] == "example.com"
    # SNI extension also carries the hostname for TLS handshake.
    assert req["sni"] == "example.com"


def test_fetch_blocks_dns_rebinding_between_validate_and_connect(monkeypatch):
    """Simulate DNS rebinding: ``_resolve_safe_ip`` is called once
    upfront (returns a public IP), then again at fetch time (returns
    a private IP). Pre-pin guarantees the fetch uses the validated
    IP, so the rebinding attempt fails closed.
    """
    call_count = {"n": 0}

    def flaky_resolve(host):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return (httpx_safe_public_ip(), "")
        # Second resolution returns loopback — would be exploited
        # without IP pinning. With pinning, this triggers the
        # second-tier rejection.
        import ipaddress
        loop = ipaddress.ip_address("127.0.0.1")
        return (loop, "non-global address: 127.0.0.1")

    monkeypatch.setattr(url_summarizer, "_resolve_safe_ip", flaky_resolve)

    def handler(request):
        return httpx.Response(200, content=b"should not reach")

    _install_transport(monkeypatch, handler)
    summary = fetch_and_summarize("https://example.com/path")
    # The _is_safe_target call sees the public IP, gate passes.
    # Then the fetch loop calls _resolve_safe_ip again and gets the
    # private IP — fetch aborts before httpx connects.
    assert summary.error == "non-global address: 127.0.0.1"
    assert call_count["n"] >= 2


def test_fetch_follows_one_public_redirect(monkeypatch):
    """A single safe redirect lands on the real content — verify the
    happy path through the manual hop loop still resolves.
    """
    hop = {"step": 0}

    def handler(request):
        hop["step"] += 1
        if hop["step"] == 1:
            return httpx.Response(
                302,
                headers={"location": "https://example.com/final"},
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"<html><head><title>Final</title></head><body>landed</body></html>",
        )

    _install_transport(monkeypatch, handler)
    summary = fetch_and_summarize("https://example.com/start")
    assert summary.error is None
    assert summary.title == "Final"
    assert "landed" in summary.text
