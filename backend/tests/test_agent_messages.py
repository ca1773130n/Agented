"""Tests for inter-agent messaging CRUD, bus service, and route endpoints."""

import pytest

from app.db.messages import (
    add_agent_message,
    batch_add_broadcast_messages,
    expire_stale_messages,
    get_inbox_messages,
    get_outbox_messages,
    get_pending_messages,
    update_message_status,
)
from app.db.super_agents import add_super_agent
from app.services.agent_message_bus_service import AgentMessageBusService
from app.services.super_agent_session_service import SuperAgentSessionService


@pytest.fixture(autouse=True)
def clear_bus_state():
    """Clear message bus subscriber state between tests."""
    AgentMessageBusService._subscribers = {}
    SuperAgentSessionService._active_sessions = {}
    yield
    AgentMessageBusService._subscribers = {}
    SuperAgentSessionService._active_sessions = {}


def _make_agent(name="Agent-A"):
    """Helper to create a super agent directly via DB."""
    return add_super_agent(name=name, description=f"{name} description")


# =============================================================================
# CRUD tests
# =============================================================================


class TestAddMessage:
    def test_add_message(self, isolated_db):
        """add_agent_message returns a msg-* prefixed ID."""
        agent_a = _make_agent("Agent-A")
        agent_b = _make_agent("Agent-B")

        msg_id = add_agent_message(
            from_agent_id=agent_a,
            to_agent_id=agent_b,
            content="Hello from A",
        )
        assert msg_id is not None
        assert msg_id.startswith("msg-")


class TestGetInbox:
    def test_get_inbox(self, isolated_db):
        """get_inbox_messages returns messages to an agent with correct count."""
        agent_a = _make_agent("Agent-A")
        agent_b = _make_agent("Agent-B")

        add_agent_message(from_agent_id=agent_a, to_agent_id=agent_b, content="msg1")
        add_agent_message(from_agent_id=agent_a, to_agent_id=agent_b, content="msg2")
        add_agent_message(from_agent_id=agent_a, to_agent_id=agent_b, content="msg3")

        inbox = get_inbox_messages(agent_b)
        assert len(inbox) == 3
        # All messages should be present
        contents = {m["content"] for m in inbox}
        assert contents == {"msg1", "msg2", "msg3"}


class TestGetOutbox:
    def test_get_outbox(self, isolated_db):
        """get_outbox_messages returns messages from an agent."""
        agent_a = _make_agent("Agent-A")
        agent_b = _make_agent("Agent-B")

        add_agent_message(from_agent_id=agent_a, to_agent_id=agent_b, content="out1")
        add_agent_message(from_agent_id=agent_a, to_agent_id=agent_b, content="out2")
        add_agent_message(from_agent_id=agent_a, to_agent_id=agent_b, content="out3")

        outbox = get_outbox_messages(agent_a)
        assert len(outbox) == 3


class TestGetPending:
    def test_get_pending_priority_order(self, isolated_db):
        """get_pending_messages returns messages ordered by priority DESC then created_at ASC."""
        agent_a = _make_agent("Agent-A")
        agent_b = _make_agent("Agent-B")

        add_agent_message(from_agent_id=agent_a, to_agent_id=agent_b, content="low", priority="low")
        add_agent_message(
            from_agent_id=agent_a, to_agent_id=agent_b, content="normal", priority="normal"
        )
        add_agent_message(
            from_agent_id=agent_a, to_agent_id=agent_b, content="high", priority="high"
        )

        pending = get_pending_messages(agent_b)
        assert len(pending) == 3
        # High first, then normal, then low
        assert pending[0]["priority"] == "high"
        assert pending[1]["priority"] == "normal"
        assert pending[2]["priority"] == "low"


class TestUpdateStatusDelivered:
    def test_update_status_delivered(self, isolated_db):
        """update_message_status to 'delivered' sets delivered_at timestamp."""
        agent_a = _make_agent("Agent-A")
        agent_b = _make_agent("Agent-B")

        msg_id = add_agent_message(from_agent_id=agent_a, to_agent_id=agent_b, content="test")
        result = update_message_status(msg_id, "delivered")
        assert result is True

        # Verify delivered_at is set
        inbox = get_inbox_messages(agent_b)
        delivered_msg = [m for m in inbox if m["id"] == msg_id][0]
        assert delivered_msg["status"] == "delivered"
        assert delivered_msg["delivered_at"] is not None


