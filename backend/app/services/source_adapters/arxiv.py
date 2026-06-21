"""ArxivAdapter — the ``arxiv`` source adapter (phase 25, plan 03).

A research-led competitor's new papers (by category, author, or query) are
*technique lead time*: a paper often precedes a shipped capability by months.
This adapter turns an operator-pasted ``arxiv.org`` source into normalized
``competitor_snapshot`` rows that the EXISTING ``SignalSummarizerService``
(unchanged) converts to ``detected_signal`` rows. No new pipeline, no migration,
no new LLM path, no UI change — only a new fetcher behind the 25-01
``SourceAdapter`` seam. ``KIND_ARXIV`` and ``detect_kind`` already existed since
P1 (``competitor_source_service.py``: ``arxiv.org`` -> ``arxiv``) but the kind
had **no adapter**; this plan supplies only the fetcher.

The legacy export API is a **keyless, read-only GET** (research §5A [23][24][25]):

* ``GET https://export.arxiv.org/api/query?search_query=<q>``
  ``&sortBy=submittedDate&sortOrder=descending&max_results=<N small>``

The response is **Atom 1.0 XML ONLY** — even an error is returned as an Atom
feed (an ``<entry>`` whose ``<id>`` is an ``arxiv.org/api/errors#...`` URL), so
the body is ALWAYS parsed as XML, never JSON. Parsing uses
``defusedxml.ElementTree`` (the feed is UNTRUSTED competitor content, so the
stdlib parser's XXE / billion-laughs exposure is hardened away — ``defusedxml``
is already in the lockfile, no new dependency); a non-feed / error document
yields ``outcome='error'`` and NEVER raises (per-source isolation is the
dispatcher's job, but the adapter is the first line).

Rate discipline is **two-layered and HARD** (research §5A — arXiv asks for at
most 1 request / 3 seconds *in aggregate* and a poll cadence of at most once per
day, with no full-corpus crawling):

* ``poll_interval_floor_s = 86400`` (daily) — the per-kind 25-01 poll floor the
  dispatcher enforces (``now - last_polled_at >= floor_s``) keeps EACH query's
  cadence to at most once per day.
* a module-level ``time.monotonic()`` gate ``_arxiv_rate_gate()`` serializes
  EVERY arXiv request to ``>= 3.0s`` apart **across the whole batch** (the gate
  is process-global, not per-source — sharding multiple sources to evade the
  aggregate limit is BANNED). It sleeps only the remaining delta.

We do NOT crawl the full corpus: ``max_results`` is bounded (small, newest-first
``submittedDate`` feed). Incremental dedup (research §5A): each entry has a
stable ``id`` and a ``published`` (submittedDate) timestamp. The watermark is
``max(published)`` across the returned entries (a monotonic cursor); an entry is
*new* iff its ``published`` is strictly greater than the stored watermark. The
first poll (watermark NULL) takes the current newest window. ``raw_ref`` is a
human-readable ``"<title>\n<authors>\n<summary(abstract)>"`` block per new entry
— DISTINCT from the watermark cursor; it flows UNCHANGED through the summarizer's
``_wrap_tainted`` (every fetched abstract is prompt-injection-tainted, OWASP
LLM01). arXiv metadata is CC0, so no attribution is required.

Persistence is owned by ``AdapterBase.commit`` (sha256 + dedup + cursor write);
``fetch`` is a pure read. HTTP uses ``httpx`` — the codebase's standard outbound
client (matching ``github_monitor_service`` / ``job_board``) — no new dependency.
"""

from __future__ import annotations

import logging
import time
from threading import Lock
from typing import Optional
from urllib.parse import urlencode, urlparse
from xml.etree.ElementTree import Element  # type-hints only; parse via defusedxml

import defusedxml.ElementTree as ET  # XXE / billion-laughs hardened (untrusted feed)
import httpx

from app.services.competitor_source_service import KIND_ARXIV
from app.services.source_adapters import registry
from app.services.source_adapters.base import AdapterBase, FetchResult

logger = logging.getLogger(__name__)

# HTTP timeout for one arXiv poll (seconds). Short — a poll is a cheap GET.
_POLL_TIMEOUT = 30

# The legacy export API base (read-only Atom query endpoint). HTTP (not HTTPS) is
# arXiv's documented host for this API; it is a public GET with no credential.
_EXPORT_ENDPOINT = "https://export.arxiv.org/api/query"

