"""Tests for ALL conversation route → service send_message signature compatibility.

These tests verify that:
1. Every conversation service's send_message() accepts backend/account_id/model kwargs
2. Every conversation route's POST /<conv_id>/message doesn't crash with those kwargs
3. Start → send_message round-trip works for each conversation type
4. Missing message body returns 400

This test file exists because routes pass backend=, account_id=, model= kwargs
to service send_message() and a signature mismatch causes a runtime TypeError
that is invisible at import time and only caught when a user actually sends a message.
"""

import inspect

import pytest

from app.services.agent_conversation_service import AgentConversationService
from app.services.command_conversation_service import CommandConversationService
from app.services.hook_conversation_service import HookConversationService
from app.services.plugin_conversation_service import PluginConversationService
from app.services.rule_conversation_service import RuleConversationService
from app.services.skill_conversation_service import SkillConversationService

# ===========================================================================
# Signature compatibility tests (catch TypeError before it reaches production)
# ===========================================================================


class TestSendMessageSignatures:
    """Verify every service's send_message accepts the kwargs routes pass."""

    SERVICES = [
        ("AgentConversationService", AgentConversationService),
        ("SkillConversationService", SkillConversationService),
        ("PluginConversationService", PluginConversationService),
        ("HookConversationService", HookConversationService),
        ("CommandConversationService", CommandConversationService),
        ("RuleConversationService", RuleConversationService),
    ]

    @pytest.mark.parametrize("name,svc", SERVICES, ids=[s[0] for s in SERVICES])
    def test_send_message_accepts_backend_kwarg(self, name, svc):
        """send_message must accept 'backend' keyword argument."""
        sig = inspect.signature(svc.send_message)
        params = list(sig.parameters.keys())
        assert "backend" in params, (
            f"{name}.send_message() missing 'backend' parameter. "
            f"Route passes backend=data.get('backend') but service won't accept it."
        )

    @pytest.mark.parametrize("name,svc", SERVICES, ids=[s[0] for s in SERVICES])
    def test_send_message_accepts_account_id_kwarg(self, name, svc):
        """send_message must accept 'account_id' keyword argument."""
        sig = inspect.signature(svc.send_message)
        params = list(sig.parameters.keys())
        assert "account_id" in params, (
            f"{name}.send_message() missing 'account_id' parameter. "
            f"Route passes account_id=data.get('account_id') but service won't accept it."
        )

    @pytest.mark.parametrize("name,svc", SERVICES, ids=[s[0] for s in SERVICES])
    def test_send_message_accepts_model_kwarg(self, name, svc):
        """send_message must accept 'model' keyword argument."""
        sig = inspect.signature(svc.send_message)
        params = list(sig.parameters.keys())
        assert "model" in params, (
            f"{name}.send_message() missing 'model' parameter. "
            f"Route passes model=data.get('model') but service won't accept it."
        )

    @pytest.mark.parametrize("name,svc", SERVICES, ids=[s[0] for s in SERVICES])
    def test_send_message_has_conv_id_and_message(self, name, svc):
        """send_message must accept positional conv_id and message."""
        sig = inspect.signature(svc.send_message)
        params = list(sig.parameters.keys())
        # First param is 'cls' for classmethod, then conv_id, message
        assert "conv_id" in params, f"{name}.send_message() missing 'conv_id'"
        assert "message" in params, f"{name}.send_message() missing 'message'"


# ===========================================================================
# Route-level HTTP tests (agent conversations)
# ===========================================================================


class TestAgentConversationRoutes:
    """Route-level tests for /api/agents/conversations."""

    def test_send_message_missing_body_returns_400(self, client, isolated_db):
        """POST without message body should return 400."""
        resp = client.post(
            "/api/agents/conversations/fake-conv/message",
            json={},
        )
        assert resp.status_code == 400

    def test_send_message_missing_message_field_returns_400(self, client, isolated_db):
        """POST with body but no 'message' field should return 400."""
        resp = client.post(
            "/api/agents/conversations/fake-conv/message",
            json={"backend": "claude"},
        )
        assert resp.status_code == 400

    def test_send_message_with_backend_kwargs_no_crash(self, client, isolated_db):
        """POST with backend/account_id/model kwargs must not crash with TypeError."""
        # Start a conversation first
        resp = client.post("/api/agents/conversations/start")
        assert resp.status_code == 201
        conv_id = resp.get_json()["conversation_id"]

        # Send message with all kwargs — this is the exact call that was crashing
        resp = client.post(
            f"/api/agents/conversations/{conv_id}/message",
            json={
                "message": "Create an agent called TestBot",
                "backend": "claude",
                "account_id": "123",
                "model": "claude-sonnet-4-20250514",
            },
        )
        # Should be 202 (accepted) or similar, NOT 500/TypeError
        assert resp.status_code != 500, (
            f"send_message crashed with kwargs. Response: {resp.get_json()}"
        )

    def test_send_message_without_kwargs_works(self, client, isolated_db):
        """POST with just message (no backend kwargs) should work."""
        resp = client.post("/api/agents/conversations/start")
        conv_id = resp.get_json()["conversation_id"]

        resp = client.post(
            f"/api/agents/conversations/{conv_id}/message",
            json={"message": "Hello"},
        )
        assert resp.status_code != 500

    def test_send_message_nonexistent_conv_returns_404(self, client, isolated_db):
        """POST to nonexistent conversation should return 404."""
        resp = client.post(
            "/api/agents/conversations/nonexistent/message",
            json={"message": "hello"},
        )
        assert resp.status_code == 404


