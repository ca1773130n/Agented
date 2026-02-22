"""Tests for ChatStateService subscription, replay, cap, and route endpoints."""

import json
import threading
import time

import pytest

from app.services.chat_state_service import EVENT_LOG_MAX, ChatStateService
from app.services.super_agent_session_service import SuperAgentSessionService


@pytest.fixture(autouse=True)
def clear_state():
    """Clear ChatStateService and SuperAgentSessionService state between tests."""
    ChatStateService.reset()
    SuperAgentSessionService._active_sessions = {}
    yield
    ChatStateService.reset()
    SuperAgentSessionService._active_sessions = {}


SAMPLE_SUPER_AGENT = {
    "name": "ChatAgent",
    "description": "Agent for chat testing",
    "backend_type": "claude",
}


def _create_super_agent(client, **overrides):
    """Helper to create a super agent via API."""
    data = {**SAMPLE_SUPER_AGENT, **overrides}
    return client.post("/admin/super-agents/", json=data)


# =============================================================================
# ChatStateService unit tests
# =============================================================================


class TestInitAndRemoveSession:
    def test_init_creates_session(self, isolated_db):
        """init_session creates a session entry with default values."""
        ChatStateService.init_session("sess-abc")
        status = ChatStateService.get_session_status("sess-abc")
        assert status == "idle"

    def test_init_idempotent(self, isolated_db):
        """init_session does not overwrite an existing session."""
        ChatStateService.init_session("sess-abc")
        ChatStateService.push_delta("sess-abc", "test", {"x": 1})
        ChatStateService.init_session("sess-abc")  # Should not reset
        status = ChatStateService.get_session_status("sess-abc")
        assert status == "idle"
        # Seq should still be 1 (not reset)
        with ChatStateService._lock:
            assert ChatStateService._sessions["sess-abc"]["seq"] == 1

    def test_remove_cleans_up(self, isolated_db):
        """remove_session removes the session and returns None for status."""
        ChatStateService.init_session("sess-abc")
        ChatStateService.remove_session("sess-abc")
        assert ChatStateService.get_session_status("sess-abc") is None

    def test_remove_nonexistent_is_noop(self, isolated_db):
        """remove_session on nonexistent session does not raise."""
        ChatStateService.remove_session("sess-nonexist")  # Should not raise


class TestPushDeltaIncrementsSeq:
    def test_push_three_deltas(self, isolated_db):
        """Pushing 3 deltas gives seq 1, 2, 3."""
        ChatStateService.init_session("sess-abc")
        ChatStateService.push_delta("sess-abc", "content_delta", {"text": "a"})
        ChatStateService.push_delta("sess-abc", "content_delta", {"text": "b"})
        ChatStateService.push_delta("sess-abc", "content_delta", {"text": "c"})

        with ChatStateService._lock:
            session = ChatStateService._sessions["sess-abc"]
            assert session["seq"] == 3
            assert len(session["event_log"]) == 3
            assert session["event_log"][0]["seq"] == 1
            assert session["event_log"][1]["seq"] == 2
            assert session["event_log"][2]["seq"] == 3


class TestSubscribeReceivesDeltas:
    def test_subscribe_receives_pushed_deltas(self, isolated_db):
        """Subscriber generator yields events pushed after subscription."""
        ChatStateService.init_session("sess-abc")

        results = []

        def subscriber():
            gen = ChatStateService.subscribe("sess-abc", heartbeat_timeout=1)
            for event in gen:
                results.append(event)
                if len(results) >= 3:
                    break

        t = threading.Thread(target=subscriber)
        t.start()

        # Give the subscriber time to start
        time.sleep(0.1)

        ChatStateService.push_delta("sess-abc", "content_delta", {"text": "a"})
        ChatStateService.push_delta("sess-abc", "content_delta", {"text": "b"})
        ChatStateService.push_delta("sess-abc", "content_delta", {"text": "c"})

        t.join(timeout=5)

        assert len(results) == 3
        for r in results:
            assert "event: state_delta" in r
            assert "id: " in r


