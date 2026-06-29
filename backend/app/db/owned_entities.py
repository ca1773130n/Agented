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

# Whitelist of sortable columns. Never interpolate raw user input into a SQL
# ORDER BY — map it through this set first so injection is structurally
# impossible.
_SORT_COLUMNS = {"name", "created_at", "updated_at"}
_SORT_ORDERS = {"asc", "desc"}


def _order_clause(sort_field: Optional[str], sort_order: Optional[str], default: str) -> str:
    """Build a SAFE ``ORDER BY col dir`` string from whitelisted inputs.

    ``sort_field`` must be in ``_SORT_COLUMNS`` or it falls back to ``default``
    (the caller-supplied trusted column). ``sort_order`` must be asc/desc or it
    falls back to asc. Inputs are never interpolated raw.
    """
    col = sort_field if sort_field in _SORT_COLUMNS else default
    order = sort_order.lower() if isinstance(sort_order, str) else "asc"
    if order not in _SORT_ORDERS:
        order = "asc"
    return f"ORDER BY {col} {order.upper()}"


def get_for_user(
    table: str,
    user_id: str,
    limit: Optional[int] = None,
    offset: int = 0,
    extra_where: str = "",
    extra_params: Optional[list] = None,
    search: Optional[str] = None,
    sort_field: Optional[str] = None,
    sort_order: str = "asc",
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
    if search:
        sql += " AND (name LIKE ? OR description LIKE ?)"
        like = f"%{search}%"
        params.extend([like, like])
    sql += " " + _order_clause(sort_field, sort_order, default="id")
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

    with get_connection() as conn:
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def count_for_user(table: str, user_id: str, search: Optional[str] = None) -> int:
    if table not in _VALID_TABLES:
        raise ValueError(f"unknown owned-entity table: {table!r}")
    sql = f"SELECT COUNT(*) FROM {table} WHERE user_id = ?"
    params: list = [user_id]
    if search:
        sql += " AND (name LIKE ? OR description LIKE ?)"
        like = f"%{search}%"
        params.extend([like, like])
    with get_connection() as conn:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row else 0


# Backfilled sentinel for rows that predate per-user ownership. Such rows are
# treated as shared/unowned so the move to per-object enforcement doesn't lock
# existing data away from non-admin users.
LEGACY_OWNER = "legacy@local"


def resolve_owner_user_id(conn, user_id: Optional[str]) -> Optional[str]:
    """Resolve the owning user_id for a create, falling back to the legacy user.

    Falls back to ``legacy@local`` when the caller passes no user_id OR one that
    isn't a real user — the latter happens for an admin API key whose principal
    has no user account (its resolved id is None or the role-row id), which would
    otherwise violate the ``<table>.user_id`` FK and 500 the create. Pass the
    open connection so the lookup joins the create's transaction.
    """
    if user_id:
        row = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if row:
            return user_id
    row = conn.execute("SELECT id FROM users WHERE email = ?", (LEGACY_OWNER,)).fetchone()
    return row[0] if row else None


def get_owner(table: str, entity_id: str) -> Optional[str]:
    """Return the owning user_id for a row, or None if the row doesn't exist
    or has no owner set. Allow-listed table names only."""
    if table not in _VALID_TABLES:
        raise ValueError(f"unknown owned-entity table: {table!r}")
    with get_connection() as conn:
        row = conn.execute(f"SELECT user_id FROM {table} WHERE id = ?", (entity_id,)).fetchone()
    if not row:
        return None
    try:
        return row["user_id"]
    except (KeyError, IndexError, TypeError):
        return row[0]


def can_access(table: str, entity_id: str, user_id: Optional[str], role: Optional[str]) -> bool:
    """Per-object access decision for owned entities.

    Admins always pass. Rows with no owner or the legacy sentinel are shared
    (backward compat). A non-existent row passes here so the handler can return
    its own 404. Otherwise only the owner passes.
    """
    if role == "admin":
        return True
    owner = get_owner(table, entity_id)
    if owner is None or owner == LEGACY_OWNER:
        return True
    return owner == user_id
