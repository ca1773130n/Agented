"""Regression test: `run_streaming_response` registers the session
synchronously so the SSE doesn't error out before the streaming thread
has a chance to push anything.

The bug: a sketch send opened the SSE at
``/admin/super-agents/{sa}/sessions/{sid}/chat/stream`` immediately
after the route returned, but no caller had registered ``session_id``
in ``ChatStateService._sessions``. ``subscribe()`` checked the dict,
fell through to ``yield "Session not found"`` + return, and the
EventSource fired ``onerror``. The frontend rendered "Connection lost.
You can retry by routing again." even though the streaming thread
behind the scenes had completed fine.

Pinning the fix here in a small focused test so future refactors of
the helper don't silently regress it. The companion test in
``test_litestar_leaf_crud_i.py`` covers the chat endpoint's eager
``init_session`` call.
"""

from __future__ import annotations

from unittest.mock import patch

from app.services.chat_state_service import ChatStateService
from app.services.streaming_helper import run_streaming_response


def test_run_streaming_response_registers_session_synchronously(isolated_db):
    """`init_session` must run on the calling thread before the streaming
    thread spawns so a frontend that opens the SSE immediately after
    the POST returns finds the session already registered.
    """
    session_id = "sess-init-sync"

    # Sanity: nothing registered yet.
    assert session_id not in ChatStateService._sessions

    # Stub everything the streaming thread touches so the test stays fast
    # and never actually shells out to a CLI.
    with (
        patch(
            "app.services.super_agent_session_service.SuperAgentSessionService.assemble_system_prompt",
            return_value="sys",
        ),
        patch(
            "app.services.super_agent_session_service.SuperAgentSessionService.get_session_state",
            return_value={"conversation_log": []},
        ),
        patch(
            "app.services.conversation_streaming.stream_llm_response",
            return_value=iter([]),
        ),
    ):
        run_streaming_response(
            session_id=session_id,
            super_agent_id="sa-init-sync",
            backend="claude",
            use_cli_agent=False,  # force the legacy path so we don't fork
        )

        # The session must be registered as soon as the helper returns,
        # *before* the background thread has a chance to run. Without
        # this, the SSE handler beats the thread to the lookup and
        # yields "Session not found".
        assert session_id in ChatStateService._sessions

    # Cleanup so other tests don't see leakage.
    ChatStateService.remove_session(session_id)


def test_init_session_is_idempotent(isolated_db):
    """Multiple `init_session` calls don't reset the event log.

    `run_streaming_response` calls `init_session` unconditionally, but
    `super_agents_cluster.create_session_endpoint` and `grd_routes.
    project_chat` already do too. Idempotency keeps both paths safe.
    """
    session_id = "sess-idem"
    ChatStateService.init_session(session_id)
    ChatStateService.push_delta(session_id, "marker", {"keep": True})
    seq_before = ChatStateService._sessions[session_id]["seq"]

    ChatStateService.init_session(session_id)
    ChatStateService.init_session(session_id)

    assert ChatStateService._sessions[session_id]["seq"] == seq_before
    log = ChatStateService._sessions[session_id]["event_log"]
    assert any(entry.get("keep") for entry in log)

    ChatStateService.remove_session(session_id)
