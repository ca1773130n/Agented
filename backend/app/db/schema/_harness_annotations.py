"""Life-Harness failure-annotation DDL (post-pivot, session-scoped).

Two tables back the four-layer failure-observability surface across EVERY
session kind Agented runs (trigger executions, workflow nodes, super-agent
sessions, project sessions). Layers follow the paper's priority order:
H2 → H3 → H4 → general (Appendix A.1).

- ``session_layer_incidents`` — one row per detected interface incident.
  Polymorphic ``(session_kind, session_id)`` identifier so the annotator
  works against any session producer.
- ``session_annotations`` — per-session denormalized roll-up consumed by
  the Activity-lane card and the evolver. ``project_id`` is denormalized
  here so project-scoped queries don't have to fan out per session kind.

Session kinds today: ``trigger_execution``, ``workflow``, ``super_agent``,
``project_session``. New kinds are added by adding a fetcher in
``app.services.harness_failure_annotator``.

Reference: arXiv 2605.22166 Appendix A.1.
"""

from __future__ import annotations


def create_harness_annotation_tables(conn) -> None:
    """Create Life-Harness annotation tables on a fresh DB. Idempotent."""

    # Per-incident detail. Polymorphic session reference.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS session_layer_incidents (
            id                TEXT    PRIMARY KEY,
            session_kind      TEXT    NOT NULL,
            session_id        TEXT    NOT NULL,
            project_id        TEXT,
            layer             TEXT    NOT NULL
                              CHECK (layer IN ('h2', 'h3', 'h4', 'general')),
            priority          INTEGER NOT NULL,
            kind              TEXT    NOT NULL,
            evidence_json     TEXT    NOT NULL DEFAULT '{}',
            event_index       INTEGER,
            detector_version  TEXT    NOT NULL,
            created_at        TEXT    NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sli_session "
        "ON session_layer_incidents(session_kind, session_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sli_project "
        "ON session_layer_incidents(project_id, created_at DESC)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sli_layer ON session_layer_incidents(layer)")

    # Per-session roll-up. Recomputed on each annotation pass.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS session_annotations (
            session_kind       TEXT NOT NULL,
            session_id         TEXT NOT NULL,
            project_id         TEXT,
            annotator_version  TEXT NOT NULL,
            primary_layer      TEXT
                               CHECK (primary_layer IS NULL OR
                                      primary_layer IN ('h2', 'h3', 'h4', 'general')),
            incident_count     INTEGER NOT NULL DEFAULT 0,
            h2_count           INTEGER NOT NULL DEFAULT 0,
            h3_count           INTEGER NOT NULL DEFAULT 0,
            h4_count           INTEGER NOT NULL DEFAULT 0,
            general_count      INTEGER NOT NULL DEFAULT 0,
            outcome            TEXT,
            annotated_at       TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (session_kind, session_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sa_project "
        "ON session_annotations(project_id, annotated_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sa_primary_layer ON session_annotations(primary_layer)"
    )
