"""Typed tool_use evidence ledger (Harness-1 Phase 2, P3).

One row per ToolUseEvent emitted by an in-process super-agent run, keyed by
``session_id`` (FK to ``super_agent_sessions(id)``), so the run's tool calls
are queryable in order without grepping the transcript. ``seq`` is a
per-session monotonic ordinal.

Reference: docs/superpowers/specs/2026-06-10-harness-phase2-evidence-verification-design.md
"""

from __future__ import annotations


def create_harness_evidence_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS harness_evidence (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT    NOT NULL,
            super_agent_id  TEXT,
            seq             INTEGER NOT NULL,
            tool_name       TEXT    NOT NULL,
            tool_input_json TEXT    NOT NULL DEFAULT '{}',
            tool_use_id     TEXT,
            created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE (session_id, seq),
            FOREIGN KEY (session_id)
                REFERENCES super_agent_sessions(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_harness_evidence_session "
        "ON harness_evidence(session_id, seq)"
    )
