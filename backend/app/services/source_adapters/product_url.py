"""ProductUrlAdapter — the ``product_url`` source adapter (the default kind).

The ``product_url`` kind is what ``CompetitorSourceService.detect_kind`` assigns
to ANY watched URL that isn't a github repo / arxiv / job board — i.e. a
competitor's product or marketing website. Phase 25 shipped adapters for the
specialized kinds but left ``product_url`` (the most common one an operator
pastes) without a fetcher, so the dispatcher logged "no adapter registered for
kind 'product_url' — skipping" and a watched product page produced NOTHING. This
adapter closes that gap.

Approach — a keyless, read-only content-change watcher that CRAWLS the product
site (not just the landing page):

* GET the seed URL, then follow up to ``_MAX_CRAWL_PAGES`` SAME-SITE links to the
  product's feature / pricing / docs / about pages (``_select_links`` orders those
  first) so the summary characterizes the whole product, not just the home page.
  Each crawled URL is re-validated by ``_safe_get`` (SSRF) and is best-effort — a
  bad sub-page is skipped, never fatal.
* Strip every fetched page to visible text, combine them (feature pages first,
  each path-tagged + per-page capped), and ``sha256`` the COMBINED text as the
  ``watermark`` cursor: the site is *changed* iff the combined hash differs from
  the stored watermark (so a change on ANY crawled page is detected). First poll
  (watermark NULL) → ``changed`` (a baseline snapshot of the whole product).
  No conditional GET on the seed — we always need its HTML to discover sub-pages,
  and a seed-only ``304`` would miss changes on the crawled pages.
* ``raw_ref`` is the combined extracted text (capped to ~the taint layer's content
  limit, feature pages first) the EXISTING
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
# Crawl: beyond the seed (home) page, follow up to this many SAME-SITE links to
# the product's feature/pricing/docs pages so the summary characterizes the whole
# product, not just the landing page. Each page is bounded, and the WHOLE crawl is
# small and runs at the 6h poll floor — a handful of GETs to one host.
_MAX_CRAWL_PAGES = 6
# Per-page text cap (bounds each page's contribution to the combined blob + hash).
_PER_PAGE_CHARS = 1800
# Cap the combined text handed to the summarizer. ~= the taint layer's
# _MAX_CONTENT_CHARS (8 KiB) so nothing past it is wasted; feature pages are
# ordered FIRST so they survive the cap. The change-detection hash uses the FULL
# combined text (uncapped) so a change on ANY crawled page is still detected.
_MAX_RAW_REF = 8000

# Anchor href extractor (crude, no parser dep) + the path keywords that mark a
# page as feature/pricing/positioning-relevant (crawled first).
_HREF_RE = re.compile(r"<a\b[^>]*\bhref\s*=\s*[\"']([^\"'#]+)[\"']", re.IGNORECASE)
_FEATURE_HINTS = (
    "feature",
    "pricing",
    "price",
    "plans",
    "product",
    "solution",
    "platform",
    "capabilit",
    "use-case",
    "use_case",
    "usecase",
    "integration",
    "docs",
    "documentation",
    "about",
    "overview",
    "compare",
    "why-",
)

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
    "&nbsp;": " ",
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&#39;": "'",
    "&apos;": "'",
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


def _same_site(host_a: str, host_b: str) -> bool:
    """True iff two hosts are the same site, ignoring a leading ``www.`` so a
    home page that links to ``www.`` (or vice versa) still counts as same-site."""
    if not host_a or not host_b:
        return False
    return host_a.lower().removeprefix("www.") == host_b.lower().removeprefix("www.")


def _select_links(html: str, base_url: str) -> list[str]:
    """Same-site links from ``html``, absolutised against ``base_url``, deduped on
    scheme+host+path (query/fragment dropped), seed excluded, and ordered so
    feature/pricing/docs pages come first (the crawl cap trims the long tail).

    Off-site links, non-http(s) schemes, and mailto/tel/js are excluded here; each
    selected URL is STILL re-validated by ``_safe_get`` (SSRF) before any fetch.

    # ponytail: robots.txt is not consulted — same-site + a small page cap + a
    # polite UA at a 6h floor is light-touch; add a robots check if a target asks.
    """
    base = urlparse(base_url)
    seed = f"{base.scheme}://{base.netloc}{base.path}".rstrip("/")
    seen: set[str] = set()
    scored: list[tuple[int, str]] = []
    for m in _HREF_RE.finditer(html or ""):
        href = m.group(1).strip()
        if not href or href.lower().startswith(("mailto:", "tel:", "javascript:", "data:")):
            continue
        try:
            absu = urlparse(str(httpx.URL(base_url).join(href)))
        except Exception:  # noqa: BLE001 — a malformed href just gets skipped
            continue
        if absu.scheme not in ("http", "https") or not _same_site(absu.hostname, base.hostname):
            continue
        clean = f"{absu.scheme}://{absu.netloc}{absu.path}".rstrip("/")
        if not clean or clean == seed or clean in seen:
            continue
        seen.add(clean)
        path_l = (absu.path or "").lower()
        # 0 (feature page) sorts before 1 (everything else); stable within a tier.
        scored.append((0 if any(h in path_l for h in _FEATURE_HINTS) else 1, clean))
    scored.sort(key=lambda t: t[0])
    return [u for _, u in scored]


def _combine_pages(pages: list[tuple[str, str]]) -> str:
    """Join ``(url, text)`` pages into one labelled blob (each page path-tagged so
    the summarizer can attribute features to a page), per-page capped."""
    parts = []
    for url, text in pages:
        parts.append(f"[{urlparse(url).path or '/'}]\n{text[:_PER_PAGE_CHARS]}")
    return "\n\n".join(parts)


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
        resp = httpx.get(current, timeout=_POLL_TIMEOUT, headers=headers, follow_redirects=False)
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
        """GET ``source['url']`` then CRAWL its same-site feature/pricing/docs pages,
        combine the visible text, and map outcomes to ``FetchResult``.

        * blank / scheme-less URL → ``skipped``
        * ``403`` / ``429`` on the seed → ``throttled`` (back off this kind)
        * transport error / non-200 on the seed → ``error``
        * seed ``200`` then crawl up to ``_MAX_CRAWL_PAGES`` same-site pages
          (each SSRF-revalidated, best-effort — a bad sub-page is skipped, never
          fatal). The COMBINED text's hash is the watermark:
            - hash == stored watermark → ``unchanged``
            - new/changed hash (or first poll) → ``changed`` with ``raw_ref``
              (the combined, feature-page-first text, capped), ``watermark`` /
              ``content_hash`` = the combined hash, ``etag`` = the seed's ETag.

        No conditional GET on the seed: we always need its HTML to discover the
        sub-pages, and a seed-only 304 would miss changes on the crawled pages.
        """
        source_id = source.get("id")
        url = (source.get("url") or "").strip()
        if "://" not in url:
            logger.warning("competitor product_url source %s has no fetchable URL", source_id)
            return FetchResult(outcome="skipped")

        try:
            resp = _safe_get(url, dict(_HEADERS))
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
        # We don't send If-None-Match, but a caching layer could still answer 304 —
        # treat it as unchanged rather than a spurious error.
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

        home_html = resp.text or ""
        home_text = _extract_text(home_html)
        if not home_text:
            # A text-less page (e.g. a pure-JS shell with no SSR content) — nothing
            # to hash or summarize; skip rather than emit an empty snapshot.
            return FetchResult(outcome="skipped")

        # Crawl the same-site feature/pricing/docs pages (feature pages first).
        pages: list[tuple[str, str]] = [(url, home_text)]
        for link in _select_links(home_html, url)[:_MAX_CRAWL_PAGES]:
            try:
                sub = _safe_get(link, dict(_HEADERS))
            except Exception:  # noqa: BLE001 — per-page best-effort; SSRF/transport just skips
                continue
            if sub.status_code != 200:
                continue
            ctype = sub.headers.get("Content-Type", "")
            if ctype and "html" not in ctype.lower():
                continue  # only mine HTML pages (skip PDFs/feeds/binaries)
            sub_text = _extract_text(sub.text or "")
            if sub_text:
                pages.append((link, sub_text))

        combined = _combine_pages(pages)
        # Hash the FULL combined text so a change on any crawled page is detected;
        # store/summarize only the capped, feature-first prefix.
        content_hash = hashlib.sha256(combined.encode("utf-8")).hexdigest()
        if source.get("watermark") == content_hash:
            return FetchResult(outcome="unchanged")

        return FetchResult(
            outcome="changed",
            raw_ref=combined[:_MAX_RAW_REF],
            watermark=content_hash,
            etag=resp.headers.get("ETag"),
            content_hash=content_hash,
        )


# Register on import (the package __init__ imports this module). Last-write-wins.
registry.register(ProductUrlAdapter())
