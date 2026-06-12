"""Provenance for session-auto-imported forge primitives (migration 157).

Why this exists: the session-completion auto-import handler
(``app.services.forge_session_import``) imports primitives that an
Agented-driven session scaffolded under ``.claude/``. Each import records the
sha256 content-hash of the source file plus the session that produced it, so
that:

- a re-run with an unchanged file is a no-op (hash matches → skip);
- a changed file can be re-imported (hash differs);
- an operator can audit where an auto-bound primitive came from.

Keyed on (asset_id, kind) — the same (id, kind) identity the rest of the forge
layer uses.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .connection import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
            (str(asset_id), kind, origin_hash, source_session_id, _now()),
        )
        conn.commit()


def get_origin(asset_id: str, kind: str) -> Optional[dict]:
    """Return the provenance row for (asset_id, kind), or None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM forge_origin WHERE asset_id = ? AND kind = ?",
            (str(asset_id), kind),
        ).fetchone()
        return dict(row) if row else None


def get_origin_by_hash(origin_hash: str) -> Optional[dict]:
    """Return any provenance row matching this content-hash, or None. Lets the
    import handler skip a file whose bytes were already imported (even under a
    different asset id)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM forge_origin WHERE origin_hash = ? LIMIT 1",
            (origin_hash,),
        ).fetchone()
        return dict(row) if row else None
