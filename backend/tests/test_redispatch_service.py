"""Manual re-dispatch of interrupted/failed executions (Phase 4, Unit A)."""

import json
import threading
import time
from unittest.mock import patch

from app.db.execution_logs import (
    create_execution_log,
    get_redispatch_child,
    set_execution_session_id,
    update_execution_log,
)
from app.services.execution_service import ExecutionService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_execution(
    execution_id: str = "exec-1",
    status: str = "interrupted",
    backend: str = "claude",
):
    create_execution_log(
        execution_id=execution_id,
        trigger_id="bot-pr-review",
        trigger_type="manual",
        started_at="2026-06-11T00:00:00",
        prompt="ORIGINAL STORED PROMPT",
        backend_type=backend,
        command="echo hi",
    )
    update_execution_log(execution_id, status=status, finished_at="2026-06-11T00:01:00")


def _wait_for_call(mock, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if mock.called:
            return
        time.sleep(0.01)
    assert mock.called, "run_trigger was never invoked by the dispatch thread"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_redispatch_interrupted_uses_stored_prompt():
    _make_execution()
    with patch.object(ExecutionService, "run_trigger", return_value="exec-new") as rt:
        result = ExecutionService.redispatch_execution("exec-1")
        _wait_for_call(rt)
    # The returned id is PREALLOCATED (dispatch is async) and threaded into
    # run_trigger as execution_id.
    kwargs = rt.call_args.kwargs
    assert result["execution_id"] == kwargs["execution_id"]
    assert kwargs["prompt_override"] == "ORIGINAL STORED PROMPT"
    assert kwargs.get("resume_session_id") is None  # interrupted run has no handle


def test_redispatch_failed_claude_with_session_resumes():
    _make_execution(status="failed")
    set_execution_session_id("exec-1", "sess-abc")
    with patch.object(ExecutionService, "run_trigger", return_value="exec-new") as rt:
        ExecutionService.redispatch_execution("exec-1")
        _wait_for_call(rt)
    kwargs = rt.call_args.kwargs
    assert kwargs["resume_session_id"] == "sess-abc"
    # Continuation prompt replaces the raw stored prompt when resuming.
    assert "Continue" in kwargs["prompt_override"]
    assert "ORIGINAL STORED PROMPT" in kwargs["prompt_override"]


def test_redispatch_codex_never_resumes():
    _make_execution(status="failed", backend="codex")
    set_execution_session_id("exec-1", "sess-abc")  # even with a stored id
    with patch.object(ExecutionService, "run_trigger", return_value="exec-new") as rt:
        ExecutionService.redispatch_execution("exec-1")
        _wait_for_call(rt)
    assert rt.call_args.kwargs.get("resume_session_id") is None


def test_redispatch_replays_original_account_identity():
    """claude --resume only works under the SAME account config dir; the
    original account_id must be resolved and passed through."""
    create_execution_log(
        execution_id="exec-acct",
        trigger_id="bot-pr-review",
        trigger_type="manual",
        started_at="2026-06-11T00:00:00",
        prompt="p",
        backend_type="claude",
        command="echo hi",
        account_id=42,
    )
    update_execution_log("exec-acct", status="interrupted", finished_at="2026-06-11T00:01:00")
    with (
        patch.object(ExecutionService, "run_trigger", return_value="exec-new") as rt,
        patch(
            "app.services.execution_service._build_account_env_overrides",
            return_value={"CLAUDE_CONFIG_DIR": "/cfg/42"},
        ) as env,
    ):
        ExecutionService.redispatch_execution("exec-acct")
        _wait_for_call(rt)
    env.assert_called_once_with(42)
    assert rt.call_args.kwargs["account_id"] == 42
    assert rt.call_args.kwargs["env_overrides"] == {"CLAUDE_CONFIG_DIR": "/cfg/42"}


def test_redispatch_rejects_running_and_success():
    _make_execution("exec-r", status="running")
    _make_execution("exec-s", status="success")
    for eid in ("exec-r", "exec-s"):
        result = ExecutionService.redispatch_execution(eid)
        assert result.get("error") == "not_eligible"


def test_redispatch_rejects_unknown():
    assert ExecutionService.redispatch_execution("nope").get("error") == "not_found"


def test_redispatch_early_return_does_not_leak_in_flight():
    """A trigger_missing (or any post-eligibility) early return must NOT leave
    the origin stuck in the in-flight set — the claim happens last."""
    # The FK constraint requires a valid trigger_id; patch get_trigger to
    # simulate a trigger row that has since been deleted (trigger_missing path).
    create_execution_log(
        execution_id="exec-orphan",
        trigger_id="bot-pr-review",  # valid FK target
        trigger_type="manual",
        started_at="2026-06-11T00:00:00",
        prompt="p",
        backend_type="claude",
        command="echo hi",
    )
    update_execution_log("exec-orphan", status="interrupted", finished_at="2026-06-11T00:01:00")
    with patch("app.db.triggers.get_trigger", return_value=None):
        assert (
            ExecutionService.redispatch_execution("exec-orphan").get("error") == "trigger_missing"
        )
        # Second call must report the SAME error — not already_redispatched.
        assert (
            ExecutionService.redispatch_execution("exec-orphan").get("error") == "trigger_missing"
        )


def test_redispatch_rapid_double_call_single_dispatch():
    """The async no-fan-out race: while the first dispatch thread is still
    in flight (no child row yet), a second call must be rejected by the
    in-process in-flight set."""
    _make_execution("exec-race")

    release = threading.Event()
    started = threading.Event()

    def _blocking_run_trigger(*args, **kwargs):
        started.set()
        release.wait(timeout=5)
        return "exec-new"

    with patch.object(ExecutionService, "run_trigger", side_effect=_blocking_run_trigger):
        first = ExecutionService.redispatch_execution("exec-race")
        assert "execution_id" in first
        assert started.wait(timeout=2)  # dispatch thread is now in flight
        second = ExecutionService.redispatch_execution("exec-race")
        release.set()
    assert second.get("error") == "already_redispatched"


def test_redispatch_prefers_trigger_config_snapshot():
    """Deterministic replay: the trigger dict passed to run_trigger comes from
    the stored snapshot, not the (possibly since-edited) current DB row."""
    create_execution_log(
        execution_id="exec-snap",
        trigger_id="bot-pr-review",
        trigger_type="manual",
        started_at="2026-06-11T00:00:00",
        prompt="stored prompt",
        backend_type="claude",
        command="echo hi",
        trigger_config_snapshot=json.dumps(
            {"id": "bot-pr-review", "name": "AS-IT-WAS", "prompt_template": "old tpl"}
        ),
    )
    update_execution_log("exec-snap", status="interrupted", finished_at="2026-06-11T00:01:00")
    with patch.object(ExecutionService, "run_trigger", return_value="exec-new") as rt:
        ExecutionService.redispatch_execution("exec-snap")
        _wait_for_call(rt)
    assert rt.call_args.args[0]["name"] == "AS-IT-WAS"  # snapshot, not current DB row


def test_redispatch_no_fan_out():
    _make_execution()
    with patch.object(ExecutionService, "run_trigger", return_value="exec-new"):
        first = ExecutionService.redispatch_execution("exec-1")
    assert "execution_id" in first
    # run_trigger was mocked, so set provenance the way the real path does:
    from app.db.execution_logs import set_redispatched_from

    create_execution_log(
        execution_id="exec-new",
        trigger_id="bot-pr-review",
        trigger_type="manual",
        started_at="2026-06-11T00:02:00",
        prompt="p",
        backend_type="claude",
        command="echo hi",
    )
    set_redispatched_from("exec-new", "exec-1")
    second = ExecutionService.redispatch_execution("exec-1")
    assert second.get("error") == "already_redispatched"
    assert get_redispatch_child("exec-1")["execution_id"] == "exec-new"


def test_account_env_overrides_include_backend_type():
    """_build_account_env_overrides must JOIN the backend row: the canonical
    _build_account_env decides CLAUDE_CONFIG_DIR vs GEMINI_CLI_HOME from
    account['backend_type'], which lives on ai_backends, not backend_accounts.
    Without it a claude --resume redispatch falls back to the default config
    dir and the saved session id is unusable (codex PR review P2)."""
    from app.db.connection import get_connection
    from app.services.execution_service import _build_account_env_overrides

    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO ai_backends (id, name, type) VALUES ('be-claude', 'Claude', 'claude')"
        )
        conn.execute(
            "INSERT INTO backend_accounts (backend_id, account_name, config_path) "
            "VALUES ('be-claude', 'acct', '/cfg/claude-acct')"
        )
        account_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()

    env = _build_account_env_overrides(account_id)
    assert env is not None
    assert env.get("CLAUDE_CONFIG_DIR") == "/cfg/claude-acct"
