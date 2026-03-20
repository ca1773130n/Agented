"""Comprehensive scenario tests for all conversation-related routes.

Covers: agent conversations, command conversations, hook conversations,
plugin conversations, rule conversations, skill conversations,
conversation branches, super agent chat, super agent messages,
and super agent sessions.
"""

import json
import time
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_super_agent(client, name="Test SA", backend_type="claude"):
    """Create a super agent and return its ID."""
    resp = client.post(
        "/admin/super-agents/",
        json={"name": name, "backend_type": backend_type},
    )
    assert resp.status_code == 201
    return resp.get_json()["super_agent_id"]


def _create_agent(client, name="Test Agent"):
    """Create an agent and return its ID."""
    resp = client.post(
        "/admin/agents/",
        json={"name": name, "description": "test agent", "backend_type": "claude"},
    )
    assert resp.status_code == 201
    return resp.get_json()["agent"]["id"]


def _create_agent_conversation(client):
    """Start an agent conversation and return its conv_id."""
    resp = client.post("/api/agents/conversations/start")
    assert resp.status_code == 201
    body = resp.get_json()
    assert "conversation_id" in body
    return body["conversation_id"]


def _mock_stream_llm(*args, **kwargs):
    """Mock stream_llm_response to yield deterministic chunks."""
    yield "Hello, "
    yield "I can help you."


def _mock_stream_llm_with_agent_config(*args, **kwargs):
    """Mock that yields an agent config block."""
    yield '---AGENT_CONFIG---\n{"name": "Test Bot", "description": "A test agent", "role": "tester", "goals": ["test"], "skills": ["code"], "context": "testing"}\n---END_CONFIG---'


# ---------------------------------------------------------------------------
# 1. Agent Conversations
# ---------------------------------------------------------------------------


