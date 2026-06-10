"""Durable verification records (Harness-1 Phase 2, P5).

One row per claim checked against an execution, keyed by
``execution_logs(execution_id)``. Sits next to Phase 1's ``harness_runs``.
Read/written via app.db.verification_records and VerificationService; consulted
by the post-hoc PR gate in ExecutionService.
"""

from __future__ import annotations


def create_verification_records_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS verification_records (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id  TEXT    NOT NULL,
            claim         TEXT    NOT NULL,
            status        TEXT    NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending', 'passed', 'failed')),
            evidence_ref  TEXT,
            checked_at    TEXT,
            created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (execution_id)
                REFERENCES execution_logs(execution_id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_verification_records_exec "
        "ON verification_records(execution_id)"
    )
