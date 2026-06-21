"""JobBoardAdapter — the ``job_board`` source adapter (phase 25, plan 02).

"Hiring-as-roadmap": a public job posting is an unannounced product bet, often
weeks ahead of a release. This adapter turns an operator-pasted Greenhouse or
Lever board URL into normalized ``competitor_snapshot`` rows that the EXISTING
``SignalSummarizerService`` (unchanged) converts to ``detected_signal`` rows.
No new pipeline, no new LLM path, no UI change — only a new fetcher behind the
25-01 ``SourceAdapter`` seam.

Both providers are **keyless, read-only GETs** (research §5B [42][43]):

* Greenhouse — ``GET https://boards-api.greenhouse.io/v1/boards/<token>/jobs?content=true``
* Lever      — ``GET https://api.lever.co/v0/postings/<company>?mode=json``

The ``<token>`` (Greenhouse board token) / ``<company>`` (Lever company slug) is
a **PUBLIC identifier parsed from the source URL path** — it names a public
board, it is NOT a credential. It is used ONLY as a path segment and is NEVER
sent as auth (no ``Authorization`` header is ever constructed). ``has_credential``
is therefore always ``True`` (a keyless read needs no credential), and the
never-unauth guard does not apply: there is no auth to omit.

Incremental dedup (research §5B): each posting has a stable ``id`` + ``updated_at``.
A posting is *new or changed* iff its ``id`` is unseen OR its ``updated_at`` is
strictly greater than the stored ``watermark``. The watermark is ``max(updated_at)``
across ALL returned postings (a monotonic cursor); the first poll (watermark NULL)
takes every current posting. ``raw_ref`` is a SHORT human-readable text block of
the diff set — ``"<title> (<department>, <location>)"`` per new/changed posting —
DISTINCT from the watermark cursor; it flows unchanged through the summarizer's
taint-wrap (every fetched posting string is prompt-injection-tainted, OWASP LLM01).

``poll_interval_floor_s = 21600`` (6h): unlike github there is no ETag/304 free
path, so the 25-01 per-kind poll floor is what throttles this kind (the dispatcher
enforces ``now - last_polled_at >= floor_s``). ``403``/``429`` -> ``throttled``;
a transport/parse failure -> ``error``; an empty/unparseable board -> ``skipped``.
This method NEVER raises for a bad payload — per-source isolation is the
dispatcher's job, but the adapter is the first line.

Persistence is owned by ``AdapterBase.commit`` (sha256 + dedup + cursor write);
``fetch`` is a pure read. HTTP uses ``httpx`` — the codebase's standard outbound
client (matching ``github_monitor_service``) — no new dependency.
"""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlparse

import httpx

from app.services.competitor_source_service import KIND_JOB_BOARD
from app.services.source_adapters import registry
from app.services.source_adapters.base import AdapterBase, FetchResult

logger = logging.getLogger(__name__)

# HTTP timeout for one board poll (seconds). Short — a poll is a cheap GET.
_POLL_TIMEOUT = 15

# Provider tags (internal — which URL template + payload shape to use).
_PROVIDER_GREENHOUSE = "greenhouse"
_PROVIDER_LEVER = "lever"

# Host -> provider. ``www.``-stripped before lookup. The slug after the host is
# the PUBLIC board token / company slug (parsed from the path, never auth).
_GREENHOUSE_HOSTS = frozenset(
    {"boards.greenhouse.io", "job-boards.greenhouse.io", "api.greenhouse.io"}
)
_LEVER_HOSTS = frozenset({"jobs.lever.co", "api.lever.co"})


def _provider_and_slug(url: str) -> tuple[Optional[str], Optional[str]]:
    """Parse ``(provider, public_slug)`` from a board URL, or ``(None, None)``.

    The provider is keyed off the host; the slug is the FIRST path segment
    (Greenhouse board token / Lever company slug) — a PUBLIC identifier, used
    only as a path segment downstream and NEVER as auth. A blank/garbage URL,
    an unknown host, or a missing path segment yields ``(None, None)`` so the
    caller returns ``skipped`` rather than raising.
    """
    parsed = urlparse(url or "")
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]

    if host in _GREENHOUSE_HOSTS:
        provider = _PROVIDER_GREENHOUSE
    elif host in _LEVER_HOSTS:
        provider = _PROVIDER_LEVER
    else:
        return None, None

    # First non-empty path segment is the public board token / company slug.
    segments = [seg for seg in (parsed.path or "").split("/") if seg]
    if not segments:
        return None, None
    return provider, segments[0]


