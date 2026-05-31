"""Phase E2 Task 3 — ``input_kg_signals_json`` round column + persist.

Covers the fresh-schema default, ``start_round`` persistence, the new
``_ensure_kg_signals_column`` ensure link (idempotent + C1 recreate-path
preservation), and the v07 migration-143 ALTER.
"""

import json

from app.database import get_connection
from app.db import harness_evolution as evo


def _seed_project(project_id="p"):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, status) VALUES (?, 'P', 'active')", (project_id,)
        )
        conn.commit()


def test_fresh_schema_defaults_empty_list(isolated_db):
    """A fresh schema's round table carries ``input_kg_signals_json`` defaulting '[]'."""
    _seed_project("pm")
    with get_connection() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(harness_evolution_rounds)")}
        assert "input_kg_signals_json" in cols
        conn.execute(
            "INSERT INTO harness_evolution_rounds (id, project_id, status) "
            "VALUES ('r1', 'pm', 'pending')"
        )
        conn.commit()
        row = conn.execute(
            "SELECT input_kg_signals_json FROM harness_evolution_rounds WHERE id='r1'"
        ).fetchone()
    assert row["input_kg_signals_json"] == "[]"


def test_start_round_persists_kg_signals(isolated_db):
    _seed_project("pm")
    rid = evo.start_round(
        project_id="pm",
        input_window_since=None,
        input_window_until=None,
        input_execution_count=0,
        input_forge={},
        input_kg_signals=[{"x": 1}],
    )
    with get_connection() as conn:
        row = conn.execute(
            "SELECT input_kg_signals_json FROM harness_evolution_rounds WHERE id=?", (rid,)
        ).fetchone()
    assert json.loads(row["input_kg_signals_json"]) == [{"x": 1}]


def test_start_round_without_param_defaults_empty(isolated_db):
    _seed_project("pm")
    rid = evo.start_round(
        project_id="pm",
        input_window_since=None,
        input_window_until=None,
        input_execution_count=0,
        input_forge={},
    )
    with get_connection() as conn:
        row = conn.execute(
            "SELECT input_kg_signals_json FROM harness_evolution_rounds WHERE id=?", (rid,)
        ).fetchone()
    assert row["input_kg_signals_json"] == "[]"


def test_ensure_kg_signals_column_idempotent(isolated_db):
    """Build an old-shape table lacking the column; ensure adds it, twice is safe."""
    with get_connection() as conn:
        conn.execute("DROP TABLE harness_evolution_rounds")
        # old-shape: modern CHECK (has 'evaluating') so no recreate fires,
        # but the new KG column is absent.
        conn.execute(
            """CREATE TABLE harness_evolution_rounds (
                   id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                   started_at TEXT NOT NULL DEFAULT (datetime('now')), finished_at TEXT,
                   status TEXT NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending','running','evaluating','awaiting_approval',
                                         'applied','eval_failed','failed','aborted','reverted')),
                   input_window_since TEXT, input_window_until TEXT,
                   input_execution_count INTEGER NOT NULL DEFAULT 0,
                   input_forge_json TEXT NOT NULL DEFAULT '{}', output_patch_json TEXT,
                   applied_asset_ids_json TEXT NOT NULL DEFAULT '[]',
                   error_message TEXT, notes TEXT, scratch_dir TEXT)"""
        )
        conn.commit()
        evo._ensure_kg_signals_column(conn)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(harness_evolution_rounds)")}
        assert "input_kg_signals_json" in cols
        evo._ensure_kg_signals_column(conn)  # idempotent — no error
        conn.commit()


def test_c1_recreate_preserves_kg_signals(isolated_db):
    """Old CHECK (no 'evaluating') but WITH the KG column populated → the
    table-recreate must allow 'evaluating' AND keep the column's value.

    This proves ``input_kg_signals_json`` is in ``_ROUND_COLUMNS_IN_ORDER``;
    if it weren't, the SELECT-copy would silently drop the value.
    """
    with get_connection() as conn:
        conn.execute("DROP TABLE harness_evolution_rounds")
        conn.execute(
            """CREATE TABLE harness_evolution_rounds (
                   id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                   started_at TEXT NOT NULL DEFAULT (datetime('now')), finished_at TEXT,
                   status TEXT NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending','running','awaiting_approval',
                                         'applied','failed','aborted')),
                   input_window_since TEXT, input_window_until TEXT,
                   input_execution_count INTEGER NOT NULL DEFAULT 0,
                   input_forge_json TEXT NOT NULL DEFAULT '{}',
                   input_kg_signals_json TEXT NOT NULL DEFAULT '[]',
                   output_patch_json TEXT,
                   applied_asset_ids_json TEXT NOT NULL DEFAULT '[]',
                   error_message TEXT, notes TEXT, scratch_dir TEXT)"""
        )
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pm', 'P', 'active')")
        conn.execute(
            "INSERT INTO harness_evolution_rounds "
            "(id, project_id, status, input_kg_signals_json) "
            "VALUES ('r-old', 'pm', 'applied', ?)",
            (json.dumps([{"sig": "keep-me"}]),),
        )
        conn.commit()
        evo._ensure_kg_signals_column(conn)
        conn.commit()
    row = evo.get_round("r-old")
    assert row is not None and row["status"] == "applied"
    with get_connection() as conn:
        kept = conn.execute(
            "SELECT input_kg_signals_json FROM harness_evolution_rounds WHERE id='r-old'"
        ).fetchone()["input_kg_signals_json"]
    assert json.loads(kept) == [{"sig": "keep-me"}]
    # And the recreate widened the CHECK so 'evaluating' is now allowed.
    rid = evo.start_round(
        project_id="pm",
        input_window_since=None,
        input_window_until=None,
        input_execution_count=0,
        input_forge={},
    )
    evo.mark_running(rid)
    evo.mark_evaluating(rid)
    assert evo.get_round(rid)["status"] == "evaluating"


def test_migration_143_adds_column_idempotent(isolated_db):
    """The v07 migration body adds the column on an old DB and is idempotent."""
    from app.db.migrations.v07_features import _migrate_143_round_kg_signals_col

    with get_connection() as conn:
        conn.execute("DROP TABLE harness_evolution_rounds")
        conn.execute(
            """CREATE TABLE harness_evolution_rounds (
                   id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                   status TEXT NOT NULL DEFAULT 'pending',
                   input_forge_json TEXT NOT NULL DEFAULT '{}')"""
        )
        conn.commit()
        _migrate_143_round_kg_signals_col(conn)
        _migrate_143_round_kg_signals_col(conn)  # idempotent
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(harness_evolution_rounds)")}
    assert "input_kg_signals_json" in cols
