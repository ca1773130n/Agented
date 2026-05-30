"""project_autonomy_config — per-project autonomous-apply policy (Phase D)."""

from __future__ import annotations


def create_project_autonomy_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS project_autonomy_config (
            project_id  TEXT PRIMARY KEY,
            enabled     INTEGER NOT NULL DEFAULT 0,
            policy_json TEXT NOT NULL DEFAULT '{}',
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_autonomy_enabled ON project_autonomy_config(enabled)"
    )
