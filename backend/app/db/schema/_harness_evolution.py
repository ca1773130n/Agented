"""Life-Harness T3 — evolution-round audit table.

One row per Codex-driven evolution attempt. Stores the inputs (harness state
+ trajectory window), the proposed patch, and what was actually applied so
that any future regression can be traced back to the round that introduced it.

Reference: arXiv 2605.22166 §5.2 Evolution Dynamics.
"""

from __future__ import annotations


def create_harness_evolution_tables(conn) -> None:
    """Project-scoped audit table for Codex-driven Forge evolution rounds.

    ``input_forge_json`` is a snapshot of the project's bound Forge primitives
    (rules/skills/hooks/commands/mcp_servers) at the moment the round
    started. ``output_patch_json`` carries Codex's proposed CRUD operations
    against those Forge tables. ``applied_asset_ids_json`` records what
    actually got persisted on approval.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS harness_evolution_rounds (
            id                       TEXT PRIMARY KEY,
            project_id               TEXT NOT NULL,
            started_at               TEXT NOT NULL DEFAULT (datetime('now')),
            finished_at              TEXT,
            status                   TEXT NOT NULL DEFAULT 'pending'
                                     CHECK (status IN (
                                         'pending', 'running', 'awaiting_approval',
                                         'applied', 'failed', 'aborted'
                                     )),
            input_window_since       TEXT,
            input_window_until       TEXT,
            input_execution_count    INTEGER NOT NULL DEFAULT 0,
            input_forge_json         TEXT NOT NULL DEFAULT '{}',
            output_patch_json        TEXT,
            applied_asset_ids_json   TEXT NOT NULL DEFAULT '[]',
            error_message            TEXT,
            notes                    TEXT,
            scratch_dir              TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_her_project "
        "ON harness_evolution_rounds(project_id, started_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_her_status "
        "ON harness_evolution_rounds(status)"
    )