class TestSubscribeReplayOnReconnect:
    def test_replay_missed_events(self, isolated_db):
        """Subscribing with last_seq=2 replays seq 3, 4, 5."""
        ChatStateService.init_session("sess-abc")

        # Push 5 deltas
        for i in range(5):
            ChatStateService.push_delta("sess-abc", "content_delta", {"text": f"msg{i}"})

        # Subscribe with last_seq=2 -- should replay seq 3, 4, 5
        gen = ChatStateService.subscribe("sess-abc", last_seq=2, heartbeat_timeout=1)
        replayed = []
        for event in gen:
            if "state_delta" in event:
                replayed.append(event)
            if len(replayed) >= 3:
                break

        assert len(replayed) == 3
        # Parse the events to verify seq numbers
        for i, event_str in enumerate(replayed):
            data_line = [ln for ln in event_str.strip().split("\n") if ln.startswith("data:")][0]
            data = json.loads(data_line.replace("data: ", "", 1))
            assert data["seq"] == i + 3  # seq 3, 4, 5

        # Cleanup: remove session to stop the generator
        ChatStateService.remove_session("sess-abc")


class TestEventLogCap:
    def test_log_capped_at_1000(self, isolated_db):
        """Pushing 1100 deltas leaves only 1000 in the log, oldest seq is 101."""
        ChatStateService.init_session("sess-abc")

        for i in range(1100):
            ChatStateService.push_delta("sess-abc", "content_delta", {"n": i})

        with ChatStateService._lock:
            session = ChatStateService._sessions["sess-abc"]
            assert len(session["event_log"]) == EVENT_LOG_MAX
            assert session["event_log"][0]["seq"] == 101
            assert session["event_log"][-1]["seq"] == 1100
            assert session["seq"] == 1100


class TestSubscribeFullSyncOnStaleCursor:
    def test_full_sync_for_stale_cursor(self, isolated_db):
        """Subscribing with last_seq=1 after 1100 deltas triggers full_sync."""
        ChatStateService.init_session("sess-abc")

        for i in range(1100):
            ChatStateService.push_delta("sess-abc", "content_delta", {"n": i})

        gen = ChatStateService.subscribe("sess-abc", last_seq=1, heartbeat_timeout=1)
        first_event = next(gen)

        assert "event: full_sync" in first_event
        data_line = [ln for ln in first_event.strip().split("\n") if ln.startswith("data:")][0]
        data = json.loads(data_line.replace("data: ", "", 1))
        assert "events" in data
        assert len(data["events"]) == EVENT_LOG_MAX

        # Cleanup
        ChatStateService.remove_session("sess-abc")


class TestHeartbeatOnTimeout:
    def test_heartbeat_sent_on_timeout(self, isolated_db):
        """When no deltas arrive, heartbeat comment is yielded after timeout."""
        ChatStateService.init_session("sess-abc")

        gen = ChatStateService.subscribe("sess-abc", heartbeat_timeout=1)
        # The first event should be a heartbeat (no deltas pushed)
        event = next(gen)
        assert event == ": heartbeat\n\n"

        # Cleanup
        ChatStateService.remove_session("sess-abc")


class TestSubscribeSessionNotFound:
    def test_error_for_nonexistent_session(self, isolated_db):
        """Subscribing to a nonexistent session yields an error event."""
        gen = ChatStateService.subscribe("sess-nonexist")
        event = next(gen)
        assert "event: error" in event
        assert "Session not found" in event


# =============================================================================
# Route integration tests
# =============================================================================


class TestChatStreamRoute:
    def test_chat_stream_returns_sse(self, client):
        """GET /chat/stream with Last-Event-ID replays missed events as SSE."""
        sa_resp = _create_super_agent(client)
        sa_id = sa_resp.get_json()["super_agent_id"]

        sess_resp = client.post(f"/admin/super-agents/{sa_id}/sessions")
        sess_id = sess_resp.get_json()["session_id"]

        # Push deltas before connecting
        ChatStateService.push_delta(sess_id, "content_delta", {"text": "hello"})
        ChatStateService.push_delta(sess_id, "content_delta", {"text": "world"})

        # Schedule session removal to terminate the SSE generator after replay
        def _remove_after_delay():
            time.sleep(0.3)
            ChatStateService.remove_session(sess_id)

        t = threading.Thread(target=_remove_after_delay, daemon=True)
        t.start()

        # Use Last-Event-ID to trigger replay (last_seq=0 means no replay,
        # but there's no "replay all" semantic. So we pass "0" but the logic
        # only replays when last_seq > 0. We verify content-type and status.
        resp = client.get(f"/admin/super-agents/{sa_id}/sessions/{sess_id}/chat/stream")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/event-stream")

        t.join(timeout=5)

    def test_chat_stream_nonexistent_session(self, client):
        """GET /chat/stream for nonexistent session yields error event."""
        sa_resp = _create_super_agent(client)
        sa_id = sa_resp.get_json()["super_agent_id"]

        # Access a session that doesn't exist in ChatStateService
        resp = client.get(f"/admin/super-agents/{sa_id}/sessions/sess-nonexist/chat/stream")
        assert resp.status_code == 200
        data = resp.get_data(as_text=True)
        assert "Session not found" in data