def _endpoint(provider: str, slug: str) -> str:
    """Build the keyless read-only API URL for ``provider`` + ``slug``.

    The slug is interpolated ONLY into the path — it names a public board, it is
    not a credential and is never placed in a header.
    """
    if provider == _PROVIDER_GREENHOUSE:
        return f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    return f"https://api.lever.co/v0/postings/{slug}?mode=json"


def _normalize_postings(provider: str, payload: object) -> list[dict]:
    """Normalize a provider payload to ``[{id, updated_at, title, department, location}]``.

    Greenhouse: ``{"jobs": [{"id", "updated_at", "title", "departments":[{"name"}],
    "location":{"name"}}]}``. Lever: a top-level ``[{"id", "updatedAt",
    "text", "categories":{"team","location"}}]``. Both id/updated_at are coerced
    to ``str`` (ids may be ints; Lever ``updatedAt`` is an epoch-ms int) so the
    watermark comparison is string-stable and the cursor persists as TEXT. A
    posting with no usable id is dropped (it can't be deduped). Never raises on a
    missing field — a malformed shape yields ``[]`` and the caller skips.
    """
    if provider == _PROVIDER_GREENHOUSE:
        raw = payload.get("jobs", []) if isinstance(payload, dict) else []
    else:
        # Lever returns a bare top-level list.
        raw = payload if isinstance(payload, list) else []

    postings: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        if provider == _PROVIDER_GREENHOUSE:
            pid = item.get("id")
            updated_at = item.get("updated_at")
            title = item.get("title") or ""
            departments = item.get("departments") or []
            department = ""
            if isinstance(departments, list) and departments:
                first = departments[0]
                if isinstance(first, dict):
                    department = first.get("name") or ""
            location_obj = item.get("location") or {}
            location = location_obj.get("name") or "" if isinstance(location_obj, dict) else ""
        else:
            pid = item.get("id")
            updated_at = item.get("updatedAt")
            title = item.get("text") or ""
            categories = item.get("categories") or {}
            department = ""
            location = ""
            if isinstance(categories, dict):
                department = categories.get("team") or ""
                location = categories.get("location") or ""

        if pid is None:
            continue
        postings.append(
            {
                "id": str(pid),
                # ``updated_at`` may be absent (rare); empty string sorts below any
                # real cursor so such a posting is treated as not-newer (its
                # unseen id still makes it new on first encounter).
                "updated_at": "" if updated_at is None else str(updated_at),
                "title": str(title),
                "department": str(department),
                "location": str(location),
            }
        )
    return postings


def _render_diff(new_or_changed: list[dict]) -> str:
    """Render the diff set as a short human-readable text block.

    ``"New roles: <title> (<department>, <location>); ..."`` — the CONTENT the
    summarizer reads (and taint-wraps), DISTINCT from the watermark cursor.
    Department/location are best-effort; an empty one is omitted from the parens
    so the line stays readable.
    """
    parts: list[str] = []
    for posting in new_or_changed:
        title = posting.get("title") or "(untitled role)"
        meta = [posting.get("department") or "", posting.get("location") or ""]
        meta = [m for m in meta if m]
        if meta:
            parts.append(f"{title} ({', '.join(meta)})")
        else:
            parts.append(title)
    return "New roles: " + "; ".join(parts)


