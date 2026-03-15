"""Database functions for repository scope filters."""

from typing import Optional

from .connection import get_connection
from .ids import generate_id

FILTER_ID_PREFIX = "sf-"
FILTER_ID_LENGTH = 6

PATTERN_ID_PREFIX = "spat-"
PATTERN_ID_LENGTH = 6


def _gen_filter_id(conn) -> str:
    while True:
        fid = generate_id(FILTER_ID_PREFIX, FILTER_ID_LENGTH)
        cur = conn.execute("SELECT id FROM scope_filters WHERE id = ?", (fid,))
        if cur.fetchone() is None:
            return fid


def _gen_pattern_id(conn) -> str:
    while True:
        pid = generate_id(PATTERN_ID_PREFIX, PATTERN_ID_LENGTH)
        cur = conn.execute("SELECT id FROM scope_filter_patterns WHERE id = ?", (pid,))
        if cur.fetchone() is None:
            return pid


def list_scope_filters() -> list[dict]:
    """Return all scope filters joined with their trigger name."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT sf.id, sf.trigger_id, sf.mode, sf.enabled, sf.updated_at,
                   t.name AS trigger_name
            FROM scope_filters sf
            LEFT JOIN triggers t ON t.id = sf.trigger_id
            ORDER BY sf.updated_at DESC
            """
        )
        rows = [dict(r) for r in cursor.fetchall()]
    for row in rows:
        row["enabled"] = bool(row["enabled"])
    return rows


def get_scope_filter(filter_id: str) -> Optional[dict]:
    """Return a single scope filter with its patterns, or None if not found."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT sf.id, sf.trigger_id, sf.mode, sf.enabled, sf.updated_at,
                   t.name AS trigger_name
            FROM scope_filters sf
            LEFT JOIN triggers t ON t.id = sf.trigger_id
            WHERE sf.id = ?
            """,
            (filter_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        result = dict(row)
        result["enabled"] = bool(result["enabled"])
        pat_cursor = conn.execute(
            """
            SELECT id, filter_id, type, pattern, description, created_at
            FROM scope_filter_patterns
            WHERE filter_id = ?
            ORDER BY created_at
            """,
            (filter_id,),
        )
        result["patterns"] = [dict(p) for p in pat_cursor.fetchall()]
    return result


def upsert_scope_filter(trigger_id: str, mode: str = "denylist", enabled: bool = True) -> str:
    """Insert or update a scope filter for the given trigger. Returns the filter ID."""
    with get_connection() as conn:
        cur = conn.execute("SELECT id FROM scope_filters WHERE trigger_id = ?", (trigger_id,))
        existing = cur.fetchone()
        if existing:
            conn.execute(
                """
                UPDATE scope_filters
                SET mode = ?, enabled = ?, updated_at = datetime('now')
                WHERE trigger_id = ?
                """,
                (mode, 1 if enabled else 0, trigger_id),
            )
            conn.commit()
            return existing["id"]
        fid = _gen_filter_id(conn)
        conn.execute(
            """
            INSERT INTO scope_filters (id, trigger_id, mode, enabled)
            VALUES (?, ?, ?, ?)
            """,
            (fid, trigger_id, mode, 1 if enabled else 0),
        )
        conn.commit()
        return fid


def update_scope_filter(
    filter_id: str,
    mode: Optional[str] = None,
    enabled: Optional[bool] = None,
) -> bool:
    """Update mode and/or enabled state of a scope filter. Returns True if updated."""
    updates = []
    params = []
    if mode is not None:
        updates.append("mode = ?")
        params.append(mode)
    if enabled is not None:
        updates.append("enabled = ?")
        params.append(1 if enabled else 0)
    if not updates:
        return False
    updates.append("updated_at = datetime('now')")
    params.append(filter_id)
    sql = f"UPDATE scope_filters SET {', '.join(updates)} WHERE id = ?"
    with get_connection() as conn:
        cursor = conn.execute(sql, params)
        conn.commit()
        return cursor.rowcount > 0


def list_patterns(filter_id: str) -> list[dict]:
    """Return all patterns for a scope filter."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, filter_id, type, pattern, description, created_at
            FROM scope_filter_patterns
            WHERE filter_id = ?
            ORDER BY created_at
            """,
            (filter_id,),
        )
        return [dict(r) for r in cursor.fetchall()]


def add_pattern(
    filter_id: str,
    type: str,
    pattern: str,
    description: str = "",
) -> str:
    """Add a pattern to a scope filter. Returns the new pattern ID."""
    with get_connection() as conn:
        pid = _gen_pattern_id(conn)
        conn.execute(
            """
            INSERT INTO scope_filter_patterns (id, filter_id, type, pattern, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            (pid, filter_id, type, pattern, description),
        )
        conn.execute(
            "UPDATE scope_filters SET updated_at = datetime('now') WHERE id = ?",
            (filter_id,),
        )
        conn.commit()
        return pid


def delete_pattern(pattern_id: str) -> bool:
    """Delete a pattern by ID. Returns True if deleted."""
    with get_connection() as conn:
        # Grab filter_id so we can update updated_at
        cur = conn.execute(
            "SELECT filter_id FROM scope_filter_patterns WHERE id = ?", (pattern_id,)
        )
        row = cur.fetchone()
        if row is None:
            return False
        filter_id = row["filter_id"]
        cursor = conn.execute("DELETE FROM scope_filter_patterns WHERE id = ?", (pattern_id,))
        if cursor.rowcount > 0:
            conn.execute(
                "UPDATE scope_filters SET updated_at = datetime('now') WHERE id = ?",
                (filter_id,),
            )
        conn.commit()
        return cursor.rowcount > 0