class TestUpdateStatusRead:
    def test_update_status_read(self, isolated_db):
        """update_message_status to 'read' sets read_at timestamp."""
        agent_a = _make_agent("Agent-A")
        agent_b = _make_agent("Agent-B")

        msg_id = add_agent_message(from_agent_id=agent_a, to_agent_id=agent_b, content="test")
        update_message_status(msg_id, "delivered")
        result = update_message_status(msg_id, "read")
        assert result is True

        inbox = get_inbox_messages(agent_b)
        read_msg = [m for m in inbox if m["id"] == msg_id][0]
        assert read_msg["status"] == "read"
        assert read_msg["read_at"] is not None


class TestExpireStale:
    def test_expire_stale_messages(self, isolated_db):
        """expire_stale_messages marks past-expiry messages as expired."""
        agent_a = _make_agent("Agent-A")
        agent_b = _make_agent("Agent-B")

        # Create a message with expires_at in the past
        add_agent_message(
            from_agent_id=agent_a,
            to_agent_id=agent_b,
            content="will expire",
            expires_at="2020-01-01 00:00:00",
        )

        expired_count = expire_stale_messages()
        assert expired_count == 1


class TestInboxExcludesExpired:
    def test_inbox_excludes_expired(self, isolated_db):
        """get_inbox_messages does NOT return expired messages."""
        agent_a = _make_agent("Agent-A")
        agent_b = _make_agent("Agent-B")

        # Create an expired message
        add_agent_message(
            from_agent_id=agent_a,
            to_agent_id=agent_b,
            content="expired msg",
            expires_at="2020-01-01 00:00:00",
        )
        # Create a valid message
        add_agent_message(from_agent_id=agent_a, to_agent_id=agent_b, content="valid msg")

        inbox = get_inbox_messages(agent_b)
        assert len(inbox) == 1
        assert inbox[0]["content"] == "valid msg"


class TestBroadcast:
    def test_broadcast_creates_individual_rows(self, isolated_db):
        """Broadcast from one agent creates N-1 individual messages."""
        agent_a = _make_agent("Agent-A")
        agent_b = _make_agent("Agent-B")
        agent_c = _make_agent("Agent-C")

        msg_ids = batch_add_broadcast_messages(
            from_agent_id=agent_a,
            recipients=[agent_b, agent_c],
            content="broadcast content",
        )
        assert len(msg_ids) == 2

        # Check agent_b inbox
        inbox_b = get_inbox_messages(agent_b)
        assert len(inbox_b) == 1
        assert inbox_b[0]["content"] == "broadcast content"
        assert inbox_b[0]["message_type"] == "broadcast"

        # Check agent_c inbox
        inbox_c = get_inbox_messages(agent_c)
        assert len(inbox_c) == 1

        # Sender should have no inbox messages
        inbox_a = get_inbox_messages(agent_a)
        assert len(inbox_a) == 0


# =============================================================================
# Route tests
# =============================================================================


