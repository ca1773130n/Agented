"""Team-execution observation DDL.

Persists every team-orchestrated run so the Life-Harness takeaway
extractor + failure annotator can attach to ``session_kind='team_session'``
the same way they attach to trigger executions, workflows, super-agents,
and project sessions.

The in-memory ``TeamExecutionTracker`` keeps live state (300 s TTL); this
table is the durable mirror that survives the tracker's cleanup.
"""

from __future__ import annotations


def create_team_execution_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS team_executions (
            id TEXT PRIMARY KEY,
            team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            topology TEXT NOT NULL,
            trigger_type TEXT NOT NULL DEFAULT 'manual',
            project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
            message TEXT,
            status TEXT NOT NULL DEFAULT 'running',
            error TEXT,
            execution_ids TEXT,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_team_executions_team "
        "ON team_executions(team_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_team_executions_project "
        "ON team_executions(project_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_team_executions_status "
        "ON team_executions(status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_team_executions_started "
        "ON team_executions(started_at DESC)"
    )
