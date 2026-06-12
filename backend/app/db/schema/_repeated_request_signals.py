"""Repeated-request signal store — the persistence substrate for the
self-improvement loop (Phase 22, REQ-22).

A hash-keyed table whose UPSERT *accumulates* evidence of recurring user
requests: salience grows with repetition rather than decaying. The detector
(22-03) writes rows here on every session completion; the gate (22-05) reads
``occurrence_count`` and ``verified_success_count`` to decide whether a
request recurs often enough (and succeeds reliably enough) to be promoted
into an auto-created skill.

Design notes:
- ``request_hash`` is the sha256 of the normalized request text and is the
  UPSERT conflict key (also the embed-disabled exact-match key, EVAL A1).
- ``first_seen_at`` is set ONCE on the original insert and never overwritten —
  the ON CONFLICT branch touches only ``last_seen_at`` + the growing counters.
- ``embedding`` is the ``serialize_embedding`` BLOB (NULL when embedding is
  disabled), mirroring how ``agent_memory`` stores vectors.
- ``example_session_ids`` is a JSON array FIFO-capped at 5 by the repo layer.
"""

from __future__ import annotations


def create_repeated_request_signal_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS repeated_request_signals (
            request_hash            TEXT    PRIMARY KEY,
            project_id              TEXT,
            session_kind            TEXT    NOT NULL,
            representative_text     TEXT    NOT NULL,
            embedding               BLOB,
            occurrence_count        INTEGER NOT NULL DEFAULT 1,
            verified_success_count  INTEGER NOT NULL DEFAULT 0,
            example_session_ids     TEXT    NOT NULL DEFAULT '[]',
            skill_created           INTEGER NOT NULL DEFAULT 0,
            first_seen_at           TEXT    NOT NULL,
            last_seen_at            TEXT    NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_repeated_request_signals_project "
        "ON repeated_request_signals(project_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_repeated_request_signals_kind "
        "ON repeated_request_signals(session_kind)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_repeated_request_signals_skill_created "
        "ON repeated_request_signals(skill_created)"
    )
