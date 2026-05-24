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
    """Per-execution record of which Forge primitives were active at spawn.

    ``bundle_hash`` is a deterministic digest of the rendered ``ContextBundle``
    (sufficient to identify "same harness as run X"). ``resolved_bindings_json``
    lists the ``(kind, asset_id)`` pairs that fed into the bundle. T3's
    evolution loop joins on ``project_id`` + this table + ``execution_annotations``
    to compute pre/post-evolution impact deltas.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS execution_harness_snapshots (
            execution_id            TEXT PRIMARY KEY,
            project_id              TEXT,
            bot_id                  TEXT,
            harness_kind            TEXT NOT NULL,
            bundle_hash             TEXT,
            resolved_bindings_json  TEXT NOT NULL DEFAULT '[]',
            created_at              TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ehs_project_id "
        "ON execution_harness_snapshots(project_id, created_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ehs_bundle_hash "
        "ON execution_harness_snapshots(bundle_hash)"
    )
