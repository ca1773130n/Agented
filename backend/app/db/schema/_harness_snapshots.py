"""Per-session record of which Forge primitives were active at start.

Polymorphic ``(session_kind, session_id)`` identifier so the same table
captures trigger executions, workflow nodes, super-agent sessions, and
project sessions. ``project_id`` is denormalized so the evolver can
window snapshots cheaply on project scope without joining per kind.

``bundle_hash`` is a deterministic SHA-256 digest of the active Forge
bindings (sufficient to identify "same harness as session X").
``resolved_bindings_json`` lists the ``(kind, asset_id)`` pairs that fed
the renderer.
"""

from __future__ import annotations


def create_harness_snapshot_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS session_harness_snapshots (
            session_kind            TEXT NOT NULL,
            session_id              TEXT NOT NULL,
            project_id              TEXT,
            harness_kind            TEXT NOT NULL,
            bundle_hash             TEXT,
            resolved_bindings_json  TEXT NOT NULL DEFAULT '[]',
            created_at              TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (session_kind, session_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_shs_project "
        "ON session_harness_snapshots(project_id, created_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_shs_bundle "
        "ON session_harness_snapshots(bundle_hash)"
    )
