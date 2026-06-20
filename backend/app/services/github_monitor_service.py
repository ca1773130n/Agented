"""GitHubMonitorService — authenticated conditional polling of competitor repos (REQ-28).

Wave-2 of phase 23's competitive-intelligence MVP. Turns a stored
``competitor_source`` (kind ``github_repo``) into a stream of point-in-time
``competitor_snapshot`` rows *cheaply*: every poll is an **authenticated**
conditional GET that sends the source's stored ``ETag`` via ``If-None-Match``.

Why conditional GET (research §4.1):
  * GitHub returns ``304 Not Modified`` when the ETag still matches. A 304 is
    **exempt from the primary rate limit** — it is the free path. We write
    nothing on a 304 (no snapshot, no row rewrite).
  * Only a ``200 OK`` (the resource actually changed) costs rate budget; only
    then do we hash the body, write ONE snapshot, and persist the fresh ETag +
    watermark back onto the source row.

Why always authenticated (research §4.1):
  * The unauthenticated GitHub REST limit is 60 req/hr — unusable for polling.
    A PAT lifts it to 5,000 req/hr. We therefore ALWAYS attach an
    ``Authorization`` header when a token is configured; if none is configured
    we **log a warning and skip** the source rather than fall through to the
    60/hr unauth path.

GitHub-App upgrade path:
  ``_auth_headers`` is the single seam where the credential is built. The MVP
  reads a PAT from ``GITHUB_TOKEN``; a multi-tenant GitHub-App *installation
  token* can be swapped in there later without touching the poll logic. App
  support is out of scope for P1 — noted only.

Persistence is raw SQLite via ``app.database.get_connection`` (repo convention,
no ORM). HTTP uses ``httpx`` (the codebase's standard outbound client, e.g.
``app/services/github_service.py``) — no new dependency.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Optional

import httpx

from app.database import get_connection
from app.db.ids import generate_id
from app.services.competitor_source_service import KIND_GITHUB_REPO

logger = logging.getLogger(__name__)

# Env var holding the GitHub Personal Access Token (the MVP credential). Same
# name `gh` + the rest of the backend already use (see scripts/check_env.py).
GITHUB_PAT_ENV = "GITHUB_TOKEN"

# GitHub recommends pinning a REST API version; this also stabilises ETags.
_GH_API_VERSION = "2022-11-28"
_GH_ACCEPT = "application/vnd.github+json"

# Settings-table key (JSON blob) holding the competitor-intel poll config.
# Mirrors `monitoring_config` (app/db/monitoring.py). Default DISABLED.
COMPETITOR_INTEL_CONFIG_KEY = "competitor_intel_config"
_DEFAULT_POLL_MINUTES = 15
_DEFAULT_CONFIG = {"enabled": False, "polling_minutes": _DEFAULT_POLL_MINUTES}

# HTTP timeout for a single poll (seconds). Short — a poll is a cheap GET.
_POLL_TIMEOUT = 15


def get_competitor_intel_config() -> dict:
    """Read the competitor-intel poll config from the settings table.

    Returns the parsed JSON blob or a DISABLED default. Mirrors
    ``app.db.monitoring.get_monitoring_config`` so the lifecycle scheduler reads
    it the same way it reads the monitoring daemon's config.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (COMPETITOR_INTEL_CONFIG_KEY,),
        )
        row = cursor.fetchone()
        if row and row["value"]:
            try:
                parsed = json.loads(row["value"])
                if isinstance(parsed, dict):
                    return {**_DEFAULT_CONFIG, **parsed}
            except (json.JSONDecodeError, TypeError):
                pass
    return dict(_DEFAULT_CONFIG)


