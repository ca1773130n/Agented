"""HNAdapter — the ``hn_query`` source adapter (phase 25, plan 05).

Hacker News is *market signal*: a competitor's launch, Show HN, or a discussion
naming them is an early demand/sentiment read, often the first public chatter
before press. This adapter turns an operator-supplied SEARCH QUERY (a company /
product name) into normalized ``competitor_snapshot`` rows that the EXISTING
``SignalSummarizerService`` (unchanged) converts to ``detected_signal`` rows. No
new pipeline, no new LLM path, no UI change — only a new fetcher behind the
25-01 ``SourceAdapter`` seam.

The source identifier is a QUERY, not a URL: unlike github/arxiv/job_board the
``source['url']`` column holds the free-text search string (a company name). It
is therefore added via ``add_source(..., kind=KIND_HN_QUERY)`` (the explicit-kind
path), since the URL-host ``detect_kind`` can't route a bare name.

The query runs against the **keyless, read-only** HN Algolia search API
(research §4.1 [8][9]):

* ``GET https://hn.algolia.com/api/v1/search_by_date``
  ``?query=<q>&tags=story&numericFilters=created_at_i><watermark>``

``search_by_date`` is reverse-chronological; ``tags=story`` scopes to stories
(not comments). No auth, no key (~10k req/hr soft cap) — ``has_credential`` is
always ``True`` (a keyless read needs no credential; there is no auth to omit).

Incremental dedup (research §4.1): each hit has a stable ``objectID`` and a
numeric ``created_at_i`` (epoch seconds). The watermark is ``max(created_at_i)``
across the returned hits (a monotonic cursor); a hit is *new* iff its
``created_at_i`` is strictly greater than the stored watermark. We ALSO pass
``numericFilters=created_at_i><watermark>`` server-side so the API only returns
newer stories (working around the 1,000-hit/query cap), and re-apply the
watermark client-side as defense-in-depth. The first poll (watermark NULL) omits
the numericFilter and takes the current newest window.

``raw_ref`` is a SHORT human-readable text block — ``"<title> — <url> (<points>
pts, by <author>)"`` per new story — the CONTENT the summarizer reads (and
taint-wraps; every fetched title/url is prompt-injection-tainted, OWASP LLM01),
DISTINCT from the watermark cursor (NOT a bare ``created_at_i`` number; P1's
``_extract_content`` lesson). Per-item isolation: a malformed hit is skipped, not
fatal.

``poll_interval_floor_s = 3600`` (1h): there is no ETag/304 free path, so the
25-01 per-kind poll floor is what throttles this kind (the dispatcher enforces
``now - last_polled_at >= floor_s``). The Algolia soft cap is generous (~10k/hr),
so an hourly floor per query is comfortably safe. ``403``/``429`` -> ``throttled``;
a transport/parse failure -> ``error``; no new stories -> ``unchanged``. This
method NEVER raises for a bad payload — per-source isolation is the dispatcher's
job, but the adapter is the first line.

Persistence is owned by ``AdapterBase.commit`` (sha256 + dedup + cursor write);
``fetch`` is a pure read. HTTP uses ``httpx`` — the codebase's standard outbound
client (matching ``job_board`` / ``arxiv``) — no new dependency.
"""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlencode

import httpx

from app.services.competitor_source_service import KIND_HN_QUERY
from app.services.source_adapters import registry
from app.services.source_adapters.base import AdapterBase, FetchResult

logger = logging.getLogger(__name__)

# HTTP timeout for one HN poll (seconds). Short — a poll is a cheap GET.
_POLL_TIMEOUT = 15

# The keyless read-only HN Algolia search endpoint (reverse-chronological).
_SEARCH_ENDPOINT = "https://hn.algolia.com/api/v1/search_by_date"

# Bounded result window — NEWEST-first. This is a change-monitor, not a crawler:
# we only need the most-recent stories since the watermark.
_HITS_PER_PAGE = 50


