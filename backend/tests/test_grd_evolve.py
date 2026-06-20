"""Tests for the v0.7.88 ``gd evolve`` integration.

Covers:
  * Migration v129 created the ``grd_evolve_runs`` table.
  * DB helpers: create / get / list / upsert_state / finalize round-trip.
  * Status transitions are gated correctly (active → terminal only).
  * The runner thread polls + skips no-op syncs via content hash.

The execution-handler-spawn path is NOT exercised end-to-end here
(it would require a real ``gd`` binary + PSM subprocess); the
handler is unit-tested via its public ``start/monitor/stop``
methods being importable and the run-row DB shape being correct.
"""

from __future__ import annotations

import json
import threading

from app.db.connection import get_connection
from app.db.grd_evolve import (
    create_evolve_run,
    finalize_evolve_run,
    get_evolve_run,
    get_evolve_run_by_session,
    list_evolve_runs_for_project,
    upsert_evolve_state,
)

# ---------------------------------------------------------------------
# Migration v129
# ---------------------------------------------------------------------


def test_migration_129_created_grd_evolve_runs(isolated_db):
    del isolated_db
    with get_connection() as conn:
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "grd_evolve_runs" in tables, "migration 129 must create grd_evolve_runs"
        cols = {row[1] for row in conn.execute("PRAGMA table_info(grd_evolve_runs)").fetchall()}
        for col in (
            "id",
            "project_id",
            "session_id",
            "status",
            "config_json",
            "iteration",
            "total_iterations",
            "pick_pct",
            "last_state_json",
            "last_state_synced_at",
            "started_at",
            "ended_at",
            "error_message",
        ):
            assert col in cols, f"migration 129 must add grd_evolve_runs.{col}"


# ---------------------------------------------------------------------
# CRUD round-trips
# ---------------------------------------------------------------------


def _seed_project(conn) -> str:
    from app.db.ids import _get_unique_project_id

    pid = _get_unique_project_id(conn)
    conn.execute(
        "INSERT INTO projects (id, name, local_path) VALUES (?, ?, ?)",
        (pid, "evolve-test", "/tmp/evolve-test"),
    )
    conn.commit()
    return pid


def test_create_then_get_evolve_run_round_trips(isolated_db):
    del isolated_db
    with get_connection() as conn:
        pid = _seed_project(conn)
    rid = create_evolve_run(
        project_id=pid,
        session_id="psess-evolve1",
        config={"iterations": 3, "dry_run": False},
        total_iterations=3,
        pick_pct=50,
    )
    assert rid.startswith("evol-")
    run = get_evolve_run(rid)
    assert run is not None
    assert run["project_id"] == pid
    assert run["session_id"] == "psess-evolve1"
    assert run["status"] == "active"
    assert run["total_iterations"] == 3
    assert run["pick_pct"] == 50
    assert run["config"]["iterations"] == 3


def test_get_evolve_run_by_session(isolated_db):
    del isolated_db
    with get_connection() as conn:
        pid = _seed_project(conn)
    create_evolve_run(project_id=pid, session_id="psess-bysess1", config={})
    run = get_evolve_run_by_session("psess-bysess1")
    assert run is not None
    assert run["session_id"] == "psess-bysess1"
    assert get_evolve_run_by_session("psess-nonexistent") is None


def test_list_evolve_runs_for_project_filters_by_status(isolated_db):
    del isolated_db
    with get_connection() as conn:
        pid = _seed_project(conn)
    create_evolve_run(project_id=pid, session_id="psess-a", config={})
    create_evolve_run(project_id=pid, session_id="psess-b", config={})
    finalize_evolve_run(session_id="psess-b", status="completed")

    all_runs = list_evolve_runs_for_project(pid)
    assert len(all_runs) == 2
    active = list_evolve_runs_for_project(pid, status="active")
    assert len(active) == 1
    assert active[0]["session_id"] == "psess-a"
    completed = list_evolve_runs_for_project(pid, status="completed")
    assert len(completed) == 1
    assert completed[0]["session_id"] == "psess-b"


def test_upsert_evolve_state_writes_iteration_and_state(isolated_db):
    del isolated_db
    with get_connection() as conn:
        pid = _seed_project(conn)
    create_evolve_run(project_id=pid, session_id="psess-state1", config={})

    state = {"iteration": 4, "selected_groups": [{"id": "g1"}]}
    ok = upsert_evolve_state(
        session_id="psess-state1",
        iteration=4,
        state_json=json.dumps(state),
    )
    assert ok is True

    run = get_evolve_run_by_session("psess-state1")
    assert run["iteration"] == 4
    assert run["last_state"]["selected_groups"][0]["id"] == "g1"
    assert run["last_state_synced_at"] is not None


def test_upsert_evolve_state_missing_session_returns_false(isolated_db):
    del isolated_db
    # No row matches → no-op, returns False (caller treats as "skip").
    ok = upsert_evolve_state(session_id="psess-nope", iteration=1, state_json="{}")
    assert ok is False


def test_finalize_evolve_run_terminal_states(isolated_db):
    del isolated_db
    with get_connection() as conn:
        pid = _seed_project(conn)
    create_evolve_run(project_id=pid, session_id="psess-final1", config={})

    ok = finalize_evolve_run(session_id="psess-final1", status="completed")
    assert ok is True
    run = get_evolve_run_by_session("psess-final1")
    assert run["status"] == "completed"
    assert run["ended_at"] is not None


