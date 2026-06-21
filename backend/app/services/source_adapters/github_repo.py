"""GitHubRepoAdapter — the ``github_repo`` source adapter (phase 25).

Wraps phase-23's ``GitHubMonitorService`` conditional-GET poll
(``github_monitor_service.py:178-263``) VERBATIM behind the ``SourceAdapter``
contract, so the ``github_repo`` path stays byte-for-byte identical to P1:

* It reuses P1's helpers unchanged — ``_auth_headers`` (the always-authenticated
  credential seam, :96-119), ``_api_url`` (releases/latest endpoint, :123-138),
  ``_extract_watermark`` (:265-279), ``_extract_content`` (:281-301) — and the
  same ``httpx`` conditional GET (``If-None-Match`` + ETag).
* It only changes the RETURN SHAPE: instead of P1's ad-hoc dict it returns a
  ``FetchResult``, and it does NOT persist — ``AdapterBase.commit`` (lifted from
  ``_persist_snapshot_and_cursor``) owns the snapshot+cursor write. The
  ``GITHUB_TOKEN``-or-skip guard becomes ``has_credential()``.

``poll_interval_floor_s = 0``: github's ETag/304 path is already exempt from the
primary rate limit (the free path), so there is no extra per-source floor — the
ETag IS the clock. A 403/429 still backs the whole ``github_repo`` kind off for
the tick (the dispatcher's per-kind throttle).
"""

from __future__ import annotations

import hashlib

import httpx

from app.services.competitor_source_service import KIND_GITHUB_REPO
from app.services.github_monitor_service import (
    _POLL_TIMEOUT,
    GitHubMonitorService,
    logger,
)
from app.services.source_adapters import registry
from app.services.source_adapters.base import AdapterBase, FetchResult


class GitHubRepoAdapter(AdapterBase):
    """Conditional-GET poller for ``github_repo`` competitor sources.

    Behavior-identical to phase-23 ``GitHubMonitorService.poll_source`` — it
    reuses P1's helpers and the same ``httpx`` call, returning a ``FetchResult``
    and deferring persistence to ``AdapterBase.commit``.
    """

    kind = KIND_GITHUB_REPO
    poll_interval_floor_s = 0  # ETag/304 is already the free path — no extra floor.

    def has_credential(self) -> bool:
        """True when a ``GITHUB_TOKEN`` PAT is configured.

        Reuses P1's ``_auth_headers`` None-means-no-credential guard
        (``github_monitor_service.py:96-119``) — the single credential seam — so
        the never-unauth rule is honored: no token -> dispatcher skips the fetch.
        """
        return GitHubMonitorService._auth_headers() is not None

    def fetch(self, source: dict) -> FetchResult:
        """One conditional GET of ``source``; map P1's outcomes to ``FetchResult``.

        Wraps ``GitHubMonitorService.poll_source`` (:178-263) VERBATIM (same
        ``_api_url`` / ``_auth_headers`` / ``If-None-Match`` / ``_extract_*``),
        translating the status outcomes:

        * no credential / unpollable URL -> ``outcome='skipped'``
        * ``304`` -> ``outcome='unchanged'`` (the free path; no write)
        * ``403`` / ``429`` -> ``outcome='throttled'`` (back off this kind)
        * transport error / other non-200 -> ``outcome='error'`` (per-source skip)
        * ``200`` -> ``outcome='changed'`` with ``raw_ref`` (=``_extract_content``,
          the content the summarizer reads), ``watermark`` (=``_extract_watermark``),
          ``etag`` (response ETag, falling back to the stored one), and the
          ``sha256`` body hash — exactly P1's 200 path, minus the persistence
          (``commit`` does that).
        """
        source_id = source.get("id")
        headers = GitHubMonitorService._auth_headers()
        if headers is None:
            # Never the 60/hr unauth path; the dispatcher already skips on
            # has_credential() False, so this is belt-and-suspenders.
            return FetchResult(outcome="skipped")

        url = GitHubMonitorService._api_url(source)
        if not url:
            logger.warning("competitor source %s has no pollable GitHub URL", source_id)
            return FetchResult(outcome="skipped")

        # Conditional GET: only re-send the body if the stored ETag no longer matches.
        etag = source.get("etag")
        if etag:
            headers["If-None-Match"] = etag

        try:
            resp = httpx.get(url, headers=headers, timeout=_POLL_TIMEOUT, follow_redirects=False)
        except httpx.HTTPError:
            # Transport error (DNS / timeout / connection) is a PER-SOURCE failure,
            # not a rate limit — skip this source, keep polling the rest.
            logger.warning("competitor poll HTTP error for source %s", source_id, exc_info=True)
            return FetchResult(outcome="error")

        status = resp.status_code

        # 304: the free path. ETag still valid -> nothing changed, no writes.
        if status == 304:
            return FetchResult(outcome="unchanged")

        # Secondary / abuse rate limit -> back off this kind, write nothing.
        if status in (403, 429):
            logger.warning("competitor poll throttled (HTTP %d) for source %s", status, source_id)
            return FetchResult(outcome="throttled")

        if status != 200:
            logger.warning("competitor poll unexpected HTTP %d for source %s", status, source_id)
            return FetchResult(outcome="error")

        # 200: a real change. Hash the normalized body, extract content + cursor.
        content_hash = hashlib.sha256(resp.content or b"").hexdigest()
        # Preserve the prior ETag when a 200 omits the header, so conditional GETs
        # keep working instead of being permanently disabled for this source.
        new_etag = resp.headers.get("ETag") or source.get("etag")
        watermark = GitHubMonitorService._extract_watermark(resp)
        raw_ref = GitHubMonitorService._extract_content(resp)
        return FetchResult(
            outcome="changed",
            raw_ref=raw_ref,
            watermark=watermark,
            etag=new_etag,
            content_hash=content_hash,
        )


# Register on import (the package __init__ imports this module). Last-write-wins.
registry.register(GitHubRepoAdapter())