# ===========================================================================
# Route-level HTTP tests (skill conversations)
# ===========================================================================


class TestSkillConversationRoutes:
    """Route-level tests for /api/skills/conversations."""

    def test_send_message_missing_body_returns_400(self, client, isolated_db):
        resp = client.post(
            "/api/skills/conversations/fake-conv/message",
            json={},
        )
        assert resp.status_code == 400

    def test_send_message_with_backend_kwargs_no_crash(self, client, isolated_db):
        """POST with backend kwargs must not TypeError."""
        resp = client.post("/api/skills/conversations/start")
        assert resp.status_code == 201
        conv_id = resp.get_json()["conversation_id"]

        resp = client.post(
            f"/api/skills/conversations/{conv_id}/message",
            json={
                "message": "Create a skill for formatting code",
                "backend": "claude",
                "account_id": "456",
                "model": "claude-sonnet-4-20250514",
            },
        )
        assert resp.status_code != 500, (
            f"SkillConversation send_message crashed. Response: {resp.get_json()}"
        )


# ===========================================================================
# Route-level HTTP tests (plugin conversations)
# ===========================================================================


class TestPluginConversationRoutes:
    """Route-level tests for /api/plugins/conversations."""

    def test_send_message_missing_body_returns_400(self, client, isolated_db):
        resp = client.post(
            "/api/plugins/conversations/fake-conv/message",
            json={},
        )
        assert resp.status_code == 400

    def test_send_message_with_backend_kwargs_no_crash(self, client, isolated_db):
        """POST with backend kwargs must not TypeError."""
        resp = client.post("/api/plugins/conversations/start")
        assert resp.status_code == 201
        conv_id = resp.get_json()["conversation_id"]

        resp = client.post(
            f"/api/plugins/conversations/{conv_id}/message",
            json={
                "message": "Create a plugin for linting",
                "backend": "claude",
                "account_id": "789",
                "model": "claude-sonnet-4-20250514",
            },
        )
        assert resp.status_code != 500, (
            f"PluginConversation send_message crashed. Response: {resp.get_json()}"
        )


# ===========================================================================
# Route-level HTTP tests (hook conversations — BaseConversationService)
# ===========================================================================


class TestHookConversationRoutes:
    """Route-level tests for /api/hooks/conversations."""

    def test_send_message_missing_body_returns_400(self, client, isolated_db):
        resp = client.post(
            "/api/hooks/conversations/fake-conv/message",
            json={},
        )
        assert resp.status_code == 400

    def test_send_message_with_backend_kwargs_no_crash(self, client, isolated_db):
        """POST with backend kwargs must not TypeError."""
        resp = client.post("/api/hooks/conversations/start")
        assert resp.status_code == 201
        conv_id = resp.get_json()["conversation_id"]

        resp = client.post(
            f"/api/hooks/conversations/{conv_id}/message",
            json={
                "message": "Create a pre-commit hook",
                "backend": "claude",
                "account_id": "101",
                "model": "claude-sonnet-4-20250514",
            },
        )
        assert resp.status_code != 500, (
            f"HookConversation send_message crashed. Response: {resp.get_json()}"
        )


# ===========================================================================
# Route-level HTTP tests (command conversations — BaseConversationService)
# ===========================================================================


class TestCommandConversationRoutes:
    """Route-level tests for /api/commands/conversations."""

    def test_send_message_missing_body_returns_400(self, client, isolated_db):
        resp = client.post(
            "/api/commands/conversations/fake-conv/message",
            json={},
        )
        assert resp.status_code == 400

    def test_send_message_with_backend_kwargs_no_crash(self, client, isolated_db):
        """POST with backend kwargs must not TypeError."""
        resp = client.post("/api/commands/conversations/start")
        assert resp.status_code == 201
        conv_id = resp.get_json()["conversation_id"]

        resp = client.post(
            f"/api/commands/conversations/{conv_id}/message",
            json={
                "message": "Create a deploy command",
                "backend": "claude",
                "account_id": "202",
                "model": "claude-sonnet-4-20250514",
            },
        )
        assert resp.status_code != 500, (
            f"CommandConversation send_message crashed. Response: {resp.get_json()}"
        )


# ===========================================================================
# Route-level HTTP tests (rule conversations — BaseConversationService)
# ===========================================================================


class TestRuleConversationRoutes:
    """Route-level tests for /api/rules/conversations."""

    def test_send_message_missing_body_returns_400(self, client, isolated_db):
        resp = client.post(
            "/api/rules/conversations/fake-conv/message",
            json={},
        )
        assert resp.status_code == 400

    def test_send_message_with_backend_kwargs_no_crash(self, client, isolated_db):
        """POST with backend kwargs must not TypeError."""
        resp = client.post("/api/rules/conversations/start")
        assert resp.status_code == 201
        conv_id = resp.get_json()["conversation_id"]

        resp = client.post(
            f"/api/rules/conversations/{conv_id}/message",
            json={
                "message": "Create a rule for code review",
                "backend": "claude",
                "account_id": "303",
                "model": "claude-sonnet-4-20250514",
            },
        )
        assert resp.status_code != 500, (
            f"RuleConversation send_message crashed. Response: {resp.get_json()}"
        )
