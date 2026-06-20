"""CompetitorSourceService — add/list/get competitor sources (REQ-27).

The Wave-1 root of phase 23's competitive-intelligence MVP. A *source* is a
single URL the operator wants watched (a competitor's GitHub repo, an arXiv
listing, or a product page). This service is deliberately thin: it mints a
``cmps-`` id, auto-detects the source ``kind`` from the URL host, and inserts
a ``competitor_source`` row. Polling/fetching/summarizing live in later plans
(23-02 monitor, 23-03 summarizer) and key off these rows.

Persistence is raw SQLite via ``app.database.get_connection`` (repo convention
— no ORM). Optional fields (``label``, ``etag``, ``watermark``) are
NULL-accepting and never block an insert: an empty/missing ``label`` is the
account-name-style rule from REQ-27 and the wizard-defaults feedback.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse

from app.database import get_connection
from app.db.ids import generate_id

# Source kinds, derived from the URL host. The poller/summarizer branch on these.
KIND_GITHUB_REPO = "github_repo"
KIND_ARXIV = "arxiv"
KIND_PRODUCT_URL = "product_url"

# Columns selected/returned, in declaration order (see migration 171).
_SOURCE_COLUMNS = (
    "id",
    "project_id",
    "kind",
    "url",
    "origin",
    "etag",
    "watermark",
    "status",
    "label",
    "created_at",
)


class CompetitorSourceService:
    """Add and read competitor sources for a project (REQ-27)."""

    @staticmethod
    def detect_kind(url: str) -> str:
        """Map a URL to its source ``kind`` from the host.

        ``github.com`` (or ``www.github.com``) -> ``github_repo``;
        ``arxiv.org`` (or ``www.arxiv.org``) -> ``arxiv``; everything else
        (including blank/garbage input) -> ``product_url``. Pure function —
        no I/O, trivially unit-testable.
        """
        host = (urlparse(url or "").hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        if host == "github.com":
            return KIND_GITHUB_REPO
        if host == "arxiv.org":
            return KIND_ARXIV
        return KIND_PRODUCT_URL

    @staticmethod
    def add_source(
        project_id: str,
        url: str,
        label: Optional[str] = None,
        origin: str = "manual",
    ) -> dict:
        """Insert a competitor source and return the persisted row.

        ``kind`` is auto-detected from ``url``. ``etag``/``watermark`` start
        NULL (the poller fills them later) and ``status`` defaults to
        ``'active'``. ``label`` is OPTIONAL and is normalized: an empty or
        whitespace-only string is stored as NULL. Never raises on a
        missing/blank ``label`` (REQ-27 / wizard-defaults rule).
        """
        kind = CompetitorSourceService.detect_kind(url)
        normalized_label = label.strip() if isinstance(label, str) else None
        if not normalized_label:
            normalized_label = None
        source_id = generate_id("cmps-", 6)
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO competitor_source
                    (id, project_id, kind, url, origin, status, label)
                VALUES (?, ?, ?, ?, ?, 'active', ?)
                """,
                (source_id, project_id, kind, url, origin, normalized_label),
            )
            conn.commit()
            row = conn.execute(
                f"SELECT {', '.join(_SOURCE_COLUMNS)} FROM competitor_source WHERE id = ?",
                (source_id,),
            ).fetchone()
        return dict(row)

    @staticmethod
    def list_sources(project_id: str) -> list[dict]:
        """Return all sources for ``project_id``, newest first."""
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT {', '.join(_SOURCE_COLUMNS)} FROM competitor_source "
                "WHERE project_id = ? ORDER BY created_at DESC, id DESC",
                (project_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def get_source(source_id: str) -> Optional[dict]:
        """Return a single source by id, or ``None`` if it does not exist."""
        with get_connection() as conn:
            row = conn.execute(
                f"SELECT {', '.join(_SOURCE_COLUMNS)} FROM competitor_source WHERE id = ?",
                (source_id,),
            ).fetchone()
        return dict(row) if row is not None else None