class JobBoardAdapter(AdapterBase):
    """Keyless read-only poller for ``job_board`` (Greenhouse + Lever) sources.

    Parses the PUBLIC board token / company slug from the source URL path (never
    as auth), GETs the unauthenticated postings endpoint, and returns a
    ``FetchResult`` with the new/changed-postings diff as ``raw_ref`` and
    ``max(updated_at)`` as ``watermark``. Persistence (snapshot + cursor) is
    ``AdapterBase.commit``'s job.
    """

    kind = KIND_JOB_BOARD
    # No ETag/304 free path here, so the per-kind poll floor is the only throttle.
    poll_interval_floor_s = 21600  # 6h

    def has_credential(self) -> bool:
        """Always ``True`` — Greenhouse + Lever board reads are keyless.

        There is no credential to gate on (the board token / company slug is a
        public path identifier, not auth), so the dispatcher never skips a
        job_board source for a missing credential.
        """
        return True

    def fetch(self, source: dict) -> FetchResult:
        """One keyless read-only GET of ``source``; map outcomes to ``FetchResult``.

        * unparseable / unknown / empty board URL -> ``outcome='skipped'``
        * ``403`` / ``429`` -> ``outcome='throttled'`` (back off this kind)
        * transport error / non-200 / malformed JSON -> ``outcome='error'``
        * ``200`` with NO posting whose id is unseen or whose ``updated_at`` >
          watermark -> ``outcome='unchanged'`` (no write)
        * ``200`` with new/changed postings -> ``outcome='changed'`` with
          ``raw_ref`` (the diff-set text block the summarizer reads),
          ``watermark`` = ``max(updated_at)`` across ALL returned postings, and
          ``etag=None`` (job boards have no conditional-GET cursor).

        NEVER raises for a bad payload — a transport/parse failure is caught and
        returned as ``error``.
        """
        source_id = source.get("id")
        provider, slug = _provider_and_slug(source.get("url") or "")
        if provider is None or not slug:
            # Not a parseable Greenhouse/Lever board — nothing to poll.
            logger.warning("competitor source %s has no pollable job-board URL", source_id)
            return FetchResult(outcome="skipped")

        url = _endpoint(provider, slug)
        try:
            # Read-only, UNAUTHENTICATED: the slug is the public board id in the
            # path; no Authorization header is built — the board is public.
            resp = httpx.get(url, timeout=_POLL_TIMEOUT, follow_redirects=False)
        except httpx.HTTPError:
            # Transport error (DNS / timeout / connection) — per-source failure,
            # not a rate limit; skip this source, keep polling the rest.
            logger.warning(
                "competitor job-board HTTP error for source %s", source_id, exc_info=True
            )
            return FetchResult(outcome="error")

        status = resp.status_code

        # Provider rate limit / forbidden -> back off this kind, write nothing.
        if status in (403, 429):
            logger.warning(
                "competitor job-board throttled (HTTP %d) for source %s", status, source_id
            )
            return FetchResult(outcome="throttled")

        if status != 200:
            logger.warning(
                "competitor job-board unexpected HTTP %d for source %s", status, source_id
            )
            return FetchResult(outcome="error")

        try:
            payload = resp.json()
        except (ValueError, TypeError):
            # Malformed JSON body — a per-source error, never a raise.
            logger.warning("competitor job-board malformed JSON for source %s", source_id)
            return FetchResult(outcome="error")

        postings = _normalize_postings(provider, payload)
        if not postings:
            # Empty or garbage board (no usable postings) — skip, not an error.
            return FetchResult(outcome="skipped")

        # Incremental id+updated_at dedup. The persisted cursor is max(updated_at),
        # so a posting is new/changed iff there is no watermark yet (first poll ->
        # take ALL current postings) OR its updated_at is strictly past the cursor.
        # A brand-new posting (unseen id) always carries the latest updated_at, so
        # the watermark comparison captures the unseen-id case too — the cursor is
        # the single monotonic signal, matching AdapterBase's snapshot-cursor split.
        watermark = source.get("watermark")
        new_or_changed = [p for p in postings if (not watermark) or p["updated_at"] > watermark]
        if not new_or_changed:
            return FetchResult(outcome="unchanged")

        # Monotonic cursor across ALL returned postings (not just the changed set),
        # so a later poll that re-sees the same max doesn't re-fire.
        new_watermark = max(p["updated_at"] for p in postings)
        raw_ref = _render_diff(new_or_changed)
        return FetchResult(
            outcome="changed",
            raw_ref=raw_ref,
            watermark=new_watermark,
            etag=None,
        )


# Register on import (the package __init__ imports this module). Last-write-wins.
registry.register(JobBoardAdapter())