# Bounded result window — NEWEST-first, small. This is a change-monitor, not a
# corpus crawler: we only need the most-recent submissions since the watermark.
_MAX_RESULTS = 25

# Atom 1.0 namespace (the export API returns Atom; ``{ns}tag`` is the ET idiom).
_ATOM_NS = "{http://www.w3.org/2005/Atom}"

# arXiv signals an error by returning an Atom feed whose single ``<entry>`` has an
# ``<id>`` under this URL prefix (e.g. malformed query). We detect it and return
# ``error`` rather than treating the error text as a "new paper".
_ARXIV_ERROR_ID_MARKER = "arxiv.org/api/errors"

# --------------------------------------------------------------------------- #
# Aggregate rate gate (process-global, >= 3s between ANY two arXiv requests)
# --------------------------------------------------------------------------- #

# arXiv asks for <= 1 request / 3 seconds IN AGGREGATE. This is a MODULE GLOBAL
# (shared across every source / every adapter instance in the process) precisely
# so that polling many arXiv sources in one batch cannot exceed the aggregate
# limit by sharding. ``None`` = no arXiv request has been issued yet.
_MIN_REQUEST_INTERVAL_S = 3.0
_last_request_monotonic: Optional[float] = None
_rate_gate_lock = Lock()


def _arxiv_rate_gate() -> None:
    """Block until ``>= 3.0s`` have elapsed since the last arXiv request.

    Process-global serialization of arXiv requests to honor the aggregate
    1-req/3s limit. Reads/advances the module-global ``_last_request_monotonic``
    under a lock; if the previous request was less than ``_MIN_REQUEST_INTERVAL_S``
    ago, sleeps exactly the remaining delta. The first request (no prior call)
    passes immediately. ``time.monotonic`` is used (not wall-clock) so the gate
    is immune to clock adjustments; both ``time.monotonic`` and ``time.sleep`` are
    referenced via the module ``time`` so a test can fake the clock without ever
    sleeping a real 3 seconds.

    The timestamp is stamped to ``now + slept`` (i.e. the moment this request is
    released) so back-to-back calls each wait the full interval from the previous
    RELEASE, not from a fixed origin.
    """
    global _last_request_monotonic
    with _rate_gate_lock:
        now = time.monotonic()
        if _last_request_monotonic is not None:
            elapsed = now - _last_request_monotonic
            remaining = _MIN_REQUEST_INTERVAL_S - elapsed
            if remaining > 0:
                time.sleep(remaining)
                now = now + remaining
        _last_request_monotonic = now


# --------------------------------------------------------------------------- #
# Query derivation from the source URL
# --------------------------------------------------------------------------- #


def _build_search_query(url: str) -> Optional[str]:
    """Derive an arXiv ``search_query`` from a stored ``arxiv.org`` source URL.

    Read-only, pure, no I/O. Maps the common arXiv URL shapes to a bounded
    query (NOT a full-corpus crawl):

    * ``arxiv.org/abs/<id>`` or ``arxiv.org/pdf/<id>`` -> ``id:<id>`` (watch a
      specific paper / its revisions).
    * ``arxiv.org/list/<category>/...`` (e.g. ``/list/cs.LG/recent``) ->
      ``cat:<category>`` (watch a subject category's newest submissions).
    * ``arxiv.org/a/<author>`` (an author page) -> ``au:<author>``.
    * a host that is literally the export API with a ``search_query`` already in
      the query string -> that stored query verbatim (operator-supplied).
    * anything else under ``arxiv.org`` with a usable first path segment ->
      ``all:<segment>`` as a best-effort free-text query.

    Returns ``None`` when no query can be derived (the caller then ``skips``).
    """
    parsed = urlparse(url or "")
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]

    # An operator may paste a fully-formed export-API URL; honor its search_query.
    if host == "export.arxiv.org":
        from urllib.parse import parse_qs

        stored = parse_qs(parsed.query or "").get("search_query")
        if stored and stored[0].strip():
            return stored[0].strip()
        return None

    if host != "arxiv.org":
        return None

    segments = [seg for seg in (parsed.path or "").split("/") if seg]
    if not segments:
        return None

    head = segments[0].lower()
    if head in ("abs", "pdf") and len(segments) >= 2:
        # /abs/2401.01234 (possibly with a vN suffix on /pdf) -> id:<id>
        paper_id = segments[1]
        if paper_id.lower().endswith(".pdf"):
            paper_id = paper_id[: -len(".pdf")]
        return f"id:{paper_id}"
    if head == "list" and len(segments) >= 2:
        # /list/cs.LG/recent -> cat:cs.LG
        return f"cat:{segments[1]}"
    if head == "a" and len(segments) >= 2:
        # /a/lecun_y_1 -> au:lecun_y_1 (author page)
        return f"au:{segments[1]}"

    # Best-effort free-text fallback on the first path segment.
    return f"all:{segments[0]}"