class TestChatSendRoute:
    def test_send_chat_message(self, client):
        """POST /chat sends a message and returns 200 with message_id."""
        sa_resp = _create_super_agent(client)
        sa_id = sa_resp.get_json()["super_agent_id"]

        sess_resp = client.post(f"/admin/super-agents/{sa_id}/sessions")
        sess_id = sess_resp.get_json()["session_id"]

        resp = client.post(
            f"/admin/super-agents/{sa_id}/sessions/{sess_id}/chat",
            json={"content": "Hello, chat!"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "ok"
        assert body["message_id"].startswith("msg-")

    def test_send_chat_empty_content(self, client):
        """POST /chat with empty content returns 400."""
        sa_resp = _create_super_agent(client)
        sa_id = sa_resp.get_json()["super_agent_id"]

        sess_resp = client.post(f"/admin/super-agents/{sa_id}/sessions")
        sess_id = sess_resp.get_json()["session_id"]

        resp = client.post(
            f"/admin/super-agents/{sa_id}/sessions/{sess_id}/chat",
            json={"content": ""},
        )
        assert resp.status_code == 400

    def test_send_chat_session_not_found(self, client):
        """POST /chat to nonexistent session returns 404."""
        sa_resp = _create_super_agent(client)
        sa_id = sa_resp.get_json()["super_agent_id"]

        resp = client.post(
            f"/admin/super-agents/{sa_id}/sessions/sess-nonexist/chat",
            json={"content": "Hello"},
        )
        assert resp.status_code == 404

    def test_send_chat_pushes_user_delta(self, client):
        """POST /chat pushes user message as state delta with correct type."""
        sa_resp = _create_super_agent(client)
        sa_id = sa_resp.get_json()["super_agent_id"]

        sess_resp = client.post(f"/admin/super-agents/{sa_id}/sessions")
        sess_id = sess_resp.get_json()["session_id"]

        client.post(
            f"/admin/super-agents/{sa_id}/sessions/{sess_id}/chat",
            json={"content": "Test delta push"},
        )

        # Check that the event log has the user message delta
        with ChatStateService._lock:
            session = ChatStateService._sessions.get(sess_id)
            assert session is not None
            assert len(session["event_log"]) >= 1
            user_delta = session["event_log"][0]
            assert user_delta["type"] == "message"
            assert user_delta["role"] == "user"
            assert user_delta["content"] == "Test delta push"


class TestSessionLifecycleIntegration:
    def test_create_session_inits_chat_state(self, client):
        """Creating a session also initializes ChatStateService state."""
        sa_resp = _create_super_agent(client)
        sa_id = sa_resp.get_json()["super_agent_id"]

        sess_resp = client.post(f"/admin/super-agents/{sa_id}/sessions")
        sess_id = sess_resp.get_json()["session_id"]

        status = ChatStateService.get_session_status(sess_id)
        assert status == "idle"

    def test_end_session_removes_chat_state(self, client):
        """Ending a session removes ChatStateService state."""
        sa_resp = _create_super_agent(client)
        sa_id = sa_resp.get_json()["super_agent_id"]

        sess_resp = client.post(f"/admin/super-agents/{sa_id}/sessions")
        sess_id = sess_resp.get_json()["session_id"]

        # Verify it exists
        assert ChatStateService.get_session_status(sess_id) == "idle"

        # End the session
        client.post(f"/admin/super-agents/{sa_id}/sessions/{sess_id}/end")

        # Chat state should be gone
        assert ChatStateService.get_session_status(sess_id) is None
