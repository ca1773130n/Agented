"""v0.7.7 follow-up: emission points for git_action and streaming errors.

Asserts that:
1. Calling a git-action route results in a recorded ``git_action`` event
   for the given super_agent_id with the right success flag.
2. A streaming error path records an ``error`` event (mocking the
   streaming exception inside ``run_streaming_response``).
"""

from __future__ import annotations

import threading
from unittest.mock import patch

from litestar.testing import create_test_client

from app.services import super_agent_activity_service as svc
from app_litestar.auth import provide_caller
from app_litestar.routes.super_agents_cluster import (
    super_agent_exports_router,
    super_agents_router,
)


def _client():
    return create_test_client(
        route_handlers=[super_agents_router, super_agent_exports_router],
        dependencies={"caller": provide_caller},
    )


# ---------------------------------------------------------------------------
# Fix 2B — git-action emits an activity event
# ---------------------------------------------------------------------------


def _seed_session_with_worktree(tmp_path, super_agent_id="sa-emit", session_id="sess-emit"):
    """Create the super-agent + session rows needed by git_action route."""
    from app.database import create_super_agent
    from app.db.super_agents import add_super_agent_session, update_super_agent_session

    sa_id = create_super_agent(name="emit", description=None)
    # Force the canonical id used by the test
    from app.database import get_connection

    with get_connection() as conn:
        conn.execute("UPDATE super_agents SET id = ? WHERE id = ?", (super_agent_id, sa_id))
        conn.commit()

    sess = add_super_agent_session(super_agent_id=super_agent_id)
    assert sess is not None
    update_super_agent_session(
        sess,
        worktree_path=str(tmp_path),
        branch_name="feat/emit-test",
    )
    # Force canonical session id
    with get_connection() as conn:
        conn.execute(
            "UPDATE super_agent_sessions SET id = ? WHERE id = ?",
            (session_id, sess),
        )
        conn.commit()
    return super_agent_id, session_id


def test_git_action_diff_emits_activity(isolated_db, tmp_path):
    sa_id, sess_id = _seed_session_with_worktree(tmp_path)

    class _R:
        returncode = 0
        stdout = ""
        stderr = ""

    with patch("subprocess.run", return_value=_R()):
        with _client() as c:
            resp = c.post(
                f"/admin/super-agents/{sa_id}/sessions/{sess_id}/git-action",
                json={"action": "diff"},
            )
    assert resp.status_code in (200, 201)

    rows = svc.list_for_super_agent(sa_id)
    git_events = [r for r in rows if r["event_type"] == "git_action"]
    assert len(git_events) == 1
    assert git_events[0]["status"] == "ok"
    assert "diff" in git_events[0]["payload"]


def test_git_action_commit_failure_emits_error_status(isolated_db, tmp_path):
    sa_id, sess_id = _seed_session_with_worktree(
        tmp_path, super_agent_id="sa-emit-fail", session_id="sess-emit-fail"
    )

    class _Add:
        returncode = 0
        stdout = ""
        stderr = ""

    class _Commit:
        returncode = 1
        stdout = ""
        stderr = "nothing to commit"

    calls = {"i": 0}

    def fake_run(*args, **kwargs):
        calls["i"] += 1
        return _Add() if calls["i"] == 1 else _Commit()

    with patch("subprocess.run", side_effect=fake_run):
        with _client() as c:
            resp = c.post(
                f"/admin/super-agents/{sa_id}/sessions/{sess_id}/git-action",
                json={"action": "commit", "message": "x"},
            )
    assert resp.status_code in (200, 201)

    rows = svc.list_for_super_agent(sa_id)
    git_events = [r for r in rows if r["event_type"] == "git_action"]
    assert len(git_events) == 1
    assert git_events[0]["status"] == "error"


# ---------------------------------------------------------------------------
# Fix 2A — streaming-error records an `error` activity event
# ---------------------------------------------------------------------------


def test_streaming_error_records_error_event(isolated_db):
    """When stream_llm_response raises, an `error` event is recorded.

    Forces the legacy CLIProxy path (``use_cli_agent=False``) since the
    v0.7.17 default routes through the CLI agent runner, which has its
    own subprocess-error coverage in ``test_cli_agent_runner.py``. This
    test specifically pins the legacy-path error recording.
    """
    from app.services.streaming_helper import run_streaming_response

    done = threading.Event()

    def _on_error(_msg):
        done.set()

    # Patch the imports inside the inner _stream_response.
    with (
        patch(
            "app.services.conversation_streaming.stream_llm_response",
            side_effect=RuntimeError("kaboom"),
        ),
        patch(
            "app.services.super_agent_session_service.SuperAgentSessionService.assemble_system_prompt",
            return_value="sys",
        ),
        patch(
            "app.services.super_agent_session_service.SuperAgentSessionService.get_session_state",
            return_value={"conversation_log": []},
        ),
        patch("app.services.chat_state_service.ChatStateService.push_status"),
        patch("app.services.chat_state_service.ChatStateService.push_delta"),
        patch("app.services.error_capture.capture_error"),
    ):
        run_streaming_response(
            session_id="sess-stream",
            super_agent_id="sa-stream",
            backend="claude",
            on_error=_on_error,
            use_cli_agent=False,
        )
        assert done.wait(timeout=5), "streaming thread did not finish"

    rows = svc.list_for_super_agent("sa-stream")
    err_events = [r for r in rows if r["event_type"] == "error"]
    assert len(err_events) == 1
    assert err_events[0]["status"] == "error"
    assert err_events[0]["error_message"] == "kaboom"
