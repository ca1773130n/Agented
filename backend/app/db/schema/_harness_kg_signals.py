"""Phase E2 KG-signal source tables."""

from __future__ import annotations


def create_harness_kg_signals_tables(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS harness_kg_signals (
            signal_id       TEXT PRIMARY KEY,
            project_id      TEXT NOT NULL,
            round_id        TEXT,
            question        TEXT NOT NULL,
            content         TEXT NOT NULL,
            weight          REAL NOT NULL,
            already_forged  INTEGER NOT NULL DEFAULT 0,
            first_seen_at   TEXT NOT NULL,
            captured_at     TEXT NOT NULL
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hks_project ON harness_kg_signals(project_id)")
