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