def _build_url(query: str, watermark: Optional[str]) -> str:
    """Build the keyless ``search_by_date`` URL for ``query`` (+ optional cursor).

    ``tags=story`` scopes to stories. When a watermark exists, a server-side
    ``numericFilters=created_at_i><watermark>`` only returns stories strictly
    newer than the cursor (working around the 1,000-hit/query cap); the first
    poll (watermark NULL) omits the filter and takes the newest window.
    ``urlencode`` escapes the operator query so it can't inject extra params.
    """
    params: dict[str, object] = {
        "query": query,
        "tags": "story",
        "hitsPerPage": _HITS_PER_PAGE,
    }
    # Server-side incremental filter: only stories created after the cursor.
    # ``created_at_i`` is epoch seconds (int); the stored watermark is its str.
    if watermark:
        try:
            cursor = int(watermark)
        except (TypeError, ValueError):
            cursor = None
        if cursor is not None:
            params["numericFilters"] = f"created_at_i>{cursor}"
    return f"{_SEARCH_ENDPOINT}?{urlencode(params)}"


def _normalize_hits(payload: object) -> list[dict]:
    """Normalize an Algolia payload to ``[{id, created_at_i, title, url, points, author}]``.

    Algolia: ``{"hits": [{"objectID", "created_at_i", "title", "url", "points",
    "author"}]}``. ``created_at_i`` is coerced to ``int`` (epoch seconds); a hit
    with no usable ``objectID`` or no integer ``created_at_i`` is DROPPED (it
    can't be deduped — per-item isolation). Never raises on a missing field — a
    malformed shape yields ``[]`` and the caller treats it as no-new.
    """
    raw = payload.get("hits", []) if isinstance(payload, dict) else []
    if not isinstance(raw, list):
        return []

    hits: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        object_id = item.get("objectID")
        created_at_i = item.get("created_at_i")
        if object_id is None or not isinstance(created_at_i, int):
            # bool is an int subclass; created_at_i is never a bool in practice,
            # but a non-int (str/None) hit is unsortable -> drop it.
            continue
        # A "story" may carry its title in ``title`` (Show HN / link) or, for an
        # Ask HN, in ``story_title``; fall back gracefully.
        title = item.get("title") or item.get("story_title") or ""
        url = item.get("url") or item.get("story_url") or ""
        points = item.get("points")
        author = item.get("author") or ""
        hits.append(
            {
                "id": str(object_id),
                "created_at_i": created_at_i,
                "title": str(title),
                "url": str(url),
                "points": points if isinstance(points, int) else None,
                "author": str(author),
            }
        )
    return hits


def _render_stories(new_hits: list[dict]) -> str:
    """Render new stories as the human-readable text block the summarizer reads.

    One ``"<title> — <url> (<points> pts, by <author>)"`` line per new story —
    the CONTENT (taint-wrapped by the summarizer), DISTINCT from the watermark
    cursor. NOT a bare ``created_at_i`` number. Missing url / points / author are
    omitted so the line stays readable.
    """
    lines: list[str] = []
    for hit in new_hits:
        title = hit.get("title") or "(untitled story)"
        line = title
        url = hit.get("url")
        if url:
            line = f"{line} — {url}"
        meta: list[str] = []
        points = hit.get("points")
        if points is not None:
            meta.append(f"{points} pts")
        author = hit.get("author")
        if author:
            meta.append(f"by {author}")
        if meta:
            line = f"{line} ({', '.join(meta)})"
        lines.append(line)
    return "New Hacker News stories:\n" + "\n".join(lines)


