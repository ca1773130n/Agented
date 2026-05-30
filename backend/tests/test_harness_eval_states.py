import pytest
from app.database import get_connection
from app.db import harness_evolution as evo


def _seed_round(project_id="p"):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, status) VALUES (?, 'P', 'active')", (project_id,)
        )
        conn.commit()
    return evo.start_round(
        project_id=project_id,
        input_window_since=None,
        input_window_until=None,
        input_execution_count=0,
        input_forge={},
        scratch_dir="/tmp/x",
    )


def test_evaluating_state_allowed(isolated_db):
    rid = _seed_round()
    evo.mark_running(rid)
    evo.mark_evaluating(rid)
    assert evo.get_round(rid)["status"] == "evaluating"


def test_eval_failed_is_terminal(isolated_db):
    from app.models.harness_evolution import EvalVerdict, CheckResult

    rid = _seed_round()
    evo.mark_running(rid)
    evo.mark_evaluating(rid)
    verdict = EvalVerdict(
        passed=False,
        score=0.2,
        per_check=[CheckResult(name="static", passed=False, detail="bad")],
    )
    evo.mark_eval_failed(rid, verdict=verdict)
    row = evo.get_round(rid)
    assert row["status"] == "eval_failed"
    assert row["eval_verdict"]["passed"] is False


def test_migration_recreates_table_for_old_check(isolated_db):
    with get_connection() as conn:
        conn.execute("DROP TABLE harness_evolution_rounds")
        conn.execute(
            """CREATE TABLE harness_evolution_rounds (
                   id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                   started_at TEXT NOT NULL DEFAULT (datetime('now')), finished_at TEXT,
                   status TEXT NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending','running','awaiting_approval','applied','failed','aborted')),
                   input_window_since TEXT, input_window_until TEXT,
                   input_execution_count INTEGER NOT NULL DEFAULT 0,
                   input_forge_json TEXT NOT NULL DEFAULT '{}', output_patch_json TEXT,
                   applied_asset_ids_json TEXT NOT NULL DEFAULT '[]',
                   error_message TEXT, notes TEXT, scratch_dir TEXT)"""
        )
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pm', 'P', 'active')")
        conn.execute(
            "INSERT INTO harness_evolution_rounds (id, project_id, status) VALUES ('r-old', 'pm', 'applied')"
        )
        conn.commit()
        evo._ensure_eval_columns(conn)
        conn.commit()
    row = evo.get_round("r-old")
    assert row is not None and row["status"] == "applied"
    rid = _seed_round("pm2")
    evo.mark_running(rid)
    evo.mark_evaluating(rid)
    assert evo.get_round(rid)["status"] == "evaluating"
