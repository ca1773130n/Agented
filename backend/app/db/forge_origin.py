"""Provenance for session-auto-imported forge primitives (migration 157).

Why this exists: the session-completion auto-import handler
(``app.services.forge_session_import``) imports primitives that an
Agented-driven session scaffolded under ``.claude/``. Each import records the
sha256 content-hash of the source file plus the session that produced it, so
that:

- a re-run with an unchanged file is a no-op (hash matches → skip);
- a changed file can be re-imported (hash differs);
- an operator can audit where an auto-bound primitive came from.

Keyed on (asset_id, kind). ``asset_id`` is the import handler's stable key for
the asset — for session-imported sub-agents that is the sub-agent NAME (the
identity carried by the source file), not the generated ``subag-`` row id.
"""

from __future__ import annotations

from typing import Optional

from app.utils.timezone import utc_now_iso

from .connection import get_connection


def record_origin(
    asset_id: str,
    kind: str,
    origin_hash: str,
    source_session_id: Optional[str] = None,
) -> None:
    """Upsert the provenance row for (asset_id, kind). On a changed import the
    hash + session + timestamp are refreshed."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO forge_origin
                (asset_id, kind, origin_hash, source_session_id, imported_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(asset_id, kind) DO UPDATE SET
                origin_hash = excluded.origin_hash,
                source_session_id = excluded.source_session_id,
                imported_at = excluded.imported_at
            """,
            (asset_id, kind, origin_hash, source_session_id, utc_now_iso()),
        )
        conn.commit()


def get_origin(asset_id: str, kind: str) -> Optional[dict]:
    """Return the provenance row for (asset_id, kind), or None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM forge_origin WHERE asset_id = ? AND kind = ?",
            (asset_id, kind),
        ).fetchone()
        return dict(row) if row else None
