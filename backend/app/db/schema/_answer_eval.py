"""DDL for answer eval tables (Agentic-RAG answers, migration 154).

``answer_eval_runs`` is one evaluation batch (baseline vs pipeline across N
questions). ``answer_eval_results`` holds per-question per-arm scores.
FK cascade: deleting a run removes its results.
"""

from __future__ import annotations


def create_answer_eval_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS answer_eval_runs (
            id                     INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id             TEXT    NOT NULL,
            question_count         INTEGER NOT NULL DEFAULT 0,
            judge_backend          TEXT,
            baseline_groundedness  REAL,
            baseline_sufficiency   REAL,
            baseline_quality       REAL,
            pipeline_groundedness  REAL,
            pipeline_sufficiency   REAL,
            pipeline_quality       REAL,
            delta_groundedness     REAL,
            delta_sufficiency      REAL,
            delta_quality          REAL,
            status                 TEXT    NOT NULL DEFAULT 'running'
                CHECK (status IN ('running','complete','failed')),
            created_at             TEXT    NOT NULL DEFAULT (datetime('now')),
            finished_at            TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS answer_eval_results (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id        INTEGER NOT NULL,
            question      TEXT    NOT NULL,
            arm           TEXT    NOT NULL CHECK (arm IN ('baseline','pipeline')),
            answer_text   TEXT,
            groundedness  REAL,
            sufficiency   REAL,
            quality       REAL,
            judge_reason  TEXT,
            tokens        INTEGER,
            cost_usd      REAL,
            created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (run_id)
                REFERENCES answer_eval_runs(id) ON DELETE CASCADE
        )
        """
    )
