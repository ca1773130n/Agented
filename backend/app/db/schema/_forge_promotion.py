"""Phase E propagation tables."""

from __future__ import annotations


def create_forge_promotion_tables(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS forge_promotion_evidence (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT NOT NULL,
            kind        TEXT NOT NULL,
            asset_id    TEXT NOT NULL,
            project_id  TEXT NOT NULL,
            eval_score  REAL NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_fpe_fingerprint ON forge_promotion_evidence(fingerprint)"
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS shared_forge_bindings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            scope       TEXT NOT NULL DEFAULT 'global',
            kind        TEXT NOT NULL,
            asset_id    TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            enabled     INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(scope, kind, fingerprint)
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sfb_enabled ON shared_forge_bindings(enabled)")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS project_shared_forge_adoptions (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id        TEXT NOT NULL,
            shared_binding_id INTEGER NOT NULL,
            state             TEXT NOT NULL DEFAULT 'adopted',
            created_at        TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(project_id, shared_binding_id)
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_psfa_project"
        " ON project_shared_forge_adoptions(project_id, state)"
    )
