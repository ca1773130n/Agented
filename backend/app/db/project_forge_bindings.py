"""CRUD for ``project_forge_bindings`` — per-project sticky Forge
context defaults consumed by ``ContextCompilerService``.

Behavior notes:

* ``replace_for_project`` is the bulk-write API the UI uses when the
  operator clicks "Save" on the bindings panel. It runs inside a
  single transaction so the operator never sees a half-saved state
  if the server dies mid-write.
* ``add_binding`` is idempotent on the ``UNIQUE(project_id, kind,
  asset_id)`` constraint — re-adding a binding bumps its position to
  the tail and re-enables it, rather than raising.
* Reads are not paginated — bindings per project are bounded by the
  operator's appetite for sticky context, which in practice is
  small (<50). If that assumption breaks, add LIMIT/OFFSET.
"""

from __future__ import annotations

from typing import List, Optional

from .connection import get_connection

VALID_KINDS = {"rule", "skill", "hook", "command", "mcp_server", "plugin"}


def _ensure_propagation_columns(conn) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(project_forge_bindings)")}
    if "source_scope" not in cols:
        conn.execute(
            "ALTER TABLE project_forge_bindings ADD COLUMN"
            " source_scope TEXT NOT NULL DEFAULT 'project'"
        )
    if "source_shared_binding_id" not in cols:
        conn.execute(
            "ALTER TABLE project_forge_bindings ADD COLUMN source_shared_binding_id INTEGER"
        )
    if "conflict_policy" not in cols:
        conn.execute(
            "ALTER TABLE project_forge_bindings ADD COLUMN"
            " conflict_policy TEXT NOT NULL DEFAULT 'local_wins'"
        )
    if "fingerprint" not in cols:
        conn.execute("ALTER TABLE project_forge_bindings ADD COLUMN fingerprint TEXT")


def _row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "kind": row["kind"],
        "asset_id": row["asset_id"],
        "role": row["role"],
        "enabled": bool(row["enabled"]),
        "position": row["position"],
        "created_at": row["created_at"],
        "source_scope": row["source_scope"],
        "source_shared_binding_id": row["source_shared_binding_id"],
        "conflict_policy": row["conflict_policy"],
        "fingerprint": row["fingerprint"],
    }


def list_bindings(project_id: str, *, enabled_only: bool = False) -> List[dict]:
    """Return all bindings for ``project_id`` ordered by (kind, position)."""
    sql = (
        "SELECT * FROM project_forge_bindings WHERE project_id = ? "
        + ("AND enabled = 1 " if enabled_only else "")
        + "ORDER BY kind ASC, position ASC, id ASC"
    )
    with get_connection() as conn:
        _ensure_propagation_columns(conn)
        cursor = conn.execute(sql, (project_id,))
        return [_row_to_dict(row) for row in cursor.fetchall()]


def get_binding(binding_id: int) -> Optional[dict]:
    with get_connection() as conn:
        _ensure_propagation_columns(conn)
        cursor = conn.execute(
            "SELECT * FROM project_forge_bindings WHERE id = ?",
            (binding_id,),
        )
        row = cursor.fetchone()
        return _row_to_dict(row) if row else None


def add_binding(
    project_id: str,
    kind: str,
    asset_id: str,
    *,
    role: Optional[str] = None,
    position: Optional[int] = None,
    enabled: bool = True,
    source_scope: str = "project",
    source_shared_binding_id: Optional[int] = None,
    fingerprint: Optional[str] = None,
) -> dict:
    """Insert a binding. Idempotent: re-adding bumps position + re-enables."""
    if kind not in VALID_KINDS:
        raise ValueError(f"Unknown forge kind: {kind!r}")
    with get_connection() as conn:
        _ensure_propagation_columns(conn)
        if position is None:
            cursor = conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM project_forge_bindings "
                "WHERE project_id = ? AND kind = ?",
                (project_id, kind),
            )
            position = cursor.fetchone()[0]
        conn.execute(
            """
            INSERT INTO project_forge_bindings
                (project_id, kind, asset_id, role, enabled, position,
                 source_scope, source_shared_binding_id, fingerprint)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, kind, asset_id) DO UPDATE SET
                role                    = excluded.role,
                enabled                 = excluded.enabled,
                position                = excluded.position,
                source_scope            = excluded.source_scope,
                source_shared_binding_id = excluded.source_shared_binding_id,
                fingerprint             = excluded.fingerprint
            """,
            (
                project_id,
                kind,
                asset_id,
                role,
                1 if enabled else 0,
                position,
                source_scope,
                source_shared_binding_id,
                fingerprint,
            ),
        )
        conn.commit()
        cursor = conn.execute(
            "SELECT * FROM project_forge_bindings "
            "WHERE project_id = ? AND kind = ? AND asset_id = ?",
            (project_id, kind, asset_id),
        )
        return _row_to_dict(cursor.fetchone())


def remove_binding(binding_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM project_forge_bindings WHERE id = ?",
            (binding_id,),
        )
        conn.commit()
        return cursor.rowcount > 0


def replace_for_project(project_id: str, bindings: List[dict]) -> List[dict]:
    """Atomically replace the entire binding set for a project.

    ``bindings`` is the new full list — anything currently bound and
    not in this list is deleted. Order within ``bindings`` becomes
    the persisted ``position`` (per kind).
    """
    with get_connection() as conn:
        _ensure_propagation_columns(conn)
        conn.execute(
            "DELETE FROM project_forge_bindings WHERE project_id = ?",
            (project_id,),
        )
        per_kind_pos: dict[str, int] = {}
        for b in bindings:
            kind = b.get("kind")
            asset_id = b.get("asset_id")
            if kind not in VALID_KINDS or not asset_id:
                continue
            pos = per_kind_pos.get(kind, 0)
            per_kind_pos[kind] = pos + 1
            # Carry the SAME provenance columns add_binding writes, with the
            # same default coalescing, so the two write paths can never drift.
            conn.execute(
                """
                INSERT INTO project_forge_bindings
                    (project_id, kind, asset_id, role, enabled, position,
                     source_scope, source_shared_binding_id, fingerprint,
                     conflict_policy)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    kind,
                    str(asset_id),
                    b.get("role"),
                    1 if b.get("enabled", True) else 0,
                    pos,
                    b.get("source_scope", "project"),
                    b.get("source_shared_binding_id"),
                    b.get("fingerprint"),
                    b.get("conflict_policy", "local_wins"),
                ),
            )
        conn.commit()
    return list_bindings(project_id)
