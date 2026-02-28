"""Tests for SuperAgent Session API endpoints and SuperAgentSessionService."""

import json

import pytest

from app.services.super_agent_session_service import SuperAgentSessionService

SAMPLE_SUPER_AGENT = {
    "name": "DevOps Lead",
    "description": "Handles infrastructure automation",
    "backend_type": "claude",
    "max_concurrent_sessions": 5,
}


@pytest.fixture(autouse=True)
def clear_active_sessions():
    """Clear in-memory session state between tests."""
    SuperAgentSessionService._active_sessions = {}
    yield
    SuperAgentSessionService._active_sessions = {}


def _create_super_agent(client, **overrides):
    """Helper to create a super agent via API."""
    data = {**SAMPLE_SUPER_AGENT, **overrides}
    return client.post("/admin/super-agents/", json=data)


def _create_session(client, super_agent_id):
    """Helper to create a session via API."""
    return client.post(f"/admin/super-agents/{super_agent_id}/sessions")


class TestCreateSession:
    def test_create_session(self, client):
        """POST creates a session and returns 201 with sess-* ID."""
        sa_resp = _create_super_agent(client)
        sa_id = sa_resp.get_json()["super_agent_id"]

        resp = _create_session(client, sa_id)
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["message"] == "Session created"
        assert body["session_id"].startswith("sess-")


class TestListSessions:
    def test_list_sessions(self, client):
        """GET /sessions returns all sessions for a super agent."""
        sa_resp = _create_super_agent(client)
        sa_id = sa_resp.get_json()["super_agent_id"]

        _create_session(client, sa_id)
        _create_session(client, sa_id)

        resp = client.get(f"/admin/super-agents/{sa_id}/sessions")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["sessions"]) == 2


