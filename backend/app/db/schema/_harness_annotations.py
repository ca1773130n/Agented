"""Life-Harness failure-annotation DDL (T1).

Two tables back the four-layer failure observability surface:

- ``execution_layer_incidents`` — one row per detected interface incident.
  Layers follow the paper's priority order: H2 (Action Realization), H3
  (Environment Contract), H4 (Trajectory Regulation), then ``general`` as a
  catch-all when an execution failed but no layer fired.
- ``execution_annotations`` — denormalized per-execution roll-up that the
  Activity-lane execution-inspector tile reads on render. Recomputed by the
  annotator whenever incidents are (re)written.

Reference: arXiv 2605.22166 Appendix A.1 (Failure Annotation Protocol).

Register from ``schema/__init__.py``::

    from ._harness_annotations import create_harness_annotation_tables
    ...
    create_harness_annotation_tables(conn)

And add a matching ``CREATE TABLE IF NOT EXISTS`` block to the current
``migrations/v0X_features.py`` so existing installs pick it up.
"""

from __future__ import annotations


def create_harness_annotation_tables(conn) -> None:
    """Create Life-Harness annotation tables on a fresh DB. Idempotent."""

    # Per-incident detail.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS execution_layer_incidents (
            id                TEXT    PRIMARY KEY,
            execution_id      TEXT    NOT NULL,
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
        "CREATE INDEX IF NOT EXISTS idx_eli_execution_id "
        "ON execution_layer_incidents(execution_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_eli_layer ON execution_layer_incidents(layer)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_eli_kind ON execution_layer_incidents(kind)"
    )

    # Per-execution roll-up. Recomputed; not append-only.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS execution_annotations (
            execution_id       TEXT PRIMARY KEY,
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
            annotated_at       TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ea_primary_layer "
        "ON execution_annotations(primary_layer)"
    )