class HNAdapter(AdapterBase):
    """Keyless read-only poller for ``hn_query`` competitor sources (HN Algolia).

    Reads the SEARCH QUERY from ``source['url']`` (the identifier column — a
    company/product name, not a URL), GETs the unauthenticated ``search_by_date``
    endpoint with a server-side ``created_at_i>`` cursor, and returns a
    ``FetchResult`` with the new-stories text block as ``raw_ref`` and
    ``max(created_at_i)`` as ``watermark``. Persistence (snapshot + cursor) is
    ``AdapterBase.commit``'s job; ``fetch`` never persists and never raises.
    """

    kind = KIND_HN_QUERY
    # No ETag/304 free path; the per-kind poll floor is the only throttle. The
    # Algolia soft cap (~10k req/hr) is generous, so an hourly floor per query is
    # comfortably safe.
    poll_interval_floor_s = 3600  # 1h

    def has_credential(self) -> bool:
        """Always ``True`` — the HN Algolia search API is a keyless public read.

        There is no credential to gate on (no token, no auth header is ever
        constructed), so the dispatcher never skips an hn_query source for a
        missing credential. The never-unauth rule does not apply: there is no
        auth to omit.
        """
        return True

    def fetch(self, source: dict) -> FetchResult:
        """One keyless read-only ``search_by_date`` GET; map outcomes to ``FetchResult``.

        * blank/empty query -> ``outcome='skipped'`` (no HTTP call)
        * ``403`` / ``429`` -> ``outcome='throttled'`` (back off this kind)
        * transport error / non-200 / malformed JSON -> ``outcome='error'``
        * ``200`` with NO hit whose ``created_at_i`` > watermark ->
          ``outcome='unchanged'`` (no write)
        * ``200`` with new stories -> ``outcome='changed'`` with ``raw_ref`` (the
          new-stories text block the summarizer reads), ``watermark`` =
          ``max(created_at_i)`` across the returned hits, and ``etag=None`` (HN
          has no conditional-GET cursor).

        NEVER raises for a bad payload — a transport/parse failure is caught and
        returned as ``error``.
        """
        source_id = source.get("id")
        query = (source.get("url") or "").strip()
        if not query:
            # No search query stored — nothing to poll.
            logger.warning("competitor source %s has no HN search query", source_id)
            return FetchResult(outcome="skipped")

        watermark = source.get("watermark")
        url = _build_url(query, watermark)
        try:
            # Read-only, UNAUTHENTICATED public GET — no Authorization header.
            resp = httpx.get(url, timeout=_POLL_TIMEOUT, follow_redirects=False)
        except httpx.HTTPError:
            # Transport error (DNS / timeout / connection) — per-source failure,
            # not a rate limit; skip this source, keep polling the rest.
            logger.warning("competitor HN HTTP error for source %s", source_id, exc_info=True)
            return FetchResult(outcome="error")

        status = resp.status_code

        # HN/Algolia rate limit / forbidden -> back off this kind, write nothing.
        if status in (403, 429):
            logger.warning("competitor HN throttled (HTTP %d) for source %s", status, source_id)
            return FetchResult(outcome="throttled")

        if status != 200:
            logger.warning("competitor HN unexpected HTTP %d for source %s", status, source_id)
            return FetchResult(outcome="error")

        try:
            payload = resp.json()
        except (ValueError, TypeError):
            # Malformed JSON body — a per-source error, never a raise.
            logger.warning("competitor HN malformed JSON for source %s", source_id)
            return FetchResult(outcome="error")

        hits = _normalize_hits(payload)
        if not hits:
            # No stories at all (empty result / garbage payload) -> nothing new.
            return FetchResult(outcome="unchanged")

        # Incremental created_at_i dedup. The server-side numericFilter already
        # excludes seen stories; re-apply client-side as defense-in-depth so a
        # boundary hit (created_at_i == cursor) can't re-fire. First poll (no
        # watermark) takes ALL returned hits.
        cursor: Optional[int] = None
        if watermark:
            try:
                cursor = int(watermark)
            except (TypeError, ValueError):
                cursor = None
        new_hits = [h for h in hits if cursor is None or h["created_at_i"] > cursor]
        if not new_hits:
            return FetchResult(outcome="unchanged")

        # Monotonic cursor across ALL returned hits (not just the new set), so a
        # later poll that re-sees the same max doesn't re-fire. Stored as str
        # (the watermark column is TEXT).
        new_watermark = str(max(h["created_at_i"] for h in hits))
        raw_ref = _render_stories(new_hits)
        return FetchResult(
            outcome="changed",
            raw_ref=raw_ref,
            watermark=new_watermark,
            etag=None,
        )


# Register on import (the package __init__ imports this module). Last-write-wins.
registry.register(HNAdapter())