class TestGetSession:
    def test_get_session(self, client):
        """GET /sessions/:id returns session with all fields."""
        sa_resp = _create_super_agent(client)
        sa_id = sa_resp.get_json()["super_agent_id"]

        sess_resp = _create_session(client, sa_id)
        sess_id = sess_resp.get_json()["session_id"]

        resp = client.get(f"/admin/super-agents/{sa_id}/sessions/{sess_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["id"] == sess_id
        assert body["super_agent_id"] == sa_id
        assert body["status"] == "active"
        assert body["token_count"] == 0
        assert "started_at" in body


class TestSendMessage:
    def test_send_message(self, client):
        """POST /message updates conversation_log and returns 200."""
        sa_resp = _create_super_agent(client)
        sa_id = sa_resp.get_json()["super_agent_id"]

        sess_resp = _create_session(client, sa_id)
        sess_id = sess_resp.get_json()["session_id"]

        resp = client.post(
            f"/admin/super-agents/{sa_id}/sessions/{sess_id}/message",
            json={"message": "Hello, world!"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Message sent"

        # Verify conversation_log updated in DB
        get_resp = client.get(f"/admin/super-agents/{sa_id}/sessions/{sess_id}")
        body = get_resp.get_json()
        log = json.loads(body["conversation_log"])
        assert len(log) == 1
        assert log[0]["role"] == "user"
        assert log[0]["content"] == "Hello, world!"


class TestEndSession:
    def test_end_session(self, client):
        """POST /end sets status=completed and ended_at."""
        sa_resp = _create_super_agent(client)
        sa_id = sa_resp.get_json()["super_agent_id"]

        sess_resp = _create_session(client, sa_id)
        sess_id = sess_resp.get_json()["session_id"]

        resp = client.post(f"/admin/super-agents/{sa_id}/sessions/{sess_id}/end")
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Session ended"

        # Verify status and ended_at in DB
        get_resp = client.get(f"/admin/super-agents/{sa_id}/sessions/{sess_id}")
        body = get_resp.get_json()
        assert body["status"] == "completed"
        assert body["ended_at"] is not None


class TestSessionWithoutAgent:
    def test_session_without_agent(self, client):
        """POST session for nonexistent agent returns error."""
        resp = client.post("/admin/super-agents/super-nonexist/sessions")
        assert resp.status_code == 404
        body = resp.get_json()
        assert "not found" in body["error"].lower()


class TestConcurrentSessionLimit:
    def test_concurrent_session_limit(self, client):
        """Creating 10 sessions succeeds; 11th returns error."""
        sa_resp = _create_super_agent(client)
        sa_id = sa_resp.get_json()["super_agent_id"]

        # Create 10 sessions (should all succeed)
        for i in range(10):
            session_id, error = SuperAgentSessionService.create_session(sa_id)
            assert session_id is not None, f"Session {i + 1} failed: {error}"
            assert error is None

        # 11th should fail
        session_id, error = SuperAgentSessionService.create_session(sa_id)
        assert session_id is None
        assert "Maximum concurrent sessions reached" in error


class TestTokenCounting:
    def test_token_counting(self, client):
        """Sending messages increases token_count."""
        sa_resp = _create_super_agent(client)
        sa_id = sa_resp.get_json()["super_agent_id"]

        sess_resp = _create_session(client, sa_id)
        sess_id = sess_resp.get_json()["session_id"]

        # Send a message with known content
        message = "A" * 400  # 400 chars / 4 = 100 tokens
        client.post(
            f"/admin/super-agents/{sa_id}/sessions/{sess_id}/message",
            json={"message": message},
        )

        # Verify token count increased
        get_resp = client.get(f"/admin/super-agents/{sa_id}/sessions/{sess_id}")
        body = get_resp.get_json()
        assert body["token_count"] == 100

        # Send another message
        client.post(
            f"/admin/super-agents/{sa_id}/sessions/{sess_id}/message",
            json={"message": message},
        )

        get_resp = client.get(f"/admin/super-agents/{sa_id}/sessions/{sess_id}")
        body = get_resp.get_json()
        assert body["token_count"] == 200


class TestCompactionTrigger:
    def test_compaction_trigger(self, client):
        """Sending enough messages to exceed 80k tokens triggers compaction."""
        sa_resp = _create_super_agent(client)
        sa_id = sa_resp.get_json()["super_agent_id"]

        session_id, _ = SuperAgentSessionService.create_session(sa_id)

        # Each message: 4000 chars = 1000 tokens. Need >80 messages to exceed 80k tokens.
        # After compaction at message 81 (81k tokens > 80k threshold), we keep 10 messages
        # plus a summary. Messages 82-85 are appended after compaction.
        big_message = "X" * 4000
        for _ in range(85):
            SuperAgentSessionService.send_message(session_id, big_message)

        # After compaction, conversation_log should be much smaller than 85
        state = SuperAgentSessionService.get_session_state(session_id)
        assert state is not None
        # Compaction keeps last 10 messages, then 4 more are appended after
        assert len(state["conversation_log"]) < 85
        assert state["summary"] is not None
        assert "Summary of prior conversation" in state["summary"]
        # Token count should be recalculated and much less than 85000
        assert state["token_count"] < 85000


class TestSystemPromptAssembly:
    def test_system_prompt_assembly(self, client):
        """System prompt includes all 4 document types."""
        sa_resp = _create_super_agent(client)
        sa_id = sa_resp.get_json()["super_agent_id"]

        # Create one document of each type
        for doc_type, content in [
            ("SOUL", "I am a helpful AI assistant."),
            ("IDENTITY", "My name is DevOps Lead."),
            ("MEMORY", "I remember deploying v2.0."),
            ("ROLE", "I manage infrastructure."),
        ]:
            client.post(
                f"/admin/super-agents/{sa_id}/documents",
                json={"doc_type": doc_type, "title": f"{doc_type} doc", "content": content},
            )

        # Create a session
        session_id, _ = SuperAgentSessionService.create_session(sa_id)

        # Assemble system prompt
        prompt = SuperAgentSessionService.assemble_system_prompt(sa_id, session_id)

        # Verify all 4 doc types are present
        assert "## SOUL" in prompt
        assert "I am a helpful AI assistant." in prompt
        assert "## IDENTITY" in prompt
        assert "My name is DevOps Lead." in prompt
        assert "## MEMORY" in prompt
        assert "I remember deploying v2.0." in prompt
        assert "## ROLE" in prompt
        assert "I manage infrastructure." in prompt


class TestRingBufferCap:
    def test_ring_buffer_cap(self, client):
        """Output buffer is capped at 1000 lines."""
        sa_resp = _create_super_agent(client)
        sa_id = sa_resp.get_json()["super_agent_id"]

        session_id, _ = SuperAgentSessionService.create_session(sa_id)

        # Manually add >1000 lines to the output buffer
        session = SuperAgentSessionService._active_sessions[session_id]
        for i in range(1200):
            session["output_buffer"].append(f"line {i}")

        # Verify only 1000 retained
        lines = SuperAgentSessionService.get_output_lines(session_id)
        assert len(lines) == 1000
        # Should have the most recent 1000 lines (200 through 1199)
        assert lines[0] == "line 200"
        assert lines[-1] == "line 1199"


class TestSessionCascadeDelete:
    def test_session_cascade_delete(self, client):
        """Deleting a super agent cascade-deletes its sessions."""
        sa_resp = _create_super_agent(client)
        sa_id = sa_resp.get_json()["super_agent_id"]

        sess_resp = _create_session(client, sa_id)
        sess_id = sess_resp.get_json()["session_id"]

        # Delete the super agent
        client.delete(f"/admin/super-agents/{sa_id}")

        # Session should be gone from DB
        get_resp = client.get(f"/admin/super-agents/{sa_id}/sessions/{sess_id}")
        assert get_resp.status_code == 404
