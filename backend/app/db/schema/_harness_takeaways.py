"""Session-level takeaways — the positive-learning side of Life-Harness.

Where the failure annotator captures *mistakes* (H2/H3/H4 incidents), the
takeaway extractor captures *what worked* / *what was learned* per session:
user preferences, discovered procedures, tool patterns, constraints, domain
facts. Each takeaway proposes a target (memory / rule / skill / KG /
CLAUDE.md) and (when supported) auto-applies or queues for operator review.

One row per detected takeaway. ``applied`` flips when the operator clicks
Apply in the UI (or when auto-apply ran for high-confidence kinds). The
asset id of whatever the takeaway *became* (a rule row, a KG entity, a
memory key) gets stored on ``applied_asset_id`` for the audit trail.
"""

from __future__ import annotations


def create_harness_takeaway_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS session_takeaways (
            id                      TEXT    PRIMARY KEY,
            session_kind            TEXT    NOT NULL,
            session_id              TEXT    NOT NULL,
            project_id              TEXT,
            kind                    TEXT    NOT NULL
                                    CHECK (kind IN (
                                        'user_preference',
                                        'discovered_procedure',
                                        'tool_pattern',
                                        'constraint',
                                        'domain_fact',
                                        'failure_root_cause',
                                        'success_pattern'
                                    )),
            content                 TEXT    NOT NULL,
            confidence              REAL    NOT NULL DEFAULT 0.5,
            evidence_json           TEXT    NOT NULL DEFAULT '{}',
            suggested_target        TEXT
                                    CHECK (suggested_target IS NULL OR
                                           suggested_target IN (
                                               'memory', 'rule', 'skill',
                                               'knowledge_graph', 'claude_md'
                                           )),
            suggested_payload_json  TEXT    NOT NULL DEFAULT '{}',
            extractor_version       TEXT    NOT NULL,
            applied                 INTEGER NOT NULL DEFAULT 0,
            applied_at              TEXT,
            applied_target          TEXT,
            applied_asset_id        TEXT,
            dismissed               INTEGER NOT NULL DEFAULT 0,
            dismissed_reason        TEXT,
            created_at              TEXT    NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tk_project "
        "ON session_takeaways(project_id, created_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tk_session "
        "ON session_takeaways(session_kind, session_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tk_kind ON session_takeaways(kind)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tk_status "
        "ON session_takeaways(applied, dismissed)"
    )
