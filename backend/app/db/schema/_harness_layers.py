"""Life-Harness T2 — harness_layers DDL.

One row per intervention. Rows compose into a per-bot harness via
``HarnessBuildService.build_for(bot_id, harness_kind)``.

Why rows-not-blobs:
    Evolution (T3) needs to add / disable / re-version individual interventions
    atomically. A monolithic JSON blob would force every evolution edit to
    rewrite the whole document and lose the audit trail.

Versioning model:
    ``version`` is a monotonic counter scoped to a logical layer name. A new
    iteration of the same intervention writes a fresh row, copies the prior
    row's id into ``parent_layer_id``, increments ``version``, and disables
    the parent. Rollback is just flipping ``enabled``.

FK note:
    No hard FK on ``bot_id`` — Agented's bot-id space spans predefined static
    IDs (e.g. ``bot-security``) and user-created rows, and the schema bundles
    here intentionally avoid cycles. Application code is the source of truth.
"""

from __future__ import annotations


def create_harness_layer_tables(conn) -> None:
    """Create the harness_layers table on a fresh DB. Idempotent."""

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS harness_layers (
            id               TEXT    PRIMARY KEY,
            bot_id           TEXT    NOT NULL,
            trigger_id       TEXT,
            layer            TEXT    NOT NULL
                             CHECK (layer IN ('h2', 'h3', 'h4', 'h5')),
            name             TEXT    NOT NULL,
            enabled          INTEGER NOT NULL DEFAULT 1,
            version          INTEGER NOT NULL DEFAULT 1,
            parent_layer_id  TEXT,
            source_kind      TEXT    NOT NULL DEFAULT 'manual'
                             CHECK (source_kind IN ('manual', 'template', 'evolved')),
            payload_json     TEXT    NOT NULL DEFAULT '{}',
            created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at       TEXT    NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_hl_bot_layer_enabled "
        "ON harness_layers(bot_id, layer, enabled)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_hl_trigger ON harness_layers(trigger_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_hl_parent ON harness_layers(parent_layer_id)"
    )