class TestAgentConversations:
    """Tests for /api/agents/conversations/* endpoints."""

    def test_start_conversation(self, client):
        """POST /api/agents/conversations/start creates a new conversation."""
        resp = client.post("/api/agents/conversations/start")
        assert resp.status_code == 201
        body = resp.get_json()
        assert "conversation_id" in body
        assert body["conversation_id"].startswith("conv-")

    def test_get_conversation(self, client):
        """GET /api/agents/conversations/<conv_id> returns conversation details."""
        conv_id = _create_agent_conversation(client)
        resp = client.get(f"/api/agents/conversations/{conv_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["id"] == conv_id

    def test_get_conversation_not_found(self, client):
        """GET with invalid conv_id returns 404."""
        resp = client.get("/api/agents/conversations/conv-nonexistent")
        assert resp.status_code == 404

    @patch(
        "app.services.agent_conversation_service.stream_llm_response",
        side_effect=_mock_stream_llm,
    )
    def test_send_message(self, mock_llm, client):
        """POST /api/agents/conversations/<conv_id>/message sends a message."""
        conv_id = _create_agent_conversation(client)
        resp = client.post(
            f"/api/agents/conversations/{conv_id}/message",
            json={"message": "I want to create a code review agent"},
        )
        assert resp.status_code == 202
        body = resp.get_json()
        assert body["status"] == "processing"
        assert "message_id" in body

    def test_send_message_missing_body(self, client):
        """POST message without message field returns 400."""
        conv_id = _create_agent_conversation(client)
        resp = client.post(
            f"/api/agents/conversations/{conv_id}/message",
            json={"not_message": "hello"},
        )
        assert resp.status_code == 400

    def test_send_message_conversation_not_found(self, client):
        """POST message to non-existent conversation returns 404."""
        resp = client.post(
            "/api/agents/conversations/conv-nonexistent/message",
            json={"message": "hello"},
        )
        assert resp.status_code == 404

    def test_stream_conversation(self, client):
        """GET /api/agents/conversations/<conv_id>/stream returns SSE stream."""
        conv_id = _create_agent_conversation(client)
        resp = client.get(f"/api/agents/conversations/{conv_id}/stream")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/event-stream")

    def test_stream_conversation_not_found(self, client):
        """GET stream for non-existent conversation yields error event."""
        resp = client.get("/api/agents/conversations/conv-nonexistent/stream")
        assert resp.status_code == 200
        data = resp.get_data(as_text=True)
        assert "error" in data

    def test_finalize_no_config(self, client):
        """POST /api/agents/conversations/<conv_id>/finalize without config returns 400."""
        conv_id = _create_agent_conversation(client)
        resp = client.post(f"/api/agents/conversations/{conv_id}/finalize")
        assert resp.status_code == 400

    def test_finalize_not_found(self, client):
        """POST finalize for non-existent conversation returns 404."""
        resp = client.post("/api/agents/conversations/conv-nonexistent/finalize")
        assert resp.status_code == 404

    def test_abandon_conversation(self, client):
        """POST /api/agents/conversations/<conv_id>/abandon marks conversation abandoned."""
        conv_id = _create_agent_conversation(client)
        resp = client.post(f"/api/agents/conversations/{conv_id}/abandon")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["message"] == "Conversation abandoned"

    def test_abandon_not_found(self, client):
        """POST abandon for non-existent conversation returns 404."""
        resp = client.post("/api/agents/conversations/conv-nonexistent/abandon")
        assert resp.status_code == 404

    @patch(
        "app.services.agent_conversation_service.stream_llm_response",
        side_effect=_mock_stream_llm_with_agent_config,
    )
    def test_finalize_with_config(self, mock_llm, client):
        """POST finalize creates agent when config is present in conversation."""
        conv_id = _create_agent_conversation(client)
        # Send a message so Claude generates a config
        resp = client.post(
            f"/api/agents/conversations/{conv_id}/message",
            json={"message": "Please create the agent now"},
        )
        assert resp.status_code == 202
        # Wait for background thread
        time.sleep(0.5)
        # Now finalize
        resp = client.post(f"/api/agents/conversations/{conv_id}/finalize")
        assert resp.status_code == 201
        body = resp.get_json()
        assert "agent_id" in body
        assert body["agent_id"].startswith("agent-")


# ---------------------------------------------------------------------------
# 2. Command Conversations (BaseConversationService)
# ---------------------------------------------------------------------------


class TestCommandConversations:
    """Tests for /api/commands/conversations/* endpoints."""

    @patch(
        "app.services.conversation_streaming.stream_llm_response",
        side_effect=_mock_stream_llm,
    )
    def test_start_conversation(self, mock_llm, client):
        """POST /api/commands/conversations/start creates a conversation."""
        resp = client.post("/api/commands/conversations/start")
        assert resp.status_code == 201
        body = resp.get_json()
        assert "conversation_id" in body
        assert body["conversation_id"].startswith("cmd_")

    @patch(
        "app.services.conversation_streaming.stream_llm_response",
        side_effect=_mock_stream_llm,
    )
    def test_list_conversations(self, mock_llm, client):
        """GET /api/commands/conversations/ lists active conversations."""
        resp = client.get("/api/commands/conversations/")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "conversations" in body

    @patch(
        "app.services.conversation_streaming.stream_llm_response",
        side_effect=_mock_stream_llm,
    )
    def test_get_conversation(self, mock_llm, client):
        """GET /api/commands/conversations/<conv_id> returns conversation."""
        start_resp = client.post("/api/commands/conversations/start")
        conv_id = start_resp.get_json()["conversation_id"]
        resp = client.get(f"/api/commands/conversations/{conv_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["id"] == conv_id

    def test_get_conversation_not_found(self, client):
        """GET non-existent command conversation returns 404."""
        resp = client.get("/api/commands/conversations/cmd_nonexistent")
        assert resp.status_code == 404

    @patch(
        "app.services.conversation_streaming.stream_llm_response",
        side_effect=_mock_stream_llm,
    )
    def test_send_message(self, mock_llm, client):
        """POST message to command conversation."""
        start_resp = client.post("/api/commands/conversations/start")
        conv_id = start_resp.get_json()["conversation_id"]
        time.sleep(0.3)  # Wait for initial _process_with_claude
        resp = client.post(
            f"/api/commands/conversations/{conv_id}/message",
            json={"message": "Create a deploy command"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "processing"

    def test_send_message_missing_body(self, client):
        """POST message without message field returns 400."""
        resp = client.post(
            "/api/commands/conversations/cmd_fake/message",
            json={"no_message": "test"},
        )
        assert resp.status_code == 400

    @patch(
        "app.services.conversation_streaming.stream_llm_response",
        side_effect=_mock_stream_llm,
    )
    def test_stream_conversation(self, mock_llm, client):
        """GET /api/commands/conversations/<conv_id>/stream returns SSE."""
        start_resp = client.post("/api/commands/conversations/start")
        conv_id = start_resp.get_json()["conversation_id"]
        resp = client.get(f"/api/commands/conversations/{conv_id}/stream")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/event-stream")

    def test_finalize_not_found(self, client):
        """POST finalize for non-existent conversation returns 404."""
        resp = client.post("/api/commands/conversations/cmd_nonexistent/finalize")
        assert resp.status_code == 404

    @patch(
        "app.services.conversation_streaming.stream_llm_response",
        side_effect=_mock_stream_llm,
    )
    def test_abandon_conversation(self, mock_llm, client):
        """POST abandon marks command conversation as abandoned."""
        start_resp = client.post("/api/commands/conversations/start")
        conv_id = start_resp.get_json()["conversation_id"]
        resp = client.post(f"/api/commands/conversations/{conv_id}/abandon")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["message"] == "Conversation abandoned"

    def test_abandon_not_found(self, client):
        """POST abandon for non-existent command conversation returns 404."""
        resp = client.post("/api/commands/conversations/cmd_nonexistent/abandon")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 3. Hook Conversations (BaseConversationService)
# ---------------------------------------------------------------------------


class TestHookConversations:
    """Tests for /api/hooks/conversations/* endpoints."""

    @patch(
        "app.services.conversation_streaming.stream_llm_response",
        side_effect=_mock_stream_llm,
    )
    def test_start_conversation(self, mock_llm, client):
        """POST /api/hooks/conversations/start creates a conversation."""
        resp = client.post("/api/hooks/conversations/start")
        assert resp.status_code == 201
        body = resp.get_json()
        assert "conversation_id" in body
        assert body["conversation_id"].startswith("hook_")

    @patch(
        "app.services.conversation_streaming.stream_llm_response",
        side_effect=_mock_stream_llm,
    )
    def test_list_conversations(self, mock_llm, client):
        """GET /api/hooks/conversations/ lists active hook conversations."""
        resp = client.get("/api/hooks/conversations/")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "conversations" in body

    @patch(
        "app.services.conversation_streaming.stream_llm_response",
        side_effect=_mock_stream_llm,
    )
    def test_get_conversation(self, mock_llm, client):
        """GET a specific hook conversation."""
        start_resp = client.post("/api/hooks/conversations/start")
        conv_id = start_resp.get_json()["conversation_id"]
        resp = client.get(f"/api/hooks/conversations/{conv_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["id"] == conv_id

    def test_get_conversation_not_found(self, client):
        """GET non-existent hook conversation returns 404."""
        resp = client.get("/api/hooks/conversations/hook_nonexistent")
        assert resp.status_code == 404

    @patch(
        "app.services.conversation_streaming.stream_llm_response",
        side_effect=_mock_stream_llm,
    )
    def test_send_message(self, mock_llm, client):
        """POST message to hook conversation."""
        start_resp = client.post("/api/hooks/conversations/start")
        conv_id = start_resp.get_json()["conversation_id"]
        time.sleep(0.3)
        resp = client.post(
            f"/api/hooks/conversations/{conv_id}/message",
            json={"message": "Create a pre-tool-use hook"},
        )
        assert resp.status_code == 200

    def test_send_message_missing_body(self, client):
        """POST message without message field returns 400."""
        resp = client.post(
            "/api/hooks/conversations/hook_fake/message",
            json={},
        )
        assert resp.status_code == 400

    @patch(
        "app.services.conversation_streaming.stream_llm_response",
        side_effect=_mock_stream_llm,
    )
    def test_abandon_conversation(self, mock_llm, client):
        """POST abandon marks hook conversation as abandoned."""
        start_resp = client.post("/api/hooks/conversations/start")
        conv_id = start_resp.get_json()["conversation_id"]
        resp = client.post(f"/api/hooks/conversations/{conv_id}/abandon")
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Conversation abandoned"

    def test_finalize_not_found(self, client):
        """POST finalize for non-existent hook conversation returns 404."""
        resp = client.post("/api/hooks/conversations/hook_nonexistent/finalize")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 4. Plugin Conversations (standalone service)
# ---------------------------------------------------------------------------


class TestPluginConversations:
    """Tests for /api/plugins/conversations/* endpoints."""

    @patch(
        "app.services.conversation_streaming.stream_llm_response",
        side_effect=_mock_stream_llm,
    )
    def test_start_conversation(self, mock_llm, client):
        """POST /api/plugins/conversations/start creates a conversation."""
        resp = client.post("/api/plugins/conversations/start")
        assert resp.status_code == 201
        body = resp.get_json()
        assert "conversation_id" in body
        assert body["conversation_id"].startswith("plugin_")

    @patch(
        "app.services.conversation_streaming.stream_llm_response",
        side_effect=_mock_stream_llm,
    )
    def test_get_conversation(self, mock_llm, client):
        """GET /api/plugins/conversations/<conv_id> returns conversation."""
        start_resp = client.post("/api/plugins/conversations/start")
        conv_id = start_resp.get_json()["conversation_id"]
        resp = client.get(f"/api/plugins/conversations/{conv_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["id"] == conv_id

    def test_get_conversation_not_found(self, client):
        """GET non-existent plugin conversation returns 404."""
        resp = client.get("/api/plugins/conversations/plugin_nonexistent")
        assert resp.status_code == 404

    @patch(
        "app.services.conversation_streaming.stream_llm_response",
        side_effect=_mock_stream_llm,
    )
    def test_send_message(self, mock_llm, client):
        """POST message to plugin conversation."""
        start_resp = client.post("/api/plugins/conversations/start")
        conv_id = start_resp.get_json()["conversation_id"]
        time.sleep(0.3)
        resp = client.post(
            f"/api/plugins/conversations/{conv_id}/message",
            json={"message": "I want a code quality plugin"},
        )
        # May be 200 (OK) or 409 (CONFLICT) if still processing initial greeting
        assert resp.status_code in (200, 202, 409)

    def test_send_message_missing_body(self, client):
        """POST message without message field returns 400."""
        resp = client.post(
            "/api/plugins/conversations/plugin_fake/message",
            json={"other": "data"},
        )
        assert resp.status_code == 400

    @patch(
        "app.services.conversation_streaming.stream_llm_response",
        side_effect=_mock_stream_llm,
    )
    def test_stream_conversation(self, mock_llm, client):
        """GET /api/plugins/conversations/<conv_id>/stream returns SSE."""
        start_resp = client.post("/api/plugins/conversations/start")
        conv_id = start_resp.get_json()["conversation_id"]
        resp = client.get(f"/api/plugins/conversations/{conv_id}/stream")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/event-stream")

    def test_finalize_not_found(self, client):
        """POST finalize for non-existent plugin conversation returns 404."""
        resp = client.post("/api/plugins/conversations/plugin_nonexistent/finalize")
        assert resp.status_code == 404

    @patch(
        "app.services.conversation_streaming.stream_llm_response",
        side_effect=_mock_stream_llm,
    )
    def test_abandon_conversation(self, mock_llm, client):
        """POST abandon marks plugin conversation as abandoned."""
        start_resp = client.post("/api/plugins/conversations/start")
        conv_id = start_resp.get_json()["conversation_id"]
        resp = client.post(f"/api/plugins/conversations/{conv_id}/abandon")
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Conversation abandoned"

    def test_abandon_not_found(self, client):
        """POST abandon for non-existent plugin conversation returns 404."""
        resp = client.post("/api/plugins/conversations/plugin_nonexistent/abandon")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 5. Rule Conversations (BaseConversationService)
# ---------------------------------------------------------------------------


class TestRuleConversations:
    """Tests for /api/rules/conversations/* endpoints."""

    @patch(
        "app.services.conversation_streaming.stream_llm_response",
        side_effect=_mock_stream_llm,
    )
    def test_start_conversation(self, mock_llm, client):
        """POST /api/rules/conversations/start creates a conversation."""
        resp = client.post("/api/rules/conversations/start")
        assert resp.status_code == 201
        body = resp.get_json()
        assert "conversation_id" in body
        assert body["conversation_id"].startswith("rule_")

    @patch(
        "app.services.conversation_streaming.stream_llm_response",
        side_effect=_mock_stream_llm,
    )
    def test_list_conversations(self, mock_llm, client):
        """GET /api/rules/conversations/ lists active rule conversations."""
        resp = client.get("/api/rules/conversations/")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "conversations" in body

    @patch(
        "app.services.conversation_streaming.stream_llm_response",
        side_effect=_mock_stream_llm,
    )
    def test_get_conversation(self, mock_llm, client):
        """GET a specific rule conversation."""
        start_resp = client.post("/api/rules/conversations/start")
        conv_id = start_resp.get_json()["conversation_id"]
        resp = client.get(f"/api/rules/conversations/{conv_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["id"] == conv_id

    def test_get_conversation_not_found(self, client):
        """GET non-existent rule conversation returns 404."""
        resp = client.get("/api/rules/conversations/rule_nonexistent")
        assert resp.status_code == 404

    @patch(
        "app.services.conversation_streaming.stream_llm_response",
        side_effect=_mock_stream_llm,
    )
    def test_send_message(self, mock_llm, client):
        """POST message to rule conversation."""
        start_resp = client.post("/api/rules/conversations/start")
        conv_id = start_resp.get_json()["conversation_id"]
        time.sleep(0.3)
        resp = client.post(
            f"/api/rules/conversations/{conv_id}/message",
            json={"message": "Create a validation rule"},
        )
        assert resp.status_code == 200

    def test_send_message_missing_body(self, client):
        """POST message without message field returns 400."""
        resp = client.post(
            "/api/rules/conversations/rule_fake/message",
            json={"bad": "data"},
        )
        assert resp.status_code == 400

    @patch(
        "app.services.conversation_streaming.stream_llm_response",
        side_effect=_mock_stream_llm,
    )
    def test_abandon_conversation(self, mock_llm, client):
        """POST abandon marks rule conversation as abandoned."""
        start_resp = client.post("/api/rules/conversations/start")
        conv_id = start_resp.get_json()["conversation_id"]
        resp = client.post(f"/api/rules/conversations/{conv_id}/abandon")
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Conversation abandoned"

    def test_finalize_not_found(self, client):
        """POST finalize for non-existent rule conversation returns 404."""
        resp = client.post("/api/rules/conversations/rule_nonexistent/finalize")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 6. Skill Conversations (standalone service)
# ---------------------------------------------------------------------------


class TestSkillConversations:
    """Tests for /api/skills/conversations/* endpoints."""

    @patch(
        "app.services.conversation_streaming.stream_llm_response",
        side_effect=_mock_stream_llm,
    )
    def test_start_conversation(self, mock_llm, client):
        """POST /api/skills/conversations/start creates a conversation."""
        resp = client.post("/api/skills/conversations/start")
        assert resp.status_code == 201
        body = resp.get_json()
        assert "conversation_id" in body
        assert body["conversation_id"].startswith("skill_")

    @patch(
        "app.services.conversation_streaming.stream_llm_response",
        side_effect=_mock_stream_llm,
    )
    def test_get_conversation(self, mock_llm, client):
        """GET /api/skills/conversations/<conv_id> returns conversation."""
        start_resp = client.post("/api/skills/conversations/start")
        conv_id = start_resp.get_json()["conversation_id"]
        resp = client.get(f"/api/skills/conversations/{conv_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["id"] == conv_id

    def test_get_conversation_not_found(self, client):
        """GET non-existent skill conversation returns 404."""
        resp = client.get("/api/skills/conversations/skill_nonexistent")
        assert resp.status_code == 404

    @patch(
        "app.services.conversation_streaming.stream_llm_response",
        side_effect=_mock_stream_llm,
    )
    def test_send_message(self, mock_llm, client):
        """POST message to skill conversation."""
        start_resp = client.post("/api/skills/conversations/start")
        conv_id = start_resp.get_json()["conversation_id"]
        time.sleep(0.3)
        resp = client.post(
            f"/api/skills/conversations/{conv_id}/message",
            json={"message": "I want a test generator skill"},
        )
        assert resp.status_code in (200, 202, 409)

    def test_send_message_missing_body(self, client):
        """POST message without message field returns 400."""
        resp = client.post(
            "/api/skills/conversations/skill_fake/message",
            json={"foo": "bar"},
        )
        assert resp.status_code == 400

    @patch(
        "app.services.conversation_streaming.stream_llm_response",
        side_effect=_mock_stream_llm,
    )
    def test_stream_conversation(self, mock_llm, client):
        """GET /api/skills/conversations/<conv_id>/stream returns SSE."""
        start_resp = client.post("/api/skills/conversations/start")
        conv_id = start_resp.get_json()["conversation_id"]
        resp = client.get(f"/api/skills/conversations/{conv_id}/stream")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/event-stream")

    def test_finalize_not_found(self, client):
        """POST finalize for non-existent skill conversation returns 404."""
        resp = client.post("/api/skills/conversations/skill_nonexistent/finalize")
        assert resp.status_code == 404

    @patch(
        "app.services.conversation_streaming.stream_llm_response",
        side_effect=_mock_stream_llm,
    )
    def test_abandon_conversation(self, mock_llm, client):
        """POST abandon marks skill conversation as abandoned."""
        start_resp = client.post("/api/skills/conversations/start")
        conv_id = start_resp.get_json()["conversation_id"]
        resp = client.post(f"/api/skills/conversations/{conv_id}/abandon")
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Conversation abandoned"

    def test_abandon_not_found(self, client):
        """POST abandon for non-existent skill conversation returns 404."""
        resp = client.post("/api/skills/conversations/skill_nonexistent/abandon")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 7. Conversation Branches
# ---------------------------------------------------------------------------


class TestConversationBranches:
    """Tests for /admin/conversations/<conversation_id>/branches/* endpoints."""

    def _create_conversation_with_messages(self, client):
        """Create an agent conversation with messages for branching."""
        conv_id = _create_agent_conversation(client)
        # The conversation already has system message. We need to add messages
        # via the DB to have content to branch from.
        from app.database import update_agent_conversation

        messages = json.dumps(
            [
                {
                    "role": "system",
                    "content": "You are helpful.",
                    "timestamp": "2025-01-01T00:00:00",
                },
                {"role": "user", "content": "Hello", "timestamp": "2025-01-01T00:01:00"},
                {"role": "assistant", "content": "Hi there!", "timestamp": "2025-01-01T00:02:00"},
                {"role": "user", "content": "Help me", "timestamp": "2025-01-01T00:03:00"},
            ]
        )
        update_agent_conversation(conv_id, messages=messages)
        return conv_id

    def test_create_branch(self, client):
        """POST /admin/conversations/<conv_id>/branches creates a branch."""
        conv_id = self._create_conversation_with_messages(client)
        resp = client.post(
            f"/admin/conversations/{conv_id}/branches",
            json={"fork_message_index": 1, "name": "alternative"},
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert "id" in body or "branch_id" in body

    def test_create_branch_missing_index(self, client):
        """POST create branch without fork_message_index returns 400."""
        conv_id = self._create_conversation_with_messages(client)
        resp = client.post(
            f"/admin/conversations/{conv_id}/branches",
            json={"name": "test"},
        )
        assert resp.status_code == 400

    def test_create_branch_invalid_index(self, client):
        """POST create branch with non-integer fork_message_index returns 400."""
        conv_id = self._create_conversation_with_messages(client)
        resp = client.post(
            f"/admin/conversations/{conv_id}/branches",
            json={"fork_message_index": "not-a-number"},
        )
        assert resp.status_code == 400

    def test_create_branch_index_out_of_bounds(self, client):
        """POST create branch with out-of-bounds index returns 400."""
        conv_id = self._create_conversation_with_messages(client)
        resp = client.post(
            f"/admin/conversations/{conv_id}/branches",
            json={"fork_message_index": 100},
        )
        assert resp.status_code == 400

    def test_create_branch_conversation_not_found(self, client):
        """POST create branch for non-existent conversation returns 404."""
        resp = client.post(
            "/admin/conversations/conv-nonexistent/branches",
            json={"fork_message_index": 0},
        )
        assert resp.status_code == 404

    def test_list_branches_empty(self, client):
        """GET /admin/conversations/<conv_id>/branches returns empty list."""
        conv_id = self._create_conversation_with_messages(client)
        resp = client.get(f"/admin/conversations/{conv_id}/branches")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["branches"] == []
        assert body["total"] == 0

    def test_list_branches_after_create(self, client):
        """GET branches after creating one returns the branch."""
        conv_id = self._create_conversation_with_messages(client)
        client.post(
            f"/admin/conversations/{conv_id}/branches",
            json={"fork_message_index": 2, "name": "explore"},
        )
        resp = client.get(f"/admin/conversations/{conv_id}/branches")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["total"] >= 1

    def test_get_branch_tree(self, client):
        """GET /admin/conversations/<conv_id>/branches/tree returns tree structure."""
        conv_id = self._create_conversation_with_messages(client)
        resp = client.get(f"/admin/conversations/{conv_id}/branches/tree")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["conversation_id"] == conv_id
        assert "branches" in body

    def test_get_branch_messages(self, client):
        """GET /admin/branches/<branch_id>/messages returns branch messages."""
        conv_id = self._create_conversation_with_messages(client)
        create_resp = client.post(
            f"/admin/conversations/{conv_id}/branches",
            json={"fork_message_index": 2, "name": "branch1"},
        )
        assert create_resp.status_code == 201
        branch = create_resp.get_json()
        branch_id = branch.get("id") or branch.get("branch_id")

        resp = client.get(f"/admin/branches/{branch_id}/messages")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "messages" in body
        # Should have messages 0-2 (fork_message_index=2 inclusive)
        assert body["total"] == 3

    def test_get_branch_messages_not_found(self, client):
        """GET messages for non-existent branch returns 404."""
        resp = client.get("/admin/branches/branch-nonexistent/messages")
        assert resp.status_code == 404

    def test_add_branch_message(self, client):
        """POST /admin/branches/<branch_id>/messages adds a message."""
        conv_id = self._create_conversation_with_messages(client)
        create_resp = client.post(
            f"/admin/conversations/{conv_id}/branches",
            json={"fork_message_index": 1, "name": "msg-test"},
        )
        branch = create_resp.get_json()
        branch_id = branch.get("id") or branch.get("branch_id")

        resp = client.post(
            f"/admin/branches/{branch_id}/messages",
            json={"role": "user", "content": "New branched question"},
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body.get("role") == "user" or "id" in body

    def test_add_branch_message_missing_fields(self, client):
        """POST message without role/content returns 400."""
        conv_id = self._create_conversation_with_messages(client)
        create_resp = client.post(
            f"/admin/conversations/{conv_id}/branches",
            json={"fork_message_index": 0, "name": "test"},
        )
        branch = create_resp.get_json()
        branch_id = branch.get("id") or branch.get("branch_id")

        resp = client.post(
            f"/admin/branches/{branch_id}/messages",
            json={"role": "user"},
        )
        assert resp.status_code == 400

    def test_add_branch_message_not_found(self, client):
        """POST message to non-existent branch returns 404."""
        resp = client.post(
            "/admin/branches/branch-nonexistent/messages",
            json={"role": "user", "content": "Hello"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 8. Super Agent Chat
# ---------------------------------------------------------------------------


class TestSuperAgentChat:
    """Tests for /admin/super-agents/<id>/sessions/<id>/chat endpoints."""

    @pytest.fixture(autouse=True)
    def _clear_session_state(self):
        """Clear in-memory session state between tests to avoid concurrency limit."""
        from app.services.super_agent_session_service import SuperAgentSessionService

        SuperAgentSessionService._active_sessions.clear()
        yield
        SuperAgentSessionService._active_sessions.clear()

    def _create_session(self, client):
        """Create a super agent and session, return (super_agent_id, session_id)."""
        sa_id = _create_super_agent(client)
        resp = client.post(f"/admin/super-agents/{sa_id}/sessions")
        assert resp.status_code == 201
        session_id = resp.get_json()["session_id"]
        return sa_id, session_id

    def test_send_chat_message(self, client):
        """POST /<sa_id>/sessions/<sess_id>/chat sends a message."""
        sa_id, session_id = self._create_session(client)
        resp = client.post(
            f"/admin/super-agents/{sa_id}/sessions/{session_id}/chat",
            json={"content": "Hello agent"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert "message_id" in body

    def test_send_chat_message_missing_content(self, client):
        """POST chat message without content returns 400."""
        sa_id, session_id = self._create_session(client)
        resp = client.post(
            f"/admin/super-agents/{sa_id}/sessions/{session_id}/chat",
            json={"content": ""},
        )
        assert resp.status_code == 400

    def test_send_chat_message_no_body(self, client):
        """POST chat message without JSON body returns 400."""
        sa_id, session_id = self._create_session(client)
        resp = client.post(
            f"/admin/super-agents/{sa_id}/sessions/{session_id}/chat",
            content_type="application/json",
            data="",
        )
        assert resp.status_code == 400

    def test_send_chat_message_session_not_found(self, client):
        """POST chat to non-existent session returns 404."""
        sa_id = _create_super_agent(client)
        resp = client.post(
            f"/admin/super-agents/{sa_id}/sessions/sess-fake/chat",
            json={"content": "Hello"},
        )
        assert resp.status_code == 404

    def test_send_chat_message_session_ended(self, client):
        """POST chat to ended session auto-reactivates and returns 200."""
        sa_id, session_id = self._create_session(client)
        # End the session
        client.post(f"/admin/super-agents/{sa_id}/sessions/{session_id}/end")
        resp = client.post(
            f"/admin/super-agents/{sa_id}/sessions/{session_id}/chat",
            json={"content": "Hello"},
        )
        # Ended sessions are auto-reactivated (resume_session is called)
        assert resp.status_code == 200

    def test_stream_chat_sse(self, client):
        """GET /<sa_id>/sessions/<sess_id>/chat/stream returns SSE stream."""
        sa_id, session_id = self._create_session(client)
        resp = client.get(f"/admin/super-agents/{sa_id}/sessions/{session_id}/chat/stream")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/event-stream")


# ---------------------------------------------------------------------------
# 9. Super Agent Messages
# ---------------------------------------------------------------------------


class TestSuperAgentMessages:
    """Tests for /admin/super-agents/<id>/messages/* endpoints."""

    def test_send_agent_message(self, client):
        """POST /<sa_id>/messages sends an inter-agent message."""
        sa_id_from = _create_super_agent(client, name="Sender SA")
        sa_id_to = _create_super_agent(client, name="Receiver SA")
        resp = client.post(
            f"/admin/super-agents/{sa_id_from}/messages",
            json={
                "content": "Hello receiver",
                "to_agent_id": sa_id_to,
                "message_type": "message",
                "priority": "normal",
                "subject": "Test message",
            },
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert "message_id" in body

    def test_send_message_missing_content(self, client):
        """POST message without content returns 400."""
        sa_id = _create_super_agent(client)
        resp = client.post(
            f"/admin/super-agents/{sa_id}/messages",
            json={"to_agent_id": "sa-other", "content": ""},
        )
        assert resp.status_code == 400

    def test_send_message_no_body(self, client):
        """POST message without JSON body returns 400."""
        sa_id = _create_super_agent(client)
        resp = client.post(
            f"/admin/super-agents/{sa_id}/messages",
            content_type="application/json",
            data="",
        )
        assert resp.status_code == 400

    def test_get_inbox_empty(self, client):
        """GET /<sa_id>/messages/inbox returns empty inbox initially."""
        sa_id = _create_super_agent(client)
        resp = client.get(f"/admin/super-agents/{sa_id}/messages/inbox")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["messages"] == []

    def test_get_inbox_with_messages(self, client):
        """GET inbox shows received messages."""
        sa_from = _create_super_agent(client, name="Sender")
        sa_to = _create_super_agent(client, name="Receiver")
        # Send a message
        client.post(
            f"/admin/super-agents/{sa_from}/messages",
            json={"content": "Inbox test", "to_agent_id": sa_to},
        )
        resp = client.get(f"/admin/super-agents/{sa_to}/messages/inbox")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["messages"]) >= 1

    def test_get_outbox_empty(self, client):
        """GET /<sa_id>/messages/outbox returns empty outbox initially."""
        sa_id = _create_super_agent(client)
        resp = client.get(f"/admin/super-agents/{sa_id}/messages/outbox")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["messages"] == []

    def test_get_outbox_with_messages(self, client):
        """GET outbox shows sent messages."""
        sa_from = _create_super_agent(client, name="Sender2")
        sa_to = _create_super_agent(client, name="Receiver2")
        client.post(
            f"/admin/super-agents/{sa_from}/messages",
            json={"content": "Outbox test", "to_agent_id": sa_to},
        )
        resp = client.get(f"/admin/super-agents/{sa_from}/messages/outbox")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["messages"]) >= 1

    def test_mark_message_read(self, client):
        """POST /<sa_id>/messages/<msg_id>/read marks message as read."""
        sa_from = _create_super_agent(client, name="ReadSender")
        sa_to = _create_super_agent(client, name="ReadReceiver")
        send_resp = client.post(
            f"/admin/super-agents/{sa_from}/messages",
            json={"content": "Read me", "to_agent_id": sa_to},
        )
        msg_id = send_resp.get_json()["message_id"]
        resp = client.post(f"/admin/super-agents/{sa_to}/messages/{msg_id}/read")
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Message marked as read"

    def test_mark_message_read_not_found(self, client):
        """POST mark read for non-existent message returns 404."""
        sa_id = _create_super_agent(client)
        resp = client.post(f"/admin/super-agents/{sa_id}/messages/msg-nonexistent/read")
        assert resp.status_code == 404

    def test_stream_messages(self, client):
        """GET /<sa_id>/messages/stream returns SSE stream."""
        sa_id = _create_super_agent(client)
        resp = client.get(f"/admin/super-agents/{sa_id}/messages/stream")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/event-stream")


# ---------------------------------------------------------------------------
# 10. Super Agent Sessions
# ---------------------------------------------------------------------------


class TestSuperAgentSessions:
    """Tests for /admin/super-agents/<id>/sessions/* endpoints."""

    @pytest.fixture(autouse=True)
    def _clear_session_state(self):
        """Clear in-memory session state between tests to avoid concurrency limit."""
        from app.services.super_agent_session_service import SuperAgentSessionService

        SuperAgentSessionService._active_sessions.clear()
        yield
        SuperAgentSessionService._active_sessions.clear()

    def test_create_session(self, client):
        """POST /<sa_id>/sessions creates a new session."""
        sa_id = _create_super_agent(client)
        resp = client.post(f"/admin/super-agents/{sa_id}/sessions")
        assert resp.status_code == 201
        body = resp.get_json()
        assert "session_id" in body

    def test_create_session_agent_not_found(self, client):
        """POST session for non-existent agent returns 404."""
        resp = client.post("/admin/super-agents/sa-nonexistent/sessions")
        assert resp.status_code == 404

    def test_list_sessions(self, client):
        """GET /<sa_id>/sessions lists all sessions."""
        sa_id = _create_super_agent(client)
        resp = client.get(f"/admin/super-agents/{sa_id}/sessions")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "sessions" in body

    def test_list_sessions_after_create(self, client):
        """GET sessions after creating one returns the session."""
        sa_id = _create_super_agent(client)
        client.post(f"/admin/super-agents/{sa_id}/sessions")
        resp = client.get(f"/admin/super-agents/{sa_id}/sessions")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["sessions"]) >= 1

    def test_get_session(self, client):
        """GET /<sa_id>/sessions/<sess_id> returns session details."""
        sa_id = _create_super_agent(client)
        create_resp = client.post(f"/admin/super-agents/{sa_id}/sessions")
        session_id = create_resp.get_json()["session_id"]
        resp = client.get(f"/admin/super-agents/{sa_id}/sessions/{session_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["id"] == session_id

    def test_get_session_not_found(self, client):
        """GET non-existent session returns 404."""
        sa_id = _create_super_agent(client)
        resp = client.get(f"/admin/super-agents/{sa_id}/sessions/sess-fake")
        assert resp.status_code == 404

    def test_send_session_message(self, client):
        """POST /<sa_id>/sessions/<sess_id>/message sends a message."""
        sa_id = _create_super_agent(client)
        create_resp = client.post(f"/admin/super-agents/{sa_id}/sessions")
        session_id = create_resp.get_json()["session_id"]
        resp = client.post(
            f"/admin/super-agents/{sa_id}/sessions/{session_id}/message",
            json={"message": "Hello session"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Message sent"

    def test_send_session_message_no_body(self, client):
        """POST session message without JSON body returns 400."""
        sa_id = _create_super_agent(client)
        create_resp = client.post(f"/admin/super-agents/{sa_id}/sessions")
        session_id = create_resp.get_json()["session_id"]
        resp = client.post(
            f"/admin/super-agents/{sa_id}/sessions/{session_id}/message",
            content_type="application/json",
            data="",
        )
        assert resp.status_code == 400

    def test_send_session_message_missing_message(self, client):
        """POST session message without message field returns 400."""
        sa_id = _create_super_agent(client)
        create_resp = client.post(f"/admin/super-agents/{sa_id}/sessions")
        session_id = create_resp.get_json()["session_id"]
        resp = client.post(
            f"/admin/super-agents/{sa_id}/sessions/{session_id}/message",
            json={"not_message": "test"},
        )
        assert resp.status_code == 400

    def test_send_session_message_not_found(self, client):
        """POST message to non-existent session returns 404."""
        sa_id = _create_super_agent(client)
        resp = client.post(
            f"/admin/super-agents/{sa_id}/sessions/sess-nonexistent/message",
            json={"message": "Hello"},
        )
        assert resp.status_code == 404

    def test_end_session(self, client):
        """POST /<sa_id>/sessions/<sess_id>/end ends the session."""
        sa_id = _create_super_agent(client)
        create_resp = client.post(f"/admin/super-agents/{sa_id}/sessions")
        session_id = create_resp.get_json()["session_id"]
        resp = client.post(f"/admin/super-agents/{sa_id}/sessions/{session_id}/end")
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Session ended"

    def test_end_session_not_found(self, client):
        """POST end for non-existent session returns 404."""
        sa_id = _create_super_agent(client)
        resp = client.post(f"/admin/super-agents/{sa_id}/sessions/sess-fake/end")
        assert resp.status_code == 404

    def test_stream_session(self, client):
        """GET /<sa_id>/sessions/<sess_id>/stream returns SSE stream."""
        sa_id = _create_super_agent(client)
        create_resp = client.post(f"/admin/super-agents/{sa_id}/sessions")
        session_id = create_resp.get_json()["session_id"]
        resp = client.get(f"/admin/super-agents/{sa_id}/sessions/{session_id}/stream")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/event-stream")

    def test_session_workflow_create_message_end(self, client):
        """Full lifecycle: create session, send message, end session."""
        sa_id = _create_super_agent(client)

        # Create session
        create_resp = client.post(f"/admin/super-agents/{sa_id}/sessions")
        assert create_resp.status_code == 201
        session_id = create_resp.get_json()["session_id"]

        # Send message
        msg_resp = client.post(
            f"/admin/super-agents/{sa_id}/sessions/{session_id}/message",
            json={"message": "What is the status?"},
        )
        assert msg_resp.status_code == 200

        # End session
        end_resp = client.post(f"/admin/super-agents/{sa_id}/sessions/{session_id}/end")
        assert end_resp.status_code == 200

        # Sending message to ended session should fail
        fail_resp = client.post(
            f"/admin/super-agents/{sa_id}/sessions/{session_id}/message",
            json={"message": "Should fail"},
        )
        assert fail_resp.status_code == 404