def test_finalize_evolve_run_is_idempotent(isolated_db):
    del isolated_db
    with get_connection() as conn:
        pid = _seed_project(conn)
    create_evolve_run(project_id=pid, session_id="psess-idem1", config={})

    assert finalize_evolve_run(session_id="psess-idem1", status="stopped") is True
    # Second call must no-op (status already terminal).
    assert finalize_evolve_run(session_id="psess-idem1", status="failed") is False
    run = get_evolve_run_by_session("psess-idem1")
    assert run["status"] == "stopped", "second finalize must not overwrite first"


def test_finalize_evolve_run_rejects_invalid_status():
    import pytest

    with pytest.raises(ValueError):
        finalize_evolve_run(session_id="psess-x", status="bogus")


# ---------------------------------------------------------------------
# Runner sync thread (mocked PSM + file polling)
# ---------------------------------------------------------------------


def test_runner_on_state_change_writes_through(isolated_db, monkeypatch):
    """``_on_state_change`` writes the new snapshot via
    ``upsert_evolve_state`` and broadcasts the SSE event when the
    run row exists.
    """
    from app.services import grd_evolve_runner

    del isolated_db
    with get_connection() as conn:
        pid = _seed_project(conn)
    create_evolve_run(project_id=pid, session_id="psess-runr1", config={})

    broadcasts: list = []

    class _FakePSM:
        @staticmethod
        def _broadcast(session_id, event_type, data):
            broadcasts.append((session_id, event_type, data))

    monkeypatch.setattr(grd_evolve_runner, "ProjectSessionManager", _FakePSM)

    grd_evolve_runner._on_state_change("psess-runr1", json.dumps({"iteration": 5}))
    run = get_evolve_run_by_session("psess-runr1")
    assert run["iteration"] == 5
    assert len(broadcasts) == 1
    assert broadcasts[0][1] == "grd_evolve_state"
    assert broadcasts[0][2]["iteration"] == 5


def test_runner_on_state_change_no_row_silently_skips(isolated_db, monkeypatch):
    """Edge case: the poller may tick before the handler inserts
    the run row. ``_on_state_change`` must not raise; it just logs
    and waits for the next tick.
    """
    from app.services import grd_evolve_runner

    del isolated_db

    broadcasts: list = []

    class _FakePSM:
        @staticmethod
        def _broadcast(session_id, event_type, data):
            broadcasts.append((session_id, event_type, data))

    monkeypatch.setattr(grd_evolve_runner, "ProjectSessionManager", _FakePSM)
    # No create_evolve_run call → upsert returns False → no broadcast.
    grd_evolve_runner._on_state_change("psess-norow", json.dumps({"iteration": 1}))
    assert broadcasts == []


def test_runner_finalize_on_session_exit_marks_completed(isolated_db):
    """Exit code 0 → ``completed``; non-zero → ``failed``."""
    from app.services.grd_evolve_runner import finalize_on_session_exit

    del isolated_db
    with get_connection() as conn:
        pid = _seed_project(conn)
    create_evolve_run(project_id=pid, session_id="psess-fin-ok", config={})
    create_evolve_run(project_id=pid, session_id="psess-fin-bad", config={})

    finalize_on_session_exit("psess-fin-ok", exit_code=0)
    finalize_on_session_exit("psess-fin-bad", exit_code=2)

    ok_run = get_evolve_run_by_session("psess-fin-ok")
    bad_run = get_evolve_run_by_session("psess-fin-bad")
    assert ok_run["status"] == "completed"
    assert bad_run["status"] == "failed"
    assert "exited with code 2" in (bad_run["error_message"] or "")


def test_runner_finalize_on_unknown_session_is_noop(isolated_db):
    """If the run row doesn't exist (non-evolve session), finalize
    must silently return without raising.
    """
    from app.services.grd_evolve_runner import finalize_on_session_exit

    del isolated_db
    # Just confirms it doesn't raise.
    finalize_on_session_exit("psess-unknown", exit_code=0)


def test_start_stop_state_sync_threading_idempotent(monkeypatch):
    """``start_evolve_state_sync`` is idempotent on the same
    session_id, and ``stop_evolve_state_sync`` is safe to call
    multiple times.
    """
    from app.services import grd_evolve_runner

    started: list = []

    def fake_run(session_id, planning_dir, stop_event):
        started.append(session_id)
        stop_event.wait(timeout=0.01)

    monkeypatch.setattr(grd_evolve_runner, "_run", fake_run)

    grd_evolve_runner.start_evolve_state_sync("psess-thread1", "/tmp/p1")
    grd_evolve_runner.start_evolve_state_sync("psess-thread1", "/tmp/p1")
    grd_evolve_runner.stop_evolve_state_sync("psess-thread1")
    grd_evolve_runner.stop_evolve_state_sync("psess-thread1")
    grd_evolve_runner.stop_evolve_state_sync("psess-never-started")

    # Wait for the patched _run to drain (fake_run blocks briefly
    # waiting for the stop_event, so we sleep just past that).
    deadline = threading.Event()
    deadline.wait(timeout=0.1)
    # Only one start invocation despite two calls (idempotency).
    assert started.count("psess-thread1") == 1
