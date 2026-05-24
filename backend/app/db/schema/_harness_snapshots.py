"""Life-Harness T2 integration — per-execution harness snapshots.

One row per execution that had at least one enabled harness layer at spawn
time. Records the compiled ``HarnessBuildArtifact`` inline as JSON plus a
``layer_versions`` map (``{"h2": 3, "h3": 1, ...}``) for fast joins.

Why a separate table from execution_logs:
    - Most executions won't have any layers configured, so embedding a
      column on execution_logs would be sparse and pollute the schema of
      a hot, append-heavy table.
    - The snapshot is the input to T3's evolution loop, which queries by
      bot_id and layer version. A focused table keeps those joins cheap.

Why capture-only (``applied = 0``):
    T2 ships observation, not behavioural change. The artifact records what
    *would have* been injected; the actual injection into the Claude Code
    spawn argv / env is a separate follow-up.
"""

from __future__ import annotations


def create_harness_snapshot_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS execution_harness_snapshots (
            execution_id         TEXT PRIMARY KEY,
            bot_id               TEXT NOT NULL,
            harness_kind         TEXT NOT NULL,
            layer_versions_json  TEXT NOT NULL DEFAULT '{}',
            artifact_json        TEXT NOT NULL,
            applied              INTEGER NOT NULL DEFAULT 0,
            created_at           TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ehs_bot_id "
        "ON execution_harness_snapshots(bot_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ehs_applied "
        "ON execution_harness_snapshots(applied)"
    )