class TestSendMessageRoute:
    def test_send_message_route(self, client):
        """POST /messages creates a message and returns 201 with message_id."""
        # Create two super agents
        resp_a = client.post(
            "/admin/super-agents/", json={"name": "Agent-A", "description": "test"}
        )
        sa_a = resp_a.get_json()["super_agent_id"]

        resp_b = client.post(
            "/admin/super-agents/", json={"name": "Agent-B", "description": "test"}
        )
        sa_b = resp_b.get_json()["super_agent_id"]

        resp = client.post(
            f"/admin/super-agents/{sa_a}/messages",
            json={"to_agent_id": sa_b, "content": "Hello from A"},
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["message"] == "Message sent"
        assert body["message_id"].startswith("msg-")

    def test_send_message_empty_content(self, client):
        """POST /messages with empty content returns 400."""
        resp_a = client.post(
            "/admin/super-agents/", json={"name": "Agent-A", "description": "test"}
        )
        sa_a = resp_a.get_json()["super_agent_id"]

        resp = client.post(
            f"/admin/super-agents/{sa_a}/messages",
            json={"content": ""},
        )
        assert resp.status_code == 400


class TestInboxRoute:
    def test_inbox_route(self, client):
        """GET /messages/inbox returns messages array."""
        resp_a = client.post(
            "/admin/super-agents/", json={"name": "Agent-A", "description": "test"}
        )
        sa_a = resp_a.get_json()["super_agent_id"]

        resp_b = client.post(
            "/admin/super-agents/", json={"name": "Agent-B", "description": "test"}
        )
        sa_b = resp_b.get_json()["super_agent_id"]

        # Send a message from A to B
        client.post(
            f"/admin/super-agents/{sa_a}/messages",
            json={"to_agent_id": sa_b, "content": "Hello B"},
        )

        # Check B's inbox
        resp = client.get(f"/admin/super-agents/{sa_b}/messages/inbox")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["messages"]) >= 1
        assert body["messages"][0]["content"] == "Hello B"


class TestMarkReadRoute:
    def test_mark_read_route(self, client):
        """POST /messages/:id/read marks the message as read."""
        resp_a = client.post(
            "/admin/super-agents/", json={"name": "Agent-A", "description": "test"}
        )
        sa_a = resp_a.get_json()["super_agent_id"]

        resp_b = client.post(
            "/admin/super-agents/", json={"name": "Agent-B", "description": "test"}
        )
        sa_b = resp_b.get_json()["super_agent_id"]

        # Send message
        send_resp = client.post(
            f"/admin/super-agents/{sa_a}/messages",
            json={"to_agent_id": sa_b, "content": "Read me"},
        )
        msg_id = send_resp.get_json()["message_id"]

        # Mark as read
        resp = client.post(f"/admin/super-agents/{sa_b}/messages/{msg_id}/read")
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Message marked as read"

    def test_mark_read_not_found(self, client):
        """POST /messages/:id/read returns 404 for nonexistent message."""
        resp_a = client.post(
            "/admin/super-agents/", json={"name": "Agent-A", "description": "test"}
        )
        sa_a = resp_a.get_json()["super_agent_id"]

        resp = client.post(f"/admin/super-agents/{sa_a}/messages/msg-nonexist/read")
        assert resp.status_code == 404


class TestOutboxRoute:
    def test_outbox_route(self, client):
        """GET /messages/outbox returns messages from this agent."""
        resp_a = client.post(
            "/admin/super-agents/", json={"name": "Agent-A", "description": "test"}
        )
        sa_a = resp_a.get_json()["super_agent_id"]

        resp_b = client.post(
            "/admin/super-agents/", json={"name": "Agent-B", "description": "test"}
        )
        sa_b = resp_b.get_json()["super_agent_id"]

        # Send messages from A
        client.post(
            f"/admin/super-agents/{sa_a}/messages",
            json={"to_agent_id": sa_b, "content": "msg1"},
        )

        # Check A's outbox
        resp = client.get(f"/admin/super-agents/{sa_a}/messages/outbox")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["messages"]) == 1


class TestPromptInjection:
    def test_prompt_includes_pending_messages(self, client):
        """assemble_system_prompt includes Pending Messages section for unread messages."""
        # Create two super agents
        resp_a = client.post(
            "/admin/super-agents/", json={"name": "Agent-A", "description": "test"}
        )
        sa_a = resp_a.get_json()["super_agent_id"]

        resp_b = client.post(
            "/admin/super-agents/", json={"name": "Agent-B", "description": "test"}
        )
        sa_b = resp_b.get_json()["super_agent_id"]

        # Send a pending message from A to B
        add_agent_message(
            from_agent_id=sa_a,
            to_agent_id=sa_b,
            subject="Task Update",
            content="Deployment complete",
            priority="high",
        )

        # Create a session for B to assemble prompt
        session_id, _ = SuperAgentSessionService.create_session(sa_b)

        prompt = SuperAgentSessionService.assemble_system_prompt(sa_b, session_id)

        assert "## Pending Messages" in prompt
        assert "[HIGH]" in prompt
        assert "Task Update" in prompt
        assert "Deployment complete" in prompt
