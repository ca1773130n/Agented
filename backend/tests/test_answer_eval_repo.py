"""TDD tests for answer_eval store (migration 154)."""

import sqlite3

import pytest

from app.db import answer_eval

# ---------------------------------------------------------------------------
# Migration registration
# ---------------------------------------------------------------------------


def test_migration_154_registered():
    from app.db.migrations import VERSIONED_MIGRATIONS

    versions = {v for (v, _n, _f) in VERSIONED_MIGRATIONS}
    names = {n for (_v, n, _f) in VERSIONED_MIGRATIONS}
    assert 154 in versions
    assert "answer_eval" in names


# ---------------------------------------------------------------------------
# Fresh-schema DDL — all three tables present
# ---------------------------------------------------------------------------


def test_fresh_schema_has_answer_eval_tables():
    import sqlite3 as _sqlite3

    from app.db.schema import create_fresh_schema

    conn = _sqlite3.connect(":memory:")
    conn.row_factory = _sqlite3.Row
    create_fresh_schema(conn)
    tables = {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    # migration 153 also covered here
    assert "extracted_facts" in tables
    assert "answer_eval_runs" in tables
    assert "answer_eval_results" in tables


# ---------------------------------------------------------------------------
# create_run → record_result × 2 arms → finalize_run
# ---------------------------------------------------------------------------


def test_create_run_returns_int():
    run_id = answer_eval.create_run("proj-1", judge_backend="claude")
    assert isinstance(run_id, int)
    assert run_id > 0


def test_run_lifecycle_full():
    run_id = answer_eval.create_run("proj-2", judge_backend="claude")

    r1 = answer_eval.record_result(
        run_id,
        question="What is X?",
        arm="baseline",
        answer_text="X is Y.",
        scores={"groundedness": 0.7, "sufficiency": 0.6, "quality": 0.8},
        judge_reason="looks ok",
        tokens=100,
        cost_usd=0.001,
    )
    r2 = answer_eval.record_result(
        run_id,
        question="What is X?",
        arm="pipeline",
        answer_text="X is Y with sources.",
        scores={"groundedness": 0.9, "sufficiency": 0.85, "quality": 0.9},
        judge_reason="well grounded",
        tokens=150,
        cost_usd=0.0015,
    )
    assert r1 > 0
    assert r2 > 0

    ok = answer_eval.finalize_run(
        run_id,
        aggregates={
            "baseline_groundedness": 0.7,
            "baseline_sufficiency": 0.6,
            "baseline_quality": 0.8,
            "pipeline_groundedness": 0.9,
            "pipeline_sufficiency": 0.85,
            "pipeline_quality": 0.9,
            "delta_groundedness": 0.2,
            "delta_sufficiency": 0.25,
            "delta_quality": 0.1,
        },
    )
    assert ok is True

    run = answer_eval.get_run(run_id)
    assert run is not None
    assert run["status"] == "complete"
    assert run["finished_at"] is not None
    assert run["delta_groundedness"] == pytest.approx(0.2)
    assert run["pipeline_quality"] == pytest.approx(0.9)

    results = answer_eval.list_results(run_id)
    assert len(results) == 2
    arms = {r["arm"] for r in results}
    assert arms == {"baseline", "pipeline"}


# ---------------------------------------------------------------------------
# list_results
# ---------------------------------------------------------------------------


def test_list_results_empty_for_unknown_run():
    assert answer_eval.list_results(999999) == []


# ---------------------------------------------------------------------------
# list_runs
# ---------------------------------------------------------------------------


def test_list_runs_no_filter():
    answer_eval.create_run("proj-lr1", judge_backend="claude")
    answer_eval.create_run("proj-lr2", judge_backend="claude")
    runs = answer_eval.list_runs()
    assert len(runs) >= 2


def test_list_runs_project_filter():
    answer_eval.create_run("proj-filt", judge_backend="claude")
    answer_eval.create_run("proj-other", judge_backend="claude")
    runs = answer_eval.list_runs(project_id="proj-filt")
    assert all(r["project_id"] == "proj-filt" for r in runs)
    assert len(runs) >= 1


# ---------------------------------------------------------------------------
# CHECK constraint: bad arm rejected
# ---------------------------------------------------------------------------


def test_record_result_rejects_bad_arm():
    run_id = answer_eval.create_run("proj-chk", judge_backend="claude")
    with pytest.raises(sqlite3.IntegrityError):
        answer_eval.record_result(
            run_id,
            question="Q?",
            arm="invalid_arm",
            answer_text="A",
            scores={},
            judge_reason=None,
            tokens=None,
            cost_usd=None,
        )


# ---------------------------------------------------------------------------
# FK cascade: deleting run removes results
# ---------------------------------------------------------------------------


def test_fk_cascade_run_delete_removes_results():
    from app.db.connection import get_connection

    run_id = answer_eval.create_run("proj-fk", judge_backend="claude")
    answer_eval.record_result(
        run_id,
        question="Q?",
        arm="baseline",
        answer_text="A",
        scores={"groundedness": 0.5, "sufficiency": 0.5, "quality": 0.5},
        judge_reason=None,
        tokens=None,
        cost_usd=None,
    )
    assert len(answer_eval.list_results(run_id)) == 1

    with get_connection() as conn:
        conn.execute("DELETE FROM answer_eval_runs WHERE id = ?", (run_id,))
        conn.commit()

    assert answer_eval.list_results(run_id) == []
