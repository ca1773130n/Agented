"""Tests for SuperAgent chat streaming — unified streaming path.

These tests verify:
1. ChatDelta model field structure (unit tests, no route dependency)
2. Unified streaming path calls stream_llm_response with correct args
3. Assistant responses are persisted to conversation_log after streaming
4. Backend parameter resolves correctly (auto → agent's backend_type)
5. ChatStateService receives content_delta, finish, and status_change events
6. Full conversation history (user + assistant) is sent to the LLM
"""

import json
import threading
import time
from unittest.mock import patch

import pytest

from app.models.chat_state import ChatDelta, ChatDeltaType
from app.services.chat_state_service import ChatStateService
from app.services.super_agent_session_service import SuperAgentSessionService

# ===========================================================================
# Unit tests: ChatDelta text→content field mapping
# ===========================================================================


class TestChatDeltaFieldMapping:
    """Verify ChatDelta model_dump produces expected fields."""

    def test_content_delta_has_text_field(self):
        """ChatDelta.CONTENT_DELTA uses 'text' field internally."""
        delta = ChatDelta(type=ChatDeltaType.CONTENT_DELTA, text="hello")
        data = delta.model_dump(exclude_none=True)
        assert "text" in data
        assert data["text"] == "hello"
        # The raw model uses 'text', NOT 'content'
        assert "content" not in data

    def test_text_to_content_mapping_logic(self):
        """The route maps text→content before pushing to SSE."""
        delta = ChatDelta(type=ChatDeltaType.CONTENT_DELTA, text="streaming chunk")
        delta_data = delta.model_dump(exclude_none=True)
        # Simulate the mapping that the route does
        if "text" in delta_data:
            delta_data["content"] = delta_data.pop("text")
        assert "content" in delta_data
        assert delta_data["content"] == "streaming chunk"
        assert "text" not in delta_data

    def test_finish_delta_has_finish_reason(self):
        """ChatDelta.FINISH has finish_reason, no text/content."""
        delta = ChatDelta(type=ChatDeltaType.FINISH, finish_reason="stop")
        data = delta.model_dump(exclude_none=True)
        assert data["finish_reason"] == "stop"
        assert "text" not in data
        assert "content" not in data

    def test_error_delta_has_error_message(self):
        """ChatDelta.ERROR has error_message."""
        delta = ChatDelta(type=ChatDeltaType.ERROR, error_message="API key missing")
        data = delta.model_dump(exclude_none=True)
        assert data["error_message"] == "API key missing"

    def test_tool_call_delta_fields(self):
        """ChatDelta.TOOL_CALL has tool-specific fields."""
        delta = ChatDelta(
            type=ChatDeltaType.TOOL_CALL,
            tool_call_id="tc_123",
            function_name="search",
            arguments_json='{"q": "test"}',
        )
        data = delta.model_dump(exclude_none=True)
        assert data["tool_call_id"] == "tc_123"
        assert data["function_name"] == "search"


# ===========================================================================
# ChatStateService integration tests
# ===========================================================================


class TestChatStateServiceDeltas:
    """Verify ChatStateService delivers deltas with correct fields."""

    def setup_method(self):
        ChatStateService.reset()

    def teardown_method(self):
        ChatStateService.reset()

    def test_push_content_delta_with_content_field(self):
        """push_delta with content field delivers it in SSE event."""
        session_id = "test-session-1"
        ChatStateService.init_session(session_id)

        ChatStateService.push_delta(session_id, "content_delta", {"content": "Hello world"})

        with ChatStateService._lock:
            session = ChatStateService._sessions[session_id]
            events = session["event_log"]
            assert len(events) == 1
            assert events[0]["type"] == "content_delta"
            assert events[0]["content"] == "Hello world"
            assert "text" not in events[0]

    def test_push_multiple_content_deltas(self):
        """Multiple content_delta events accumulate in order."""
        session_id = "test-session-2"
        ChatStateService.init_session(session_id)

        chunks = ["Hello ", "world", "! How ", "are you?"]
        for chunk in chunks:
            ChatStateService.push_delta(session_id, "content_delta", {"content": chunk})

        with ChatStateService._lock:
            session = ChatStateService._sessions[session_id]
            events = session["event_log"]
            assert len(events) == 4
            contents = [e["content"] for e in events]
            assert contents == chunks

    def test_push_status_change(self):
        """push_status delivers status_change event."""
        session_id = "test-session-3"
        ChatStateService.init_session(session_id)

        ChatStateService.push_status(session_id, "streaming")

        with ChatStateService._lock:
            session = ChatStateService._sessions[session_id]
            assert session["status"] == "streaming"
            events = session["event_log"]
            assert any(e["type"] == "status_change" and e["status"] == "streaming" for e in events)

    def test_subscriber_receives_content_delta(self):
        """SSE subscriber receives content_delta events in real-time."""
        session_id = "test-session-4"
        ChatStateService.init_session(session_id)

        received = []

        def subscriber():
            for event in ChatStateService.subscribe(session_id, heartbeat_timeout=1):
                if "content_delta" in event:
                    data = json.loads(event.split("data: ")[1].strip())
                    received.append(data)
                    if data.get("content") == "done":
                        break

        t = threading.Thread(target=subscriber, daemon=True)
        t.start()

        time.sleep(0.05)  # Let subscriber register
        ChatStateService.push_delta(session_id, "content_delta", {"content": "chunk1"})
        ChatStateService.push_delta(session_id, "content_delta", {"content": "done"})
        t.join(timeout=3)

        assert len(received) == 2
        assert received[0]["content"] == "chunk1"
        assert received[1]["content"] == "done"


