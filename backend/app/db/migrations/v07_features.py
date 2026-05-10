"""Migrations for v0.7.0 track — split out of migrations.py in v0.7.3c.

Hosts v116+ migrations specific to the v0.7.x track. Earlier v0.7.x
migrations (114 trigger_events, 115 execution_logs_trigger_started_index)
live in v06_features alongside the v0.6.x batch because they fall in
the same numeric range.
"""


def _migrate_116_super_agent_activity(conn):
    """v0.7.7: super-agent activity timeline + cost rollup."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS super_agent_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            super_agent_id TEXT NOT NULL,
            session_id TEXT,
            event_type TEXT NOT NULL,
            recorded_at TIMESTAMP NOT NULL,
            payload TEXT NOT NULL,
            cost_tokens_in INTEGER,
            cost_tokens_out INTEGER,
            cost_usd REAL,
            status TEXT NOT NULL DEFAULT 'ok',
            error_message TEXT,
            duration_ms INTEGER
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_saa_super_agent_recorded "
        "ON super_agent_activity(super_agent_id, recorded_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_saa_session_recorded "
        "ON super_agent_activity(session_id, recorded_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_saa_recorded_at "
        "ON super_agent_activity(recorded_at)"
    )


V07_MIGRATIONS: list = [
    # v0.7.7: super-agent activity inspector — timeline + rollup.
    (116, "super_agent_activity", _migrate_116_super_agent_activity),
]
