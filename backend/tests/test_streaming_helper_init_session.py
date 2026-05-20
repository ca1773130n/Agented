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


def test_empty_content_turns_are_filtered_from_llm_messages(isolated_db):
    """Regression for v0.7.97: the SuperAgent conversation_log
    sometimes contains entries with empty or whitespace-only content
    (interrupted assistant streams, tool-only turns where the
    serializer produced no text payload, etc.).

    Pre-fix, ``streaming_helper`` appended every entry verbatim to
    the LLM payload. CLIProxyAPI's OpenAI translation then rejected
    the request with "text content blocks must be non-empty" and
    the whole turn 500'd. The other three conversation services
    (base, plugin, skill) already filtered the same way — only this
    code path was missing the guard.

    This test asserts that the messages handed to
    ``stream_llm_response`` contain ONLY non-empty user/assistant
    turns, regardless of how many empty entries were in the
    conversation_log.
    """
    session_id = "sess-empty-filter"
    ChatStateService.remove_session(session_id)

    # conversation_log with a mix of valid + empty/whitespace entries.
    log = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": ""},        # empty → drop
        {"role": "user", "content": "   \n\t  "},    # whitespace → drop
        {"role": "assistant", "content": "world"},
        {"role": "tool", "content": None},           # None → drop (no AttributeError)
        {"role": "user", "content": "ok"},
    ]

    import threading

    captured: dict = {}
    captured_evt = threading.Event()

    def capture_messages(messages, **_kwargs):
        captured["messages"] = list(messages)
        captured_evt.set()
        return iter([])

    with (
        patch(
            "app.services.super_agent_session_service.SuperAgentSessionService.assemble_system_prompt",
            return_value="sys",
        ),
        patch(
            "app.services.super_agent_session_service.SuperAgentSessionService.get_session_state",
            return_value={"conversation_log": log},
        ),
        patch(
            "app.services.conversation_streaming.stream_llm_response",
            side_effect=capture_messages,
        ),
    ):
        run_streaming_response(
            session_id=session_id,
            super_agent_id="sa-empty-filter",
            backend="claude",
            use_cli_agent=False,
        )

    # Streaming runs on a background thread; the side_effect signals
    # the event as soon as it's been called. ``Event.wait`` is
    # deterministic + faster than a sleep-poll loop, and the 2s
    # ceiling is comfortable even on heavily loaded CI runners.
    assert captured_evt.wait(timeout=2.0), (
        "background thread didn't call stream_llm_response within 2s"
    )

    messages = captured["messages"]
    # System prompt is always first; the rest must be non-empty content only.
    assert messages[0]["role"] == "system"
    payload_turns = messages[1:]
    assert [m["content"] for m in payload_turns] == ["hello", "world", "ok"], (
        f"empty/whitespace/None content must be filtered, got {payload_turns}"
    )
    for m in payload_turns:
        assert m["content"] and m["content"].strip()

    ChatStateService.remove_session(session_id)
