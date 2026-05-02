"""Per-user reads for owned-entity tables (track B, waves 39-44).

Every owned-entity table follows the same shape: a ``user_id`` FK to
``users``, backfilled to ``legacy@local`` for pre-existing rows. This
module centralizes the user-scoped read so we don't grow N copies of
the same WHERE-clause logic across N table modules.

Routes that already had bespoke readers (products) keep their dedicated
helper; this module is the default for new tables that don't.
"""

from __future__ import annotations

from typing import List, Optional

from .connection import get_connection

_VALID_TABLES = {
    # batch 1 (wave 41)
    "projects",
    "teams",
    "agents",
    "plugins",
    "super_agents",
    # batch 2 (wave 42)
    "hooks",
    "commands",
    "rules",
    "triggers",
    "mcp_servers",
    "sketches",
    "workflows",
    "user_skills",
    "agent_conversations",
    "design_conversations",
}


def get_for_user(
    table: str,
    user_id: str,
    limit: Optional[int] = None,
    offset: int = 0,
    extra_where: str = "",
    extra_params: Optional[list] = None,
) -> List[dict]:
    """Generic user-scoped fetch. Allow-listed table names only."""
    if table not in _VALID_TABLES:
        raise ValueError(f"unknown owned-entity table: {table!r}")

    sql = f"SELECT * FROM {table} WHERE user_id = ?"
    params: list = [user_id]
    if extra_where:
        sql += f" AND {extra_where}"
        if extra_params:
            params.extend(extra_params)
    sql += " ORDER BY id ASC"
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

    with get_connection() as conn:
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def count_for_user(table: str, user_id: str) -> int:
    if table not in _VALID_TABLES:
        raise ValueError(f"unknown owned-entity table: {table!r}")
    with get_connection() as conn:
        row = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row[0] if row else 0
