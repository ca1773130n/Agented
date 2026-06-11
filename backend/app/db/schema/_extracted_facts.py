"""DDL for the extracted_facts table (Agentic-RAG answers, migration 153).

``extracted_facts`` persists claims extracted from leader-chat answers with
their provenance (evidence sources, confidence, session/project scope).
Dedup is session-scoped: same project+session+claim → same row (UNIQUE on
dedup_hash); a later session re-asserting the same claim records a NEW row.
"""

from __future__ import annotations


def create_extracted_facts_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS extracted_facts (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id    TEXT    NOT NULL,
            super_agent_id TEXT,
            project_id    TEXT,
            claim         TEXT    NOT NULL,
            evidence_json TEXT    NOT NULL DEFAULT '[]',
            confidence    REAL    NOT NULL DEFAULT 0.5,
            dedup_hash    TEXT    NOT NULL UNIQUE,
            created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_extracted_facts_session ON extracted_facts(session_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_extracted_facts_project "
        "ON extracted_facts(project_id, created_at DESC)"
    )
