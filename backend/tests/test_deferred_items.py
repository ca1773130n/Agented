"""Regression tests for the previously-deferred lower-priority items."""


def test_start_execution_accepts_preallocated_id(isolated_db):
    # 06 L1: a caller can pre-allocate the execution_id so a background runner
    # is trackable immediately instead of racing a thread.join.
    from app.db.triggers import create_trigger
    from app.services.execution_log_service import ExecutionLogService

    tid = create_trigger(name="t", prompt_template="x", backend_type="claude")
    eid = ExecutionLogService.start_execution(
        trigger_id=tid,
        trigger_type="manual",
        prompt="p",
        backend_type="claude",
        command="c",
        execution_id="exec-preallocated-1",
    )
    assert eid == "exec-preallocated-1"


def test_workflow_group_runner_runs_and_kills(monkeypatch):
    import subprocess

    from app.services.workflow_node_executor import _run_in_process_group

    # Fast command: returns a CompletedProcess with captured output.
    result = _run_in_process_group(["printf", "hi"], timeout=10)
    assert result.returncode == 0
    assert "hi" in result.stdout

    # A command that exceeds the timeout raises TimeoutExpired (group killed).
    import pytest

    with pytest.raises(subprocess.TimeoutExpired):
        _run_in_process_group(["sleep", "5"], timeout=0.3)


def test_team_monitor_config_broadcast_is_mtime_gated(tmp_path, monkeypatch):
    # 06 M4: the shared helper broadcasts at most once per mtime, so the
    # watchdog handler and polling loop never double-broadcast the same change.
    from app.services.team_monitor_service import TeamMonitorService as T

    cfg = tmp_path / "config.json"
    cfg.write_text("{}")
    calls = []
    monkeypatch.setattr(T, "_parse_team_config", lambda p: {"members": ["a"]})
    monkeypatch.setattr(T, "_update_members", lambda *a, **k: None)

    class _PSM:
        @staticmethod
        def _broadcast(sid, ev, data):
            calls.append((sid, ev))

    import app.services.project_session_manager as psm_mod

    monkeypatch.setattr(psm_mod, "ProjectSessionManager", _PSM)

    with T._lock:
        T._monitors["s"] = {"last_config_mtime": 0.0, "known_task_files": {}}
    try:
        T._broadcast_config_if_newer("s", str(cfg))
        T._broadcast_config_if_newer("s", str(cfg))  # same mtime → no 2nd broadcast
    finally:
        with T._lock:
            T._monitors.pop("s", None)
    assert len(calls) == 1
