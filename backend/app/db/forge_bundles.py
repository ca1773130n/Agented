"""CRUD for cross-kind Forge *bundles* — a named, scope-tagged group that
can hold primitives of ANY kind in one structure.

Why this exists: the legacy ``skill_sets`` table (migration 87) is
skills-only. The Forge needs a grouping primitive that spans every kind
(rule/skill/hook/command/mcp_server/plugin), so a single operator action can
stage a coherent set. ``forge_bundles`` + ``forge_bundle_items`` (migration
156) are that primitive.

This module also provides ``bind_bundle_to_project`` — binds every item of
any kind to a project in ONE ``get_connection()`` block (true single-call
atomicity) via the shared ``project_forge_bindings.upsert_binding``.
"""

from __future__ import annotations

from typing import List, Optional

from app.utils.timezone import utc_now_iso

from .connection import get_connection
from .ids import generate_id
from .project_forge_bindings import VALID_KINDS, _ensure_propagation_columns, upsert_binding


def _bundle_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "scope": row["scope"],
        "created_at": row["created_at"],
    }


def _item_to_dict(row) -> dict:
    return {
        "bundle_id": row["bundle_id"],
        "kind": row["kind"],
        "asset_id": row["asset_id"],
        "position": row["position"],
    }


# --- forge_bundles CRUD --------------------------------------------------


def create_forge_bundle(
    name: str,
    description: Optional[str] = None,
    scope: str = "project",
) -> dict:
    """Create a bundle. ``name`` is UNIQUE; raises sqlite3.IntegrityError on
    collision. ``id`` uses the ``bundle-`` prefix."""
    bundle_id = generate_id("bundle-")
    created_at = utc_now_iso()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO forge_bundles (id, name, description, scope, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (bundle_id, name, description, scope, created_at),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM forge_bundles WHERE id = ?", (bundle_id,)).fetchone()
        return _bundle_to_dict(row)


def get_forge_bundle(bundle_id: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM forge_bundles WHERE id = ?", (bundle_id,)).fetchone()
        return _bundle_to_dict(row) if row else None


def get_forge_bundle_by_name(name: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM forge_bundles WHERE name = ?", (name,)).fetchone()
        return _bundle_to_dict(row) if row else None


def list_forge_bundles(scope: Optional[str] = None) -> List[dict]:
    sql = "SELECT * FROM forge_bundles"
    params: tuple = ()
    if scope is not None:
        sql += " WHERE scope = ?"
        params = (scope,)
    sql += " ORDER BY created_at ASC, id ASC"
    with get_connection() as conn:
        return [_bundle_to_dict(r) for r in conn.execute(sql, params).fetchall()]


def delete_forge_bundle(bundle_id: str) -> bool:
    """Delete a bundle. ``forge_bundle_items`` rows cascade via ON DELETE
    CASCADE (foreign_keys PRAGMA is enabled in get_connection)."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM forge_bundles WHERE id = ?", (bundle_id,))
        conn.commit()
        return cursor.rowcount > 0


# --- forge_bundle_items CRUD ---------------------------------------------


def add_bundle_item(
    bundle_id: str,
    kind: str,
    asset_id: str,
    position: Optional[int] = None,
) -> dict:
    """Add an item of any valid kind to a bundle. Auto-assigns position to
    the current tail (max+1) when ``position`` is None. Idempotent on the
    (bundle_id, kind, asset_id) primary key — re-adding updates position."""
    if kind not in VALID_KINDS:
        raise ValueError(f"Unknown forge kind: {kind!r}")
    with get_connection() as conn:
        if position is None:
            position = conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM forge_bundle_items "
                "WHERE bundle_id = ?",
                (bundle_id,),
            ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO forge_bundle_items (bundle_id, kind, asset_id, position)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(bundle_id, kind, asset_id) DO UPDATE SET
                position = excluded.position
            """,
            (bundle_id, kind, asset_id, position),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM forge_bundle_items WHERE bundle_id = ? AND kind = ? AND asset_id = ?",
            (bundle_id, kind, asset_id),
        ).fetchone()
        return _item_to_dict(row)


def list_forge_bundle_items(bundle_id: str) -> List[dict]:
    """Return a bundle's items ordered by position (then kind, asset_id)."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM forge_bundle_items WHERE bundle_id = ? "
            "ORDER BY position ASC, kind ASC, asset_id ASC",
            (bundle_id,),
        )
        return [_item_to_dict(r) for r in cursor.fetchall()]


# --- atomic bundle bind ----------------------------------------------------


def bind_bundle_to_project(project_id: str, bundle_id: str) -> int:
    """Bind every item of a bundle to ``project_id`` in ONE transaction.

    If any item raises, nothing commits — no partial bind. Returns the
    number of items bound (0 when the bundle is empty or unknown).
    """
    with get_connection() as conn:
        items = conn.execute(
            "SELECT * FROM forge_bundle_items WHERE bundle_id = ? "
            "ORDER BY position ASC, kind ASC, asset_id ASC",
            (bundle_id,),
        ).fetchall()
        if not items:
            return 0
        # Legacy DBs gain the provenance columns lazily — every other
        # write/read path runs this guard before touching them; so must the
        # bundle bind (upsert_binding writes source_scope/conflict_policy/…).
        _ensure_propagation_columns(conn)
        for item in items:
            upsert_binding(
                conn,
                project_id,
                item["kind"],
                str(item["asset_id"]),
                position=item["position"],
            )
        conn.commit()
        return len(items)
