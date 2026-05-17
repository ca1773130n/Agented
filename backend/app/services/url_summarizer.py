"""Fetch + summarize external URLs for attachment rendering.

Used by ``ContextCompilerService`` to resolve ``{kind: 'url', url:
...}`` attachments into a short text block before they go into the
prompt prepend.

Design:

* httpx is the only network dep — no BeautifulSoup or readability
  on the backend yet, so we use stdlib ``html.parser`` for tag
  stripping.
* Page size cap: 256 KB downloaded; summary cap: 4 KB.
* In-process TTL cache (1 hour) keyed by URL. The cache is
  intentionally per-process — sessions on a single gunicorn worker
  share it, but no cross-process invalidation. Good enough; a real
  cache layer is overkill for what's essentially an operator-
  triggered fetch.
* All failure modes return a non-empty result so the prompt isn't
  silently missing the URL. The "[fetch failed: <reason>]" trailer
  makes it obvious to the operator + the model that the URL
  reference is in the prompt but the content wasn't pulled.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
import threading
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


# Soft network budget — failing fast is better than holding a chat
# turn for 30s on a slow server. The operator can re-trigger the
# send if they really need the content.
_FETCH_TIMEOUT_SECONDS = 6.0
_MAX_BYTES = 256 * 1024
_MAX_SUMMARY_CHARS = 4 * 1024
_CACHE_TTL_SECONDS = 60 * 60

# Blocked schemes — only http(s). file:// would let the operator
# leak local files via the attachment channel; data: URIs are
# essentially inline content and should use the snippet kind.
_ALLOWED_SCHEMES = {"http", "https"}

# Cap on redirect hops. ``follow_redirects=True`` on the httpx client
# would short-circuit our per-hop SSRF guard, so we follow them
# manually and re-validate the host on every step. Most legitimate
# URLs settle in 1–2 hops; a chain longer than this is either
# misconfigured or hostile.
_MAX_REDIRECT_HOPS = 5


@dataclass
class UrlSummary:
    url: str
    title: str
    text: str
    error: Optional[str] = None


_cache: dict[str, tuple[float, UrlSummary]] = {}
_cache_lock = threading.Lock()


class _TitleAndTextExtractor(HTMLParser):
    """Pull document title + visible body text.

    ``<script>``/``<style>``/``<noscript>`` content is suppressed so
    we don't inject JS source into the prompt. Whitespace is
    collapsed via the join step in ``finalize``.
    """

    _SKIP_TAGS = {"script", "style", "noscript", "template", "svg"}

    def __init__(self) -> None:
        super().__init__()
        self._in_title = False
        self._title_parts: list[str] = []
        self._suppress_stack: list[str] = []
        self._text_parts: list[str] = []

    def handle_starttag(self, tag, attrs):  # noqa: D401, ARG002
        if tag == "title":
            self._in_title = True
        if tag in self._SKIP_TAGS:
            self._suppress_stack.append(tag)

    def handle_endtag(self, tag):  # noqa: D401
        if tag == "title":
            self._in_title = False
        if self._suppress_stack and self._suppress_stack[-1] == tag:
            self._suppress_stack.pop()

    def handle_data(self, data):  # noqa: D401
        if self._suppress_stack:
            return
        if self._in_title:
            self._title_parts.append(data)
            return
        chunk = data.strip()
        if chunk:
            self._text_parts.append(chunk)

    def finalize(self) -> tuple[str, str]:
        title = " ".join(p.strip() for p in self._title_parts if p.strip())
        text = " ".join(self._text_parts)
        text = re.sub(r"\s+", " ", text).strip()
        return title, text


def _is_allowed_scheme(url: str) -> bool:
    try:
        scheme = urlparse(url).scheme.lower()
    except Exception:
        return False
    return scheme in _ALLOWED_SCHEMES


def _resolve_host_addresses(host: str) -> list[ipaddress._BaseAddress]:
    """Return every A/AAAA record for ``host``.

    A single host can resolve to multiple addresses (round-robin DNS,
    happy-eyeballs IPv4+IPv6). We must validate ALL of them or an
    attacker can use a DNS record where one IP is public and another
    is private — ``socket.gethostbyname`` would return whichever the
    resolver felt like, leaving the validation outcome unstable.
    """
    addrs: list[ipaddress._BaseAddress] = []
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError):
        return addrs
    seen: set[str] = set()
    for info in infos:
        ip_str = info[4][0]
        if ip_str in seen:
            continue
        seen.add(ip_str)
        try:
            addrs.append(ipaddress.ip_address(ip_str))
        except ValueError:
            continue
    return addrs


def _is_safe_target(url: str) -> Optional[str]:
    """Validate scheme + DNS resolution. Returns reason on rejection,
    or ``None`` if the URL is safe to fetch.

    Rejects:
      * non-http(s) schemes (file://, data:, gopher:, etc.)
      * missing or empty hostnames
      * DNS-resolution failure
      * any resolved address in a private, loopback, link-local,
        multicast, reserved, or unspecified range — including the
        AWS/GCP metadata endpoints in 169.254.0.0/16, the IPv6
        loopback ``::1``, ULAs in ``fc00::/7``, and link-locals in
        ``fe80::/10``. ``ipaddress.is_global`` (Python 3.11+) is the
        canonical "publicly routable" check.
    """
    if not _is_allowed_scheme(url):
        return "scheme not allowed"
    try:
        parsed = urlparse(url)
    except Exception:
        return "invalid URL"
    host = (parsed.hostname or "").strip()
    if not host:
        return "missing host"
    # ``host`` may itself be a literal IP — short-circuit DNS in that
    # case so we still validate the address.
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    addrs: list[ipaddress._BaseAddress]
    if literal is not None:
        addrs = [literal]
    else:
        addrs = _resolve_host_addresses(host)
        if not addrs:
            return "DNS resolution failed"
    for ip in addrs:
        if not getattr(ip, "is_global", not ip.is_private):
            return f"non-global address: {ip}"
        if ip.is_loopback or ip.is_link_local or ip.is_multicast:
            return f"non-global address: {ip}"
        if ip.is_reserved or ip.is_unspecified:
            return f"non-global address: {ip}"
    return None


def _from_cache(url: str) -> Optional[UrlSummary]:
    now = time.time()
    with _cache_lock:
        hit = _cache.get(url)
        if not hit:
            return None
        cached_at, summary = hit
        if now - cached_at > _CACHE_TTL_SECONDS:
            _cache.pop(url, None)
            return None
        return summary


def _put_cache(url: str, summary: UrlSummary) -> None:
    with _cache_lock:
        _cache[url] = (time.time(), summary)


def _summarize_html(body: bytes) -> tuple[str, str]:
    try:
        text = body.decode("utf-8", errors="replace")
    except Exception:
        text = body.decode("latin-1", errors="replace")
    parser = _TitleAndTextExtractor()
    try:
        parser.feed(text)
    except Exception:
        # Malformed HTML — fall back to a regex strip so the operator
        # still gets something rather than an empty summary.
        stripped = re.sub(r"<[^>]+>", " ", text)
        stripped = re.sub(r"\s+", " ", stripped).strip()
        return "", stripped[:_MAX_SUMMARY_CHARS]
    title, body_text = parser.finalize()
    if len(body_text) > _MAX_SUMMARY_CHARS:
        body_text = body_text[:_MAX_SUMMARY_CHARS] + " […truncated]"
    return title, body_text


def fetch_and_summarize(url: str) -> UrlSummary:
    """Return a ``UrlSummary`` for ``url`` (cached for 1h).

    Follows redirects manually so we re-validate the destination
    host on every hop — ``httpx.Client(follow_redirects=True)`` would
    transparently chase a 302 to a private IP and defeat the
    upfront ``_is_safe_target`` check (CVE-class SSRF). On any
    failure returns a ``UrlSummary`` whose ``error`` is set and
    ``text`` is empty so the caller can still render the URL with a
    ``[fetch failed: ...]`` trailer.
    """
    reason = _is_safe_target(url)
    if reason is not None:
        return UrlSummary(url=url, title="", text="", error=reason)

    cached = _from_cache(url)
    if cached is not None:
        return cached

    current_url = url
    content_type = ""
    body = b""
    try:
        with httpx.Client(
            timeout=_FETCH_TIMEOUT_SECONDS,
            follow_redirects=False,
            headers={"User-Agent": "agented-context-compiler/0.7.71"},
        ) as client:
            for hop in range(_MAX_REDIRECT_HOPS + 1):
                resp = client.get(current_url)
                if 300 <= resp.status_code < 400 and "location" in resp.headers:
                    if hop == _MAX_REDIRECT_HOPS:
                        return UrlSummary(
                            url=url,
                            title="",
                            text="",
                            error="too many redirects",
                        )
                    # Resolve relative redirects against the current
                    # URL, then re-run the SSRF gate before following.
                    nxt = str(httpx.URL(current_url).join(resp.headers["location"]))
                    reason = _is_safe_target(nxt)
                    if reason is not None:
                        return UrlSummary(
                            url=url,
                            title="",
                            text="",
                            error=f"redirect blocked: {reason}",
                        )
                    current_url = nxt
                    continue
                resp.raise_for_status()
                content_type = (resp.headers.get("content-type") or "").lower()
                body = resp.content[:_MAX_BYTES]
                break
    except httpx.HTTPStatusError as exc:
        summary = UrlSummary(
            url=url, title="", text="", error=f"HTTP {exc.response.status_code}"
        )
        _put_cache(url, summary)
        return summary
    except httpx.RequestError as exc:
        return UrlSummary(url=url, title="", text="", error=str(exc) or "request error")
    except Exception as exc:
        logger.warning("url_summarizer: unexpected failure: %s", exc, exc_info=True)
        return UrlSummary(url=url, title="", text="", error="unexpected error")

    if "html" in content_type:
        title, text = _summarize_html(body)
    elif "text/" in content_type or "json" in content_type:
        try:
            text = body.decode("utf-8", errors="replace")
        except Exception:
            text = body.decode("latin-1", errors="replace")
        text = text.strip()
        if len(text) > _MAX_SUMMARY_CHARS:
            text = text[:_MAX_SUMMARY_CHARS] + " […truncated]"
        title = ""
    else:
        text = f"(binary content, {len(body)} bytes, type={content_type or 'unknown'})"
        title = ""

    summary = UrlSummary(url=url, title=title, text=text)
    _put_cache(url, summary)
    return summary


def _clear_cache_for_tests() -> None:
    """Test seam — never call from product code."""
    with _cache_lock:
        _cache.clear()
