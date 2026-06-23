"""ProductUrlAdapter — the ``product_url`` source adapter (the default kind).

The ``product_url`` kind is what ``CompetitorSourceService.detect_kind`` assigns
to ANY watched URL that isn't a github repo / arxiv / job board — i.e. a
competitor's product or marketing website. Phase 25 shipped adapters for the
specialized kinds but left ``product_url`` (the most common one an operator
pastes) without a fetcher, so the dispatcher logged "no adapter registered for
kind 'product_url' — skipping" and a watched product page produced NOTHING. This
adapter closes that gap.

Approach — a keyless, read-only content-change watcher:

* Conditional GET with the stored ETag (``If-None-Match``) → a free ``304`` is
  the ``unchanged`` fast path (like github's, when the server supports it).
* On ``200``, strip the HTML to visible text (script/style blocks + tags removed,
  whitespace collapsed) and ``sha256`` it. The hash is the ``watermark`` cursor:
  the page is *changed* iff its content hash differs from the stored watermark.
  First poll (watermark NULL) → ``changed`` (a baseline snapshot, so the operator
  sees monitoring is live + the current state).
* ``raw_ref`` is the extracted text (truncated) the EXISTING
  ``SignalSummarizerService`` reads and taint-wraps (every fetched competitor
  page is prompt-injection-tainted, OWASP LLM01 — it MUST flow through that one
  summarizer, never a new LLM path). ``raw_ref`` (content) and ``watermark``
  (cursor) stay DISTINCT, per the ``base`` contract.

Hashing the stripped *text* (not the raw bytes) keeps the cursor stable against
trivial markup churn (re-ordered attributes, a changed inline nonce) — a coarse
but useful first line; the snapshot dedup in ``AdapterBase.commit`` is the
backstop. ``poll_interval_floor_s = 21600`` (6h): a marketing page changes
slowly and there's no guaranteed 304 path, so the per-kind floor is the throttle.
``403``/``429`` → ``throttled``; transport error / non-200 → ``error``; an empty
body or text-less page → ``skipped``. ``fetch`` NEVER raises — per-source
isolation is the dispatcher's job, but the adapter is the first line.

HTTP uses ``httpx`` (the codebase's standard outbound client — no new
dependency); persistence is ``AdapterBase.commit``'s job, ``fetch`` is a pure read.
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import re
import socket
from urllib.parse import urlparse

import httpx

from app.services.competitor_source_service import KIND_PRODUCT_URL
from app.services.source_adapters import registry
from app.services.source_adapters.base import AdapterBase, FetchResult

logger = logging.getLogger(__name__)

# HTTP timeout for one page poll (seconds). Short — a poll is a cheap GET.
_POLL_TIMEOUT = 15
# Cap the extracted text handed to the summarizer: a full page can be huge, and
# the summarizer only needs enough to characterize the page/change.
_MAX_RAW_REF = 4000

# Identify Agented's monitor politely (some sites 403 a blank UA).
_HEADERS = {"User-Agent": "Agented-CompetitorIntel/1.0 (+https://agented.local; monitoring)"}

# Strip <script>/<style>/<noscript> blocks (content + tags) BEFORE removing the
# rest of the tags, so their bodies don't leak into the extracted text.
_BLOCK_RE = re.compile(r"<(script|style|noscript)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
# The handful of HTML entities common in visible text — a cheap unescape (no
# parser dependency); anything else is left as-is (harmless for a content hash).
_ENTITIES = {
    "&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">",
    "&quot;": '"', "&#39;": "'", "&apos;": "'",
}


def _extract_text(html: str) -> str:
    """Reduce an HTML document to its collapsed visible text.

    script/style/noscript bodies are dropped, then all tags, then a few common
    entities are unescaped and whitespace is collapsed. Crude by design (no
    parser dependency) but stable enough that the content hash tracks meaningful
    page changes rather than markup noise.
    """
    text = _BLOCK_RE.sub(" ", html)
    text = _TAG_RE.sub(" ", text)
    for ent, char in _ENTITIES.items():
        text = text.replace(ent, char)
    return _WS_RE.sub(" ", text).strip()


# Max redirect hops to follow MANUALLY (each one re-validated for SSRF — httpx's
# own follow_redirects cannot validate the intermediate hops).
_MAX_REDIRECTS = 5


class _UnsafeUrl(Exception):
    """A URL that must NOT be fetched server-side: a non-http(s) scheme, or a host
    resolving to a private/internal address (the SSRF guard)."""


def _host_is_public(host: str) -> bool:
    """True iff EVERY resolved IP for ``host`` is a public address.

    Returns ``False`` on a resolution failure or ANY private / loopback /
    link-local (incl. cloud metadata ``169.254.169.254``) / reserved / multicast /
    unspecified IP. This is the SSRF guard for fetching operator-supplied URLs.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
            # Catch-all for any non-globally-routable range the explicit predicates
            # miss — notably 100.64.0.0/10 (carrier-grade NAT) — and future-proof.
            or not addr.is_global
        ):
            return False
    return True