def _export_url(search_query: str) -> str:
    """Build the bounded, newest-first export-API URL for ``search_query``.

    ``sortBy=submittedDate&sortOrder=descending`` makes the feed newest-first so
    the watermark dedup is a simple ``published > cursor`` check; ``max_results``
    is bounded (``_MAX_RESULTS``) — a change-monitor window, not a crawl.
    """
    query = urlencode(
        {
            "search_query": search_query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": _MAX_RESULTS,
        }
    )
    return f"{_EXPORT_ENDPOINT}?{query}"


# --------------------------------------------------------------------------- #
# Atom parsing
# --------------------------------------------------------------------------- #


def _text(node: Optional[Element]) -> str:
    """Collapse an Atom text node to a stripped string (``""`` if absent)."""
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _parse_entries(body: str) -> Optional[list[dict]]:
    """Parse an Atom feed body into ``[{id, published, title, authors, summary}]``.

    Returns ``None`` to signal an ERROR document (the body is not a parseable
    Atom feed, OR it is arXiv's error feed — a single ``<entry>`` whose ``<id>``
    is under ``arxiv.org/api/errors``). Otherwise returns the list of result
    entries (possibly empty for a query that legitimately matched nothing).

    Never raises: a malformed body is caught and reported as ``None`` (-> the
    caller returns ``outcome='error'``).
    """
    try:
        root = ET.fromstring(body or "")
    except ET.ParseError:
        return None

    # Tolerate a missing namespace by matching on the local tag name too.
    if not root.tag.endswith("feed"):
        return None

    entries: list[dict] = []
    for entry in root.findall(f"{_ATOM_NS}entry"):
        entry_id = _text(entry.find(f"{_ATOM_NS}id"))
        # arXiv error feed: the entry id is an errors# URL -> treat as error.
        if _ARXIV_ERROR_ID_MARKER in entry_id:
            return None
        published = _text(entry.find(f"{_ATOM_NS}published"))
        title = _text(entry.find(f"{_ATOM_NS}title"))
        summary = _text(entry.find(f"{_ATOM_NS}summary"))
        authors = [_text(a.find(f"{_ATOM_NS}name")) for a in entry.findall(f"{_ATOM_NS}author")]
        authors = [a for a in authors if a]
        entries.append(
            {
                "id": entry_id,
                "published": published,
                "title": title,
                "summary": summary,
                "authors": authors,
            }
        )
    return entries


def _render_papers(new_entries: list[dict]) -> str:
    """Render new entries as the human-readable text block the summarizer reads.

    One ``"<title>\\n<authors>\\n<summary>"`` block per new paper, blocks joined
    by a blank line — the CONTENT (taint-wrapped by the summarizer), DISTINCT
    from the watermark cursor. Abstracts (``summary``) are passed through as-is;
    they are untrusted competitor text and the summarizer owns the taint-wrap.
    """
    blocks: list[str] = []
    for entry in new_entries:
        title = entry.get("title") or "(untitled paper)"
        authors = ", ".join(entry.get("authors") or [])
        summary = entry.get("summary") or ""
        blocks.append(f"{title}\n{authors}\n{summary}")
    return "\n\n".join(blocks)


