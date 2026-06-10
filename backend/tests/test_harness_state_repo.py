"""Durable harness run-state store — Phase 1 (P1) of the Harness-1 integration.

State-externalizing harness foundation: a per-execution run-state row
(``harness_runs``) plus an append-only checkpoint ledger
(``harness_checkpoints``), both FK'd to ``execution_logs(execution_id)``.
See docs/research/harness-1-integration.md (P1); arXiv:2606.02373.
"""

import pytest

from app.db import harness_state
from app.db.connection import get_connection


def _make_execution(execution_id: str = "exec-hs-1") -> None:
    """Insert a minimal execution_logs row so the FK target exists."""
    from app.db.execution_logs import create_execution_log

    create_execution_log(
        execution_id=execution_id,
        trigger_id="bot-pr-review",
        trigger_type="manual",
        started_at="2026-06-10T00:00:00",
        prompt="p",
        backend_type="claude",
        command="echo hi",
    )


def test_record_checkpoint_creates_run_and_checkpoint():
    _make_execution()
    step = harness_state.record_checkpoint("exec-hs-1", ledger={"lines": ["a", "b"]})
    assert step == 1

    run = harness_state.get_run("exec-hs-1")
    assert run is not None
    assert run["step_cursor"] == 1
    assert run["status"] == "running"

    cp = harness_state.get_latest_checkpoint("exec-hs-1")
    assert cp["step"] == 1
    assert cp["ledger"] == {"lines": ["a", "b"]}


def test_record_checkpoint_increments_cursor_and_returns_latest():
    _make_execution()
    harness_state.record_checkpoint("exec-hs-1", ledger={"n": 1})
    step2 = harness_state.record_checkpoint("exec-hs-1", ledger={"n": 2})
    assert step2 == 2

    assert harness_state.get_run("exec-hs-1")["step_cursor"] == 2
    latest = harness_state.get_latest_checkpoint("exec-hs-1")
    assert latest["step"] == 2
    assert latest["ledger"] == {"n": 2}
    assert len(harness_state.list_checkpoints("exec-hs-1")) == 2


def test_get_run_and_checkpoint_none_for_unknown_execution():
    assert harness_state.get_run("nope") is None
    assert harness_state.get_latest_checkpoint("nope") is None
    assert harness_state.list_checkpoints("nope") == []


def test_budget_used_is_set_when_provided_and_kept_when_omitted():
    _make_execution()
    harness_state.record_checkpoint("exec-hs-1", ledger={}, budget_used=0.10)
    assert harness_state.get_run("exec-hs-1")["budget_used"] == pytest.approx(0.10)
    harness_state.record_checkpoint("exec-hs-1", ledger={}, budget_used=0.30)
    assert harness_state.get_run("exec-hs-1")["budget_used"] == pytest.approx(0.30)
    harness_state.record_checkpoint("exec-hs-1", ledger={})  # None -> keep
    assert harness_state.get_run("exec-hs-1")["budget_used"] == pytest.approx(0.30)


def test_mark_run_status():
    _make_execution()
    harness_state.record_checkpoint("exec-hs-1", ledger={})
    assert harness_state.mark_run_status("exec-hs-1", "finished") is True
    assert harness_state.get_run("exec-hs-1")["status"] == "finished"


def test_fk_cascade_delete_removes_run_and_checkpoints():
    _make_execution()
    harness_state.record_checkpoint("exec-hs-1", ledger={"x": 1})
    with get_connection() as conn:
        conn.execute("DELETE FROM execution_logs WHERE execution_id = ?", ("exec-hs-1",))
        conn.commit()
    assert harness_state.get_run("exec-hs-1") is None
    assert harness_state.list_checkpoints("exec-hs-1") == []


def test_create_tables_idempotent():
    from app.db.schema._harness_state import create_harness_state_tables

    with get_connection() as conn:
        create_harness_state_tables(conn)
        create_harness_state_tables(conn)  # second call must not raise
        conn.commit()
        tables = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert {"harness_runs", "harness_checkpoints"} <= tables


def test_migration_148_registered():
    from app.db.migrations import VERSIONED_MIGRATIONS

    versions = {v for (v, _n, _f) in VERSIONED_MIGRATIONS}
    names = {n for (_v, n, _f) in VERSIONED_MIGRATIONS}
    assert 148 in versions
    assert "harness_state" in names
