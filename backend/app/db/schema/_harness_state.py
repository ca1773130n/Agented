"""Durable harness run-state store (Harness-1 integration, Phase 1 / P1).

State-externalizing harness foundation. ``harness_runs`` holds one
recoverable run-state row per execution (a step cursor + a running budget
total + a lifecycle status). ``harness_checkpoints`` is the append-only
turn ledger: each row is a serialized snapshot of the run's externalized
state at a given step, so a crash mid-run leaves recoverable state instead
of a stale ``running`` row with NULL output.

Both tables FK to ``execution_logs(execution_id)`` — the stable string key,
which carries a UNIQUE constraint — with ``ON DELETE CASCADE`` so run state
is garbage-collected with its execution.

Reference: docs/research/harness-1-integration.md (P1); arXiv:2606.02373
(Harness-1: RL for Search Agents with State-Externalizing Harnesses).
"""

from __future__ import annotations


def create_harness_state_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS harness_runs (
            execution_id  TEXT PRIMARY KEY,
            status        TEXT    NOT NULL DEFAULT 'running',
            step_cursor   INTEGER NOT NULL DEFAULT 0,
            budget_used   REAL    NOT NULL DEFAULT 0,
            created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at    TEXT    NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (execution_id)
                REFERENCES execution_logs(execution_id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS harness_checkpoints (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id  TEXT    NOT NULL,
            step          INTEGER NOT NULL,
            ledger_json   TEXT    NOT NULL DEFAULT '{}',
            created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (execution_id)
                REFERENCES execution_logs(execution_id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_harness_checkpoints_exec_step "
        "ON harness_checkpoints(execution_id, step DESC)"
    )
