"""DDL for Skill-Sleep runs (SkillOpt integration, migration 160).

One row per gated skill-optimization attempt: the blind judge scored the
CURRENT skill body (arm A) vs a CANDIDATE body (arm B) on a held-out question
partition, and the candidate was accepted only if it strictly improved. The
row records both composite scores, the verdict, and provenance for the
operator-adopt surface.
"""

from __future__ import annotations


def create_skill_sleep_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS skill_sleep_runs (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id       TEXT    NOT NULL,
            skill_name       TEXT    NOT NULL,
            skill_id         INTEGER,
            status           TEXT    NOT NULL DEFAULT 'running'
                CHECK (status IN ('running','accepted','rejected','abstained','failed')),
            current_score    REAL,
            candidate_score  REAL,
            delta            REAL,
            question_count   INTEGER NOT NULL DEFAULT 0,
            partition_seed   INTEGER NOT NULL DEFAULT 0,
            judge_backend    TEXT,
            candidate_body   TEXT,
            reason           TEXT,
            created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
            finished_at      TEXT,
            adopted_at       TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_skill_sleep_runs_project "
        "ON skill_sleep_runs(project_id, created_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_skill_sleep_runs_skill "
        "ON skill_sleep_runs(skill_name, created_at DESC)"
    )