class ArxivAdapter(AdapterBase):
    """Keyless read-only poller for ``arxiv`` competitor sources (export API).

    Derives a bounded ``search_query`` from the source URL, passes through the
    process-global ``>= 3s`` rate gate, GETs the newest-first Atom feed, and
    returns a ``FetchResult`` with the new-papers text block as ``raw_ref`` and
    ``max(published)`` as ``watermark``. Persistence (snapshot + cursor) is
    ``AdapterBase.commit``'s job; ``fetch`` never persists and never raises.
    """

    kind = KIND_ARXIV
    # No ETag/304 free path; arXiv asks for <= 1 poll/day/query. The 25-01 poll
    # floor enforces the daily cadence; the module gate enforces the 1-req/3s
    # aggregate limit on top.
    poll_interval_floor_s = 86400  # 24h (daily)

    def has_credential(self) -> bool:
        """Always ``True`` — the arXiv export API is a keyless public read.

        There is no credential to gate on (no token, no auth header is ever
        constructed), so the dispatcher never skips an arXiv source for a
        missing credential. The never-unauth rule does not apply: there is no
        auth to omit.
        """
        return True

    def fetch(self, source: dict) -> FetchResult:
        """One keyless read-only export-API GET of ``source``; map to ``FetchResult``.

        * un-derivable / non-arXiv URL -> ``outcome='skipped'`` (no HTTP call)
        * ``429`` / ``503`` -> ``outcome='throttled'`` (back off this kind)
        * transport error / other non-200 / unparseable-or-error XML ->
          ``outcome='error'`` (per-source skip)
        * ``200`` Atom feed with NO entry whose ``published`` > watermark ->
          ``outcome='unchanged'`` (no write)
        * ``200`` with new papers -> ``outcome='changed'`` with ``raw_ref`` (the
          new-papers text block the summarizer reads), ``watermark`` =
          ``max(published)`` across the returned entries, and ``etag=None`` (arXiv
          has no conditional-GET cursor).

        RATE DISCIPLINE: ``_arxiv_rate_gate()`` runs immediately before the HTTP
        call, serializing arXiv requests to ``>= 3s`` apart across the whole
        batch. NEVER raises for a bad payload — transport/parse failures are
        caught and returned as ``error``.
        """
        source_id = source.get("id")
        search_query = _build_search_query(source.get("url") or "")
        if not search_query:
            # Not a derivable arXiv query — nothing to poll.
            logger.warning("competitor source %s has no pollable arXiv query", source_id)
            return FetchResult(outcome="skipped")

        url = _export_url(search_query)

        # HARD aggregate rate limit: serialize EVERY arXiv request >= 3s apart,
        # process-wide, BEFORE issuing the call (sharding to evade is banned).
        _arxiv_rate_gate()

        try:
            # Read-only, UNAUTHENTICATED public GET — no Authorization header.
            resp = httpx.get(url, timeout=_POLL_TIMEOUT, follow_redirects=False)
        except httpx.HTTPError:
            # Transport error (DNS / timeout / connection) — per-source failure,
            # not a rate limit; skip this source, keep polling the rest.
            logger.warning("competitor arXiv HTTP error for source %s", source_id, exc_info=True)
            return FetchResult(outcome="error")

        status = resp.status_code

        # arXiv rate limit / unavailable -> back off this kind, write nothing.
        if status in (429, 503):
            logger.warning("competitor arXiv throttled (HTTP %d) for source %s", status, source_id)
            return FetchResult(outcome="throttled")

        if status != 200:
            logger.warning("competitor arXiv unexpected HTTP %d for source %s", status, source_id)
            return FetchResult(outcome="error")

        # Even errors are Atom XML; ``None`` = unparseable OR an arXiv error feed.
        entries = _parse_entries(resp.text)
        if entries is None:
            logger.warning("competitor arXiv unparseable/error feed for source %s", source_id)
            return FetchResult(outcome="error")

        # A query that legitimately matched nothing -> unchanged (no write).
        published_values = [e["published"] for e in entries if e.get("published")]
        if not published_values:
            return FetchResult(outcome="unchanged")

        # Incremental published-watermark dedup. The persisted cursor is
        # max(published), so an entry is new iff there is no watermark yet (first
        # poll -> take the current window) OR its published is strictly past the
        # cursor. The feed is newest-first; the cursor is the single monotonic
        # signal, matching AdapterBase's snapshot-cursor split.
        watermark = source.get("watermark")
        new_entries = [
            e
            for e in entries
            if e.get("published") and ((not watermark) or e["published"] > watermark)
        ]
        if not new_entries:
            return FetchResult(outcome="unchanged")

        # Monotonic cursor across ALL returned entries (not just the new set),
        # so a later poll that re-sees the same max doesn't re-fire.
        new_watermark = max(published_values)
        raw_ref = _render_papers(new_entries)
        return FetchResult(
            outcome="changed",
            raw_ref=raw_ref,
            watermark=new_watermark,
            etag=None,
        )


# Register on import (the package __init__ imports this module). Last-write-wins.
registry.register(ArxivAdapter())