class GitHubMonitorService:
    """Authenticated conditional poller for ``github_repo`` competitor sources."""

    # -- credential seam -------------------------------------------------

    @staticmethod
    def _auth_headers() -> Optional[dict]:
        """Build the request headers, ALWAYS authenticated.

        Returns the header dict including ``Authorization`` when a PAT is
        configured, or ``None`` when no credential is available (the caller then
        skips the poll rather than issuing an unauthenticated 60/hr request).

        UPGRADE PATH (GitHub App): this is the single place the credential is
        constructed. To go multi-tenant, mint a per-installation token here
        (``token <installation_token>``) instead of reading the PAT env var; the
        poll logic below is credential-agnostic and needs no change.
        """
        pat = (os.environ.get(GITHUB_PAT_ENV) or "").strip()
        if not pat:
            return None
        return {
            # GitHub accepts both "Bearer <tok>" and "token <tok>"; "Bearer" is
            # the form an installation token will also use, so the seam stays
            # identical when an App token swaps in later.
            "Authorization": f"Bearer {pat}",
            "Accept": _GH_ACCEPT,
            "X-GitHub-Api-Version": _GH_API_VERSION,
        }

    # -- url derivation --------------------------------------------------

    @staticmethod
    def _api_url(source: dict) -> Optional[str]:
        """Derive the GitHub REST endpoint to poll from a source's repo URL.

        Starts with the repo's ``releases/latest`` endpoint — a single
        well-defined resource that ETags cleanly and is the highest-signal
        change for a competitor (a new release). Returns ``None`` if the URL is
        not a parseable ``owner/repo`` on github.com.
        """
        from app.services.github_service import GitHubService

        try:
            owner, repo = GitHubService.parse_repo_url(source["url"])
        except (ValueError, KeyError, TypeError):
            return None
        return f"https://api.github.com/repos/{owner}/{repo}/releases/latest"

    # -- persistence helpers --------------------------------------------

    @staticmethod
    def _persist_snapshot_and_cursor(
        source_id: str,
        content_hash: str,
        etag: Optional[str],
        watermark: Optional[str],
        raw_ref: Optional[str],
    ) -> str:
        """Write ONE snapshot and advance the source cursor (etag + watermark).

        Single transaction: insert the ``competitor_snapshot`` row (``raw_ref`` =
        the human-readable release content the summarizer reads), then update the
        parent ``competitor_source``'s ``etag``/``watermark`` (the monotonic poll
        cursor). ``raw_ref`` and ``watermark`` are DISTINCT — the snapshot stores
        the CONTENT to summarize, the source stores the timestamp cursor. Returns
        the new snapshot id.
        """
        snapshot_id = generate_id("cmsn-", 6)
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO competitor_snapshot
                    (id, source_id, fetched_at, content_hash, raw_ref)
                VALUES (?, ?, CURRENT_TIMESTAMP, ?, ?)
                """,
                (snapshot_id, source_id, content_hash, raw_ref),
            )
            conn.execute(
                "UPDATE competitor_source SET etag = ?, watermark = ? WHERE id = ?",
                (etag, watermark, source_id),
            )
            conn.commit()
        return snapshot_id

    # -- the poll --------------------------------------------------------

    @staticmethod
    def poll_source(source: dict) -> dict:
        """Conditionally poll one source; snapshot only on a real change.

        Sends ``If-None-Match`` with the stored ETag (when present) on an
        always-authenticated request:

        * **No credential** -> log a warning and skip (never unauth). Returns
          ``{"changed": False, "skipped": True}``.
        * **304 Not Modified** -> the free path. Writes nothing. Returns
          ``{"changed": False}``.
        * **200 OK** -> hash the normalized body, write ONE snapshot, persist the
          response ETag + new watermark on the source. Returns
          ``{"changed": True, "snapshot_id": ..., "content_hash": ...}``.
        * **403 / 429** (secondary / abuse rate limit) -> back off; writes
          nothing. Returns ``{"changed": False, "throttled": True}``.

        ``source`` is a row dict (see ``CompetitorSourceService``); only ``id``,
        ``url`` and ``etag`` are consulted.
        """
        source_id = source.get("id")
        headers = GitHubMonitorService._auth_headers()
        if headers is None:
            logger.warning(
                "GITHUB_TOKEN unset — skipping competitor source %s "
                "(refusing the 60/hr unauthenticated path)",
                source_id,
            )
            return {"changed": False, "skipped": True}

        url = GitHubMonitorService._api_url(source)
        if not url:
            logger.warning("competitor source %s has no pollable GitHub URL", source_id)
            return {"changed": False, "skipped": True}

        # Conditional GET: only re-send the body if the ETag no longer matches.
        etag = source.get("etag")
        if etag:
            headers["If-None-Match"] = etag

        try:
            resp = httpx.get(
                url,
                headers=headers,
                timeout=_POLL_TIMEOUT,
                follow_redirects=False,
            )
        except httpx.HTTPError:
            logger.warning("competitor poll HTTP error for source %s", source_id, exc_info=True)
            return {"changed": False, "throttled": True}

        status = resp.status_code

        # 304: the free path. ETag still valid -> nothing changed, no writes.
        if status == 304:
            return {"changed": False}

        # Secondary / abuse rate limit -> back off, write nothing.
        if status in (403, 429):
            logger.warning("competitor poll throttled (HTTP %d) for source %s", status, source_id)
            return {"changed": False, "throttled": True}

        if status != 200:
            logger.warning("competitor poll unexpected HTTP %d for source %s", status, source_id)
            return {"changed": False}

        # 200: a real change. Hash the normalized body, snapshot, advance cursor.
        content_hash = hashlib.sha256(resp.content or b"").hexdigest()
        new_etag = resp.headers.get("ETag")
        watermark = GitHubMonitorService._extract_watermark(resp)
        raw_ref = GitHubMonitorService._extract_content(resp)
        snapshot_id = GitHubMonitorService._persist_snapshot_and_cursor(
            source_id, content_hash, new_etag, watermark, raw_ref
        )
        logger.info(
            "competitor source %s changed -> snapshot %s (hash %s)",
            source_id,
            snapshot_id,
            content_hash[:12],
        )
        return {"changed": True, "snapshot_id": snapshot_id, "content_hash": content_hash}

    @staticmethod
    def _extract_watermark(resp: httpx.Response) -> Optional[str]:
        """Best-effort high-watermark from a releases/latest 200 body.

        Uses the release's ``published_at`` (monotonic per repo) when present,
        falling back to the tag name, then ``None``. Never raises — a missing or
        non-JSON body just yields ``None``.
        """
        try:
            body = resp.json()
        except (json.JSONDecodeError, ValueError):
            return None
        if isinstance(body, dict):
            return body.get("published_at") or body.get("tag_name")
        return None

    @staticmethod
    def _extract_content(resp: httpx.Response) -> Optional[str]:
        """Human-readable release content for the snapshot's ``raw_ref`` — what
        ``SignalSummarizerService`` reads and summarizes. Combines the release
        name/tag with the markdown ``body`` (the actual release notes). Never
        raises — a missing / non-JSON body yields ``None``.

        DISTINCT from ``_extract_watermark`` (the timestamp cursor): a snapshot
        must persist the CONTENT to summarize, not the ``published_at`` — else the
        summarizer summarizes a bare date (caught in live dogfood).
        """
        try:
            body = resp.json()
        except (json.JSONDecodeError, ValueError):
            return None
        if not isinstance(body, dict):
            return None
        header = (body.get("name") or body.get("tag_name") or "").strip()
        notes = (body.get("body") or "").strip()
        combined = "\n\n".join(part for part in (header, notes) if part).strip()
        return combined or None

    @staticmethod
    def poll_due_sources() -> int:
        """Poll every active ``github_repo`` source; return the number changed.

        The scheduler entrypoint (wired into ``lifecycle._setup_scheduler``).
        Iterates all active ``github_repo`` ``competitor_source`` rows across
        projects, polls each, and returns the count that produced a snapshot.
        Per-source failures are isolated so one bad repo can't stall the rest.
        """
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, url, etag FROM competitor_source WHERE kind = ? AND status = 'active'",
                (KIND_GITHUB_REPO,),
            ).fetchall()
        sources = [dict(r) for r in rows]

        changed = 0
        for src in sources:
            try:
                result = GitHubMonitorService.poll_source(src)
            except Exception:  # noqa: BLE001 — isolate one bad source
                logger.warning("competitor poll raised for source %s", src.get("id"), exc_info=True)
                continue
            if result.get("changed"):
                changed += 1
        return changed