# ===========================================================================
# Route-level HTTP tests
# ===========================================================================

# The mock target: stream_llm_response is imported inside the background
# thread via `from ..services.conversation_streaming import stream_llm_response`,
# so we mock it at the module level where it's defined.
_STREAM_MOCK = "app.services.conversation_streaming.stream_llm_response"


@pytest.fixture(autouse=True)
def _reset_session_service():
    """Reset SuperAgentSessionService active sessions between tests."""
    SuperAgentSessionService._active_sessions.clear()
    yield
    SuperAgentSessionService._active_sessions.clear()


def _create_super_agent_and_session(client, backend_type="claude"):
    """Helper: create a super agent and session, return (agent_id, session_id)."""
    resp = client.post(
        "/admin/super-agents/",
        json={"name": "Test Agent", "description": "For testing", "backend_type": backend_type},
    )
    assert resp.status_code == 201, f"Failed to create agent: {resp.get_json()}"
    agent_id = resp.get_json()["super_agent_id"]

    resp = client.post(f"/admin/super-agents/{agent_id}/sessions")
    assert resp.status_code == 201, f"Failed to create session: {resp.get_json()}"
    session_id = resp.get_json()["session_id"]

    return agent_id, session_id


class TestChatRouteValidation:
    """Test chat endpoint input validation and error handling."""

    def test_chat_missing_json_body(self, client, isolated_db):
        """POST without JSON body returns 400."""
        resp = client.post(
            "/admin/super-agents/fake-agent/sessions/fake-session/chat",
            content_type="application/json",
            data="",
        )
        assert resp.status_code == 400

    def test_chat_empty_content(self, client, isolated_db):
        """POST with empty content returns 400."""
        resp = client.post(
            "/admin/super-agents/fake-agent/sessions/fake-session/chat",
            json={"content": ""},
        )
        assert resp.status_code == 400

    def test_chat_whitespace_only_content(self, client, isolated_db):
        """POST with whitespace-only content returns 400."""
        resp = client.post(
            "/admin/super-agents/fake-agent/sessions/fake-session/chat",
            json={"content": "   "},
        )
        assert resp.status_code == 400

    def test_chat_nonexistent_session(self, client, isolated_db):
        """POST to nonexistent session returns 404."""
        resp = client.post(
            "/admin/super-agents/fake-agent/sessions/fake-session/chat",
            json={"content": "hello"},
        )
        assert resp.status_code == 404

    def test_chat_success_returns_ok_and_message_id(self, client, isolated_db):
        """POST with valid content to active session returns 200 with message_id."""
        agent_id, session_id = _create_super_agent_and_session(client)

        with patch(_STREAM_MOCK) as mock_stream:
            mock_stream.return_value = iter(["response"])

            resp = client.post(
                f"/admin/super-agents/{agent_id}/sessions/{session_id}/chat",
                json={"content": "hello"},
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["status"] == "ok"
            assert "message_id" in data


class TestChatStreamingUnifiedPath:
    """Test the unified streaming path via stream_llm_response."""

    def test_calls_stream_llm_response(self, client, isolated_db):
        """Streaming path calls stream_llm_response with messages."""
        agent_id, session_id = _create_super_agent_and_session(client)

        with patch(_STREAM_MOCK) as mock_stream:
            mock_stream.return_value = iter(["hi there"])

            resp = client.post(
                f"/admin/super-agents/{agent_id}/sessions/{session_id}/chat",
                json={"content": "hello"},
            )
            assert resp.status_code == 200

            time.sleep(0.3)

            mock_stream.assert_called_once()
            call_args = mock_stream.call_args
            messages = call_args[0][0]
            assert any(m["content"] == "hello" for m in messages)

    def test_pushes_content_deltas(self, client, isolated_db):
        """Streaming pushes content_delta events to ChatStateService."""
        ChatStateService.reset()
        agent_id, session_id = _create_super_agent_and_session(client)
        ChatStateService.init_session(session_id)

        with patch(_STREAM_MOCK) as mock_stream:
            mock_stream.return_value = iter(["Hello ", "world!"])

            client.post(
                f"/admin/super-agents/{agent_id}/sessions/{session_id}/chat",
                json={"content": "hi"},
            )

            time.sleep(0.5)

            with ChatStateService._lock:
                session = ChatStateService._sessions.get(session_id)
                if session:
                    events = session["event_log"]
                    content_deltas = [e for e in events if e["type"] == "content_delta"]
                    assert (
                        len(content_deltas) >= 2
                    ), f"Expected 2+ content_delta events, got {len(content_deltas)}"
                    for cd in content_deltas:
                        assert "content" in cd
                        assert "text" not in cd

    def test_pushes_finish_with_full_content(self, client, isolated_db):
        """Streaming pushes a finish event with the accumulated response."""
        ChatStateService.reset()
        agent_id, session_id = _create_super_agent_and_session(client)
        ChatStateService.init_session(session_id)

        with patch(_STREAM_MOCK) as mock_stream:
            mock_stream.return_value = iter(["Hello ", "world!"])

            client.post(
                f"/admin/super-agents/{agent_id}/sessions/{session_id}/chat",
                json={"content": "hi"},
            )

            time.sleep(0.5)

            with ChatStateService._lock:
                session = ChatStateService._sessions.get(session_id)
                if session:
                    events = session["event_log"]
                    finish_events = [e for e in events if e["type"] == "finish"]
                    assert len(finish_events) == 1, "Should push exactly one finish event"
                    assert finish_events[0]["content"] == "Hello world!"

    def test_pushes_status_streaming_then_idle(self, client, isolated_db):
        """Sets status to streaming at start, idle on completion."""
        ChatStateService.reset()
        agent_id, session_id = _create_super_agent_and_session(client)
        ChatStateService.init_session(session_id)

        with patch(_STREAM_MOCK) as mock_stream:
            mock_stream.return_value = iter(["done"])

            client.post(
                f"/admin/super-agents/{agent_id}/sessions/{session_id}/chat",
                json={"content": "test"},
            )

            time.sleep(0.5)

            with ChatStateService._lock:
                session = ChatStateService._sessions.get(session_id)
                if session:
                    events = session["event_log"]
                    status_events = [e for e in events if e["type"] == "status_change"]
                    statuses = [e["status"] for e in status_events]
                    assert "streaming" in statuses
                    assert "idle" in statuses

    def test_passes_model_kwarg(self, client, isolated_db):
        """Model parameter is forwarded to stream_llm_response."""
        agent_id, session_id = _create_super_agent_and_session(client)

        with patch(_STREAM_MOCK) as mock_stream:
            mock_stream.return_value = iter(["ok"])

            client.post(
                f"/admin/super-agents/{agent_id}/sessions/{session_id}/chat",
                json={"content": "test", "model": "claude-opus-4-20250514"},
            )

            time.sleep(0.3)
            mock_stream.assert_called_once()
            call_kwargs = mock_stream.call_args.kwargs
            assert call_kwargs.get("model") == "claude-opus-4-20250514"

    def test_passes_backend_kwarg(self, client, isolated_db):
        """Explicit backend parameter is forwarded to stream_llm_response."""
        agent_id, session_id = _create_super_agent_and_session(client)

        with patch(_STREAM_MOCK) as mock_stream:
            mock_stream.return_value = iter(["ok"])

            client.post(
                f"/admin/super-agents/{agent_id}/sessions/{session_id}/chat",
                json={"content": "test", "backend": "gemini"},
            )

            time.sleep(0.3)
            mock_stream.assert_called_once()
            call_kwargs = mock_stream.call_args.kwargs
            assert call_kwargs.get("backend") == "gemini"

    def test_auto_backend_resolves_from_agent(self, client, isolated_db):
        """When backend is 'auto', resolves to agent's backend_type."""
        agent_id, session_id = _create_super_agent_and_session(client, backend_type="codex")

        with patch(_STREAM_MOCK) as mock_stream:
            mock_stream.return_value = iter(["ok"])

            client.post(
                f"/admin/super-agents/{agent_id}/sessions/{session_id}/chat",
                json={"content": "test", "backend": "auto"},
            )

            time.sleep(0.3)
            mock_stream.assert_called_once()
            call_kwargs = mock_stream.call_args.kwargs
            assert call_kwargs.get("backend") == "codex"

    def test_passes_account_email(self, client, isolated_db):
        """Account ID is forwarded as account_email to stream_llm_response."""
        agent_id, session_id = _create_super_agent_and_session(client)

        with patch(_STREAM_MOCK) as mock_stream:
            mock_stream.return_value = iter(["ok"])

            client.post(
                f"/admin/super-agents/{agent_id}/sessions/{session_id}/chat",
                json={"content": "test", "account_id": "user@example.com"},
            )

            time.sleep(0.3)
            mock_stream.assert_called_once()
            call_kwargs = mock_stream.call_args.kwargs
            assert call_kwargs.get("account_email") == "user@example.com"


class TestAssistantMessagePersistence:
    """Test that assistant responses are persisted to conversation_log."""

    def test_assistant_response_persisted(self, client, isolated_db):
        """After streaming, the full response is saved to conversation_log."""
        agent_id, session_id = _create_super_agent_and_session(client)

        with patch(_STREAM_MOCK) as mock_stream:
            mock_stream.return_value = iter(["Hello ", "from ", "Claude!"])

            client.post(
                f"/admin/super-agents/{agent_id}/sessions/{session_id}/chat",
                json={"content": "hi"},
            )

            time.sleep(0.5)

            state = SuperAgentSessionService.get_session_state(session_id)
            assert state is not None
            log = state["conversation_log"]
            # Should have: user message + assistant message
            assert len(log) == 2
            assert log[0]["role"] == "user"
            assert log[0]["content"] == "hi"
            assert log[1]["role"] == "assistant"
            assert log[1]["content"] == "Hello from Claude!"

    def test_multi_turn_conversation_context(self, client, isolated_db):
        """Second message includes full conversation history."""
        agent_id, session_id = _create_super_agent_and_session(client)

        # Turn 1
        with patch(_STREAM_MOCK) as mock_stream:
            mock_stream.return_value = iter(["I am Claude."])

            client.post(
                f"/admin/super-agents/{agent_id}/sessions/{session_id}/chat",
                json={"content": "who are you?"},
            )
            time.sleep(0.5)

        # Turn 2 — verify full history is sent
        with patch(_STREAM_MOCK) as mock_stream:
            mock_stream.return_value = iter(["You said 'what can you do'"])

            client.post(
                f"/admin/super-agents/{agent_id}/sessions/{session_id}/chat",
                json={"content": "what can you do?"},
            )
            time.sleep(0.5)

            mock_stream.assert_called_once()
            messages = mock_stream.call_args[0][0]
            # Should include: system prompt (if any) + user1 + assistant1 + user2
            user_msgs = [m for m in messages if m["role"] == "user"]
            asst_msgs = [m for m in messages if m["role"] == "assistant"]
            assert len(user_msgs) >= 2, f"Expected 2+ user messages, got {user_msgs}"
            assert len(asst_msgs) >= 1, f"Expected 1+ assistant messages, got {asst_msgs}"
            assert user_msgs[0]["content"] == "who are you?"
            assert asst_msgs[0]["content"] == "I am Claude."
            assert user_msgs[1]["content"] == "what can you do?"


class TestChatStreamingErrorHandling:
    """Test error handling in the streaming path."""

    def test_error_pushes_error_delta(self, client, isolated_db):
        """When stream_llm_response raises, error delta is pushed."""
        ChatStateService.reset()
        agent_id, session_id = _create_super_agent_and_session(client)
        ChatStateService.init_session(session_id)

        with patch(_STREAM_MOCK, side_effect=Exception("API connection failed")):
            client.post(
                f"/admin/super-agents/{agent_id}/sessions/{session_id}/chat",
                json={"content": "test"},
            )

            time.sleep(0.5)

            with ChatStateService._lock:
                session = ChatStateService._sessions.get(session_id)
                if session:
                    events = session["event_log"]
                    error_events = [e for e in events if e["type"] == "error"]
                    assert len(error_events) > 0, "Should push error event on exception"
                    status_events = [e for e in events if e["type"] == "status_change"]
                    statuses = [e["status"] for e in status_events]
                    assert "error" in statuses

    def test_user_message_pushed_as_delta(self, client, isolated_db):
        """User message is pushed as a message delta before streaming starts."""
        ChatStateService.reset()
        agent_id, session_id = _create_super_agent_and_session(client)
        ChatStateService.init_session(session_id)

        with patch(_STREAM_MOCK) as mock_stream:
            mock_stream.return_value = iter(["ok"])

            client.post(
                f"/admin/super-agents/{agent_id}/sessions/{session_id}/chat",
                json={"content": "my test message"},
            )

            time.sleep(0.3)

            with ChatStateService._lock:
                session = ChatStateService._sessions.get(session_id)
                if session:
                    events = session["event_log"]
                    msg_events = [e for e in events if e["type"] == "message"]
                    assert len(msg_events) >= 1, "User message should be pushed as delta"
                    assert msg_events[0]["role"] == "user"
                    assert msg_events[0]["content"] == "my test message"
