"""Claude resume handle: capture + --resume command flag (Phase 4, Unit B)."""

from app.services.execution_service import ExecutionService


def test_build_command_claude_with_resume_session_id():
    cmd = ExecutionService.build_command("claude", "continue the task", resume_session_id="sess-1")
    assert "--resume" in cmd
    assert cmd[cmd.index("--resume") + 1] == "sess-1"


def test_build_command_claude_without_resume_unchanged():
    cmd = ExecutionService.build_command("claude", "do the task")
    assert "--resume" not in cmd


def test_build_command_codex_ignores_resume():
    cmd = ExecutionService.build_command("codex", "do the task", resume_session_id="sess-1")
    assert "--resume" not in cmd


def test_build_command_gemini_ignores_resume():
    cmd = ExecutionService.build_command("gemini", "do the task", resume_session_id="sess-1")
    assert "--resume" not in cmd


def test_post_run_usage_capture_writes_session_id():
    """The usage-recording path persists claude's session_id onto execution_logs."""

    from app.db.execution_logs import create_execution_log, get_execution_log
    from app.services.execution_service import _capture_session_id

    create_execution_log(
        execution_id="exec-1",
        trigger_id="bot-pr-review",
        trigger_type="manual",
        started_at="2026-06-11T00:00:00",
        prompt="p",
        backend_type="claude",
        command="echo hi",
    )
    _capture_session_id("exec-1", {"input_tokens": 1, "session_id": "sess-xyz"})
    assert get_execution_log("exec-1")["session_id"] == "sess-xyz"
    # None / absent session_id is a no-op, never an error.
    _capture_session_id("exec-1", {"input_tokens": 1})
    _capture_session_id("exec-1", None)
    assert get_execution_log("exec-1")["session_id"] == "sess-xyz"
