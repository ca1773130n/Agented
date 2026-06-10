"""Incremental checkpointing on ExecutionLogService — Phase 1 (P2).

Converts fire-and-forget runs into recoverable ones: a throttled
``checkpoint()`` persists the externalized log ledger mid-run, and the
periodic stale sweep now tombstones the abandoned DB row instead of
leaving it ``running`` forever. See docs/research/harness-1-integration.md.
"""

import datetime

from app.db import harness_state
from app.db.execution_logs import get_execution_log
from app.services.execution_log_service import ExecutionLogService


def _start() -> str:
    return ExecutionLogService.start_execution(
        trigger_id="bot-pr-review",
        trigger_type="manual",
        prompt="p",
        backend_type="claude",
        command="echo hi",
    )


def test_checkpoint_persists_run_state_without_finalizing():
    eid = _start()
    ExecutionLogService.append_log(eid, "stdout", "line one")
    ExecutionLogService.append_log(eid, "stderr", "warn")

    step = ExecutionLogService.checkpoint(eid)
    assert step == 1

    run = harness_state.get_run(eid)
    assert run is not None and run["step_cursor"] == 1

    # The execution itself is NOT finalized by a checkpoint.
    row = get_execution_log(eid)
    assert row["status"] == "running"
    assert row["finished_at"] is None

    # The ledger captured the buffered lines.
    cp = harness_state.get_latest_checkpoint(eid)
    contents = [line["content"] for line in cp["ledger"]["lines"]]
    assert "line one" in contents
    assert "warn" in contents


def test_append_log_auto_checkpoints_every_n_lines():
    eid = _start()
    n = ExecutionLogService._CHECKPOINT_EVERY_N_LINES
    for i in range(n):
        ExecutionLogService.append_log(eid, "stdout", f"line {i}")
    run = harness_state.get_run(eid)
    assert run is not None and run["step_cursor"] >= 1


def test_simulated_crash_leaves_recoverable_checkpoint():
    """Stream enough logs to auto-checkpoint, then drop the in-memory buffers
    as if the process crashed — never calling finish_execution. The
    externalized state must survive and be deserializable."""
    eid = _start()
    n = ExecutionLogService._CHECKPOINT_EVERY_N_LINES
    for i in range(n):
        ExecutionLogService.append_log(eid, "stdout", f"out {i}")

    with ExecutionLogService._lock:
        ExecutionLogService._log_buffers.pop(eid, None)
        ExecutionLogService._start_times.pop(eid, None)

    run = harness_state.get_run(eid)
    assert run is not None and run["step_cursor"] >= 1
    cp = harness_state.get_latest_checkpoint(eid)
    assert cp is not None and "lines" in cp["ledger"]


def test_finish_execution_marks_run_state_terminal():
    eid = _start()
    ExecutionLogService.append_log(eid, "stdout", "x")
    ExecutionLogService.checkpoint(eid)
    ExecutionLogService.finish_execution(eid, status="success", exit_code=0)
    assert harness_state.get_run(eid)["status"] == "success"


def test_cleanup_stale_executions_tombstones_db_row():
    """Previously the periodic sweep only dropped in-memory buffers, leaving a
    crashed run as status='running' with NULL output forever. It must now mark
    the DB row failed and preserve whatever output was buffered."""
    eid = _start()
    ExecutionLogService.append_log(eid, "stdout", "partial output")

    # Backdate the start time so the sweep treats it as stale.
    past = datetime.datetime.now() - datetime.timedelta(days=1)
    with ExecutionLogService._lock:
        ExecutionLogService._start_times[eid] = past

    cleaned = ExecutionLogService.cleanup_stale_executions()
    assert cleaned >= 1

    row = get_execution_log(eid)
    assert row["status"] == "failed"
    assert row["finished_at"] is not None
    assert "partial output" in (row["stdout_log"] or "")


def test_checkpoints_store_deltas_not_cumulative_buffer():
    """Each checkpoint must hold only the lines added since the previous one,
    not re-serialize the whole buffer — otherwise storage and serialization
    are quadratic in log length and stall the streaming path (codex P2)."""
    eid = _start()
    n = ExecutionLogService._CHECKPOINT_EVERY_N_LINES
    for i in range(2 * n):
        ExecutionLogService.append_log(eid, "stdout", f"line {i}")

    cps = harness_state.list_checkpoints(eid)
    assert len(cps) == 2  # auto-checkpoints fired at n and 2n
    # Each checkpoint holds only its delta slice, never the cumulative buffer.
    assert all(len(cp["ledger"]["lines"]) == n for cp in cps)
    # Concatenating deltas reconstructs the full ledger with no duplication.
    assert sum(len(cp["ledger"]["lines"]) for cp in cps) == 2 * n


def test_stale_cleanup_does_not_clobber_completed_run_state():
    """If stale cleanup races with normal completion, the CAS on
    execution_logs fails (already terminal) — and the durable harness_runs
    row must NOT then be flipped to 'failed', which would disagree with the
    completed execution (codex P2)."""
    from app.db.execution_logs import update_execution_log

    eid = _start()
    ExecutionLogService.append_log(eid, "stdout", "out")
    ExecutionLogService.checkpoint(eid)

    # Simulate finish having completed the execution + run-state concurrently...
    update_execution_log(eid, status="success", finished_at="2026-06-10T00:00:01")
    harness_state.mark_run_status(eid, "success")
    # ...while a stale start-time entry still lingers (the race window).
    past = datetime.datetime.now() - datetime.timedelta(days=1)
    with ExecutionLogService._lock:
        ExecutionLogService._start_times[eid] = past

    ExecutionLogService.cleanup_stale_executions()

    # CAS failed (already 'success'), so neither table may be flipped to failed.
    assert ExecutionLogService.get_execution(eid)["status"] == "success"
    assert harness_state.get_run(eid)["status"] == "success"