def _safe_get(url: str, headers: dict) -> httpx.Response:
    """SSRF-safe GET: http(s) only; the URL host AND every redirect hop's host
    must resolve to PUBLIC IPs.

    Redirects are followed MANUALLY (``follow_redirects=False`` per hop) so each
    target is re-validated — otherwise a public URL could ``30x``-redirect to an
    internal address (metadata service, localhost, a private API). Raises
    ``_UnsafeUrl`` for a bad scheme/host; the caller maps that to ``skipped``.

    ponytail: resolve-then-connect leaves a narrow DNS-rebinding window —
    acceptable for semi-trusted operator URLs; pin the resolved IP if the input
    ever becomes hostile.
    """
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        parsed = urlparse(current)
        if parsed.scheme not in ("http", "https"):
            raise _UnsafeUrl(f"scheme {parsed.scheme!r} not allowed")
        host = parsed.hostname
        if not host or not _host_is_public(host):
            raise _UnsafeUrl(f"non-public host {host!r}")
        resp = httpx.get(
            current, timeout=_POLL_TIMEOUT, headers=headers, follow_redirects=False
        )
        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location")
            if not location:
                return resp
            current = str(httpx.URL(current).join(location))
            continue
        return resp
    raise _UnsafeUrl("too many redirects")


class ProductUrlAdapter(AdapterBase):
    """Keyless read-only content-change watcher for ``product_url`` sources."""

    kind = KIND_PRODUCT_URL
    # No guaranteed ETag/304 path, so the per-kind poll floor is the throttle.
    poll_interval_floor_s = 21600  # 6h

    def has_credential(self) -> bool:
        """Always ``True`` — a public web page is a keyless GET (no auth to gate)."""
        return True

    def fetch(self, source: dict) -> FetchResult:
        """One conditional GET of ``source['url']``; map outcomes to ``FetchResult``.

        * blank / scheme-less URL → ``skipped``
        * ``304`` (ETag match) → ``unchanged`` (free path)
        * ``403`` / ``429`` → ``throttled`` (back off this kind)
        * transport error / non-200 → ``error``
        * ``200`` whose stripped-text hash == stored watermark → ``unchanged``
        * ``200`` with a new/changed hash (or first poll) → ``changed`` with
          ``raw_ref`` (truncated page text), ``watermark`` = the content hash,
          ``content_hash`` = same, and ``etag`` = the response ETag (for the next
          conditional GET).
        """
        source_id = source.get("id")
        url = (source.get("url") or "").strip()
        if "://" not in url:
            logger.warning("competitor product_url source %s has no fetchable URL", source_id)
            return FetchResult(outcome="skipped")

        headers = dict(_HEADERS)
        etag = source.get("etag")
        if etag:
            headers["If-None-Match"] = etag

        try:
            resp = _safe_get(url, headers)
        except _UnsafeUrl:
            # Non-http(s) scheme or an internal/private host (SSRF) — never fetch.
            logger.warning("competitor product_url blocked unsafe URL for source %s", source_id)
            return FetchResult(outcome="skipped")
        except Exception:  # noqa: BLE001 — fetch MUST never raise (per-source isolation)
            # Transport error, httpx.InvalidURL, or any other fetch failure.
            logger.warning(
                "competitor product_url fetch failed for source %s", source_id, exc_info=True
            )
            return FetchResult(outcome="error")

        status = resp.status_code
        if status == 304:
            return FetchResult(outcome="unchanged")
        if status in (403, 429):
            logger.warning(
                "competitor product_url throttled (HTTP %d) for source %s", status, source_id
            )
            return FetchResult(outcome="throttled")
        if status != 200:
            logger.warning(
                "competitor product_url unexpected HTTP %d for source %s", status, source_id
            )
            return FetchResult(outcome="error")

        text = _extract_text(resp.text or "")
        if not text:
            # A text-less page (e.g. a pure-JS shell with no SSR content) — nothing
            # to hash or summarize; skip rather than emit an empty snapshot.
            return FetchResult(outcome="skipped")

        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if source.get("watermark") == content_hash:
            return FetchResult(outcome="unchanged")

        return FetchResult(
            outcome="changed",
            raw_ref=text[:_MAX_RAW_REF],
            watermark=content_hash,
            etag=resp.headers.get("ETag"),
            content_hash=content_hash,
        )


# Register on import (the package __init__ imports this module). Last-write-wins.
registry.register(ProductUrlAdapter())
