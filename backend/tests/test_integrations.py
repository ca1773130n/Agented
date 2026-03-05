"""Tests for integration adapters, notification service, and CRUD routes.

All external API calls are mocked -- no real Slack, Teams, JIRA, or Linear
calls are made.
"""

import time
from unittest.mock import MagicMock, patch

from app.db import integrations as db_integrations
from app.services.integrations import ADAPTER_REGISTRY, IntegrationAdapter, get_adapter
from app.services.integrations.jira_adapter import JiraAdapter
from app.services.integrations.linear_adapter import LinearAdapter
from app.services.integrations.slack_adapter import SlackAdapter
from app.services.integrations.teams_adapter import TeamsAdapter
from app.services.notification_service import NotificationService

# =============================================================================
# Adapter registry tests
# =============================================================================


class TestAdapterRegistry:
    def test_all_four_adapters_registered(self):
        """All 4 adapter types are present in the registry."""
        assert "slack" in ADAPTER_REGISTRY
        assert "teams" in ADAPTER_REGISTRY
        assert "jira" in ADAPTER_REGISTRY
        assert "linear" in ADAPTER_REGISTRY

    def test_get_adapter_returns_correct_type(self):
        """get_adapter returns the correct adapter class instance."""
        adapter = get_adapter("slack", token="test-token")
        assert isinstance(adapter, SlackAdapter)

        adapter = get_adapter("teams", webhook_url="https://example.com/hook")
        assert isinstance(adapter, TeamsAdapter)

    def test_get_adapter_unknown_returns_none(self):
        """get_adapter returns None for unknown types."""
        assert get_adapter("unknown") is None

    def test_all_adapters_are_integration_adapters(self):
        """All registered adapters are subclasses of IntegrationAdapter."""
        for adapter_type, cls in ADAPTER_REGISTRY.items():
            assert issubclass(cls, IntegrationAdapter), (
                f"{adapter_type} is not an IntegrationAdapter"
            )


# =============================================================================
# Slack adapter tests
# =============================================================================


class TestSlackAdapter:
    def test_send_notification_with_block_kit(self):
        """Slack adapter sends Block Kit formatted message."""
        adapter = SlackAdapter(token="xoxb-test-token")
        mock_client = MagicMock()
        adapter._client = mock_client
        mock_client.chat_postMessage.return_value = {"ok": True}

        result = adapter.send_notification(
            channel="#general",
            message="Test notification",
            metadata={"status": "success", "bot_name": "TestBot", "duration": "5s"},
        )

        assert result is True
        mock_client.chat_postMessage.assert_called_once()
        call_kwargs = mock_client.chat_postMessage.call_args
        assert call_kwargs.kwargs["channel"] == "#general"
        # Verify Block Kit blocks are present
        blocks = call_kwargs.kwargs["blocks"]
        assert len(blocks) >= 2
        assert blocks[0]["type"] == "header"

    def test_send_notification_no_token(self):
        """Slack adapter returns False when no token configured."""
        adapter = SlackAdapter(token="")
        assert adapter.send_notification("#general", "test") is False

    def test_validate_config_valid(self):
        """Slack validate_config accepts non-empty token."""
        adapter = SlackAdapter()
        valid, error = adapter.validate_config({"token": "xoxb-test"})
        assert valid is True
        assert error is None

    def test_validate_config_missing_token(self):
        """Slack validate_config rejects empty token."""
        adapter = SlackAdapter()
        valid, error = adapter.validate_config({})
        assert valid is False
        assert "token" in error.lower()

    def test_create_ticket_returns_none(self):
        """Slack adapter does not create tickets."""
        adapter = SlackAdapter(token="test")
        assert adapter.create_ticket("PROJECT", {"title": "test"}) is None


# =============================================================================
# Teams adapter tests
# =============================================================================


class TestTeamsAdapter:
    @patch("app.services.integrations.teams_adapter.httpx.post")
    def test_send_notification_posts_card(self, mock_post):
        """Teams adapter POSTs MessageCard to webhook URL."""
        mock_post.return_value = MagicMock(status_code=200)
        adapter = TeamsAdapter(webhook_url="https://outlook.office.com/webhook/test")

        result = adapter.send_notification(
            channel="ignored",
            message="Test",
            metadata={"status": "success", "bot_name": "Bot", "duration": "3s"},
        )

        assert result is True
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs["json"]
        assert payload["@type"] == "MessageCard"
        assert payload["themeColor"] == "00FF00"

    def test_validate_config_valid(self):
        """Teams validate_config accepts HTTPS webhook URL."""
        adapter = TeamsAdapter()
        valid, error = adapter.validate_config(
            {"webhook_url": "https://outlook.office.com/webhook/test"}
        )
        assert valid is True

    def test_validate_config_missing_url(self):
        """Teams validate_config rejects empty URL."""
        adapter = TeamsAdapter()
        valid, error = adapter.validate_config({})
        assert valid is False

    def test_validate_config_http_url(self):
        """Teams validate_config rejects non-HTTPS URL."""
        adapter = TeamsAdapter()
        valid, error = adapter.validate_config({"webhook_url": "http://example.com"})
        assert valid is False
        assert "HTTPS" in error


# =============================================================================
# JIRA adapter tests
# =============================================================================


class TestJiraAdapter:
    @patch("app.services.integrations.jira_adapter.JiraAdapter._get_client")
    def test_create_ticket_with_severity_mapping(self, mock_get_client):
        """JIRA adapter maps severity to priority correctly."""
        mock_client = MagicMock()
        mock_issue = MagicMock()
        mock_issue.key = "SEC-42"
        mock_client.create_issue.return_value = mock_issue
        mock_get_client.return_value = mock_client

        adapter = JiraAdapter(
            server="https://jira.example.com", email="test@test.com", api_token="token"
        )

        result = adapter.create_ticket(
            "SEC",
            {
                "title": "Critical SQL Injection",
                "description": "Found SQL injection in login endpoint",
                "severity": "critical",
            },
        )

        assert result == "SEC-42"
        call_args = mock_client.create_issue.call_args
        fields = call_args.kwargs["fields"]
        assert fields["priority"]["name"] == "Highest"
        assert fields["project"]["key"] == "SEC"
        assert "agented" in fields["labels"]
        assert "automated" in fields["labels"]

    def test_send_notification_returns_false(self):
        """JIRA adapter does not send notifications."""
        adapter = JiraAdapter()
        assert adapter.send_notification("#channel", "test") is False

    def test_validate_config_requires_all_fields(self):
        """JIRA validate_config requires server, email, and api_token."""
        adapter = JiraAdapter()
        valid, _ = adapter.validate_config({"server": "https://jira.example.com"})
        assert valid is False

        valid, _ = adapter.validate_config(
            {
                "server": "https://jira.example.com",
                "email": "test@test.com",
                "api_token": "token",
            }
        )
        assert valid is True


# =============================================================================
# Linear adapter tests
# =============================================================================


class TestLinearAdapter:
    @patch("app.services.integrations.linear_adapter.httpx.post")
    def test_create_ticket_graphql(self, mock_post):
        """Linear adapter sends GraphQL mutation for issue creation."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "issueCreate": {
                    "success": True,
                    "issue": {
                        "id": "abc",
                        "identifier": "ENG-42",
                        "url": "https://linear.app/ENG-42",
                    },
                }
            }
        }
        mock_post.return_value = mock_response

        adapter = LinearAdapter(api_key="lin_test_key")
        result = adapter.create_ticket(
            "team-id",
            {
                "title": "Fix vulnerability",
                "description": "XSS found",
                "severity": "high",
            },
        )

        assert result == "ENG-42"
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs.kwargs["headers"]["Authorization"] == "lin_test_key"

    def test_validate_config_requires_key(self):
        """Linear validate_config requires api_key."""
        adapter = LinearAdapter()
        valid, _ = adapter.validate_config({})
        assert valid is False

        valid, _ = adapter.validate_config({"api_key": "lin_test"})
        assert valid is True


# =============================================================================
# Integration DB CRUD tests
# =============================================================================


class TestIntegrationDB:
    def test_create_and_get(self):
        """Create an integration and retrieve it."""
        intg_id = db_integrations.create_integration(
            name="Test Slack",
            integration_type="slack",
            config={"channel": "#alerts"},
        )
        assert intg_id.startswith("intg-")

        intg = db_integrations.get_integration(intg_id)
        assert intg is not None
        assert intg["name"] == "Test Slack"
        assert intg["type"] == "slack"
        assert intg["config"]["channel"] == "#alerts"
        assert intg["enabled"] == 1

    def test_list_integrations(self):
        """List integrations with type filter."""
        db_integrations.create_integration("Slack 1", "slack")
        db_integrations.create_integration("Teams 1", "teams")

        all_intgs = db_integrations.list_integrations()
        assert len(all_intgs) >= 2

        slack_only = db_integrations.list_integrations(integration_type="slack")
        for i in slack_only:
            assert i["type"] == "slack"

    def test_update_integration(self):
        """Update integration fields."""
        intg_id = db_integrations.create_integration("Old Name", "teams")
        updated = db_integrations.update_integration(intg_id, name="New Name", enabled=False)
        assert updated is True

        intg = db_integrations.get_integration(intg_id)
        assert intg["name"] == "New Name"
        assert intg["enabled"] == 0

    def test_delete_integration(self):
        """Delete an integration."""
        intg_id = db_integrations.create_integration("Delete Me", "linear")
        assert db_integrations.delete_integration(intg_id) is True
        assert db_integrations.get_integration(intg_id) is None

    def test_list_for_trigger(self):
        """list_integrations_for_trigger returns trigger-specific and global integrations."""
        # Use predefined trigger IDs that exist in the DB
        global_id = db_integrations.create_integration("Global", "slack")
        trigger_id = db_integrations.create_integration(
            "Trigger Specific", "teams", trigger_id="bot-security"
        )
        other_trigger = db_integrations.create_integration(
            "Other Trigger", "jira", trigger_id="bot-pr-review"
        )

        results = db_integrations.list_integrations_for_trigger("bot-security")
        result_ids = [r["id"] for r in results]
        assert global_id in result_ids
        assert trigger_id in result_ids
        assert other_trigger not in result_ids


# =============================================================================
# Notification service tests
# =============================================================================


class TestNotificationService:
    @patch("app.services.notification_service.IntegrationConfigService")
    def test_dispatch_to_all_integrations(self, mock_config_service):
        """NotificationService dispatches to all integrations for a trigger."""
        # Create test integrations using predefined trigger ID
        db_integrations.create_integration(
            "Slack", "slack", config={"channel": "#alerts"}, trigger_id="bot-security"
        )
        db_integrations.create_integration(
            "Teams", "teams", config={"webhook_url": "https://test.com"}, trigger_id="bot-security"
        )

        mock_adapter = MagicMock()
        mock_adapter.send_notification.return_value = True
        mock_config_service.get_adapter_for_integration.return_value = mock_adapter

        NotificationService.on_execution_complete(
            execution_id="exec-test-123",
            trigger_id="bot-security",
            status="success",
            duration_ms=5000,
            summary="All checks passed",
        )

        # Wait for background threads
        time.sleep(0.5)

        # At least 2 calls (one per integration)
        assert mock_config_service.get_adapter_for_integration.call_count >= 2

    def test_notification_timing_under_30s(self):
        """Notification dispatch completes within 30 seconds (proxy timing)."""
        # Create 5 integrations
        for i in range(5):
            db_integrations.create_integration(
                f"Test {i}",
                "slack",
                config={"channel": f"#ch{i}"},
                trigger_id="bot-security",
            )

        with patch("app.services.notification_service.IntegrationConfigService") as mock_cs:
            mock_adapter = MagicMock()
            mock_adapter.send_notification.return_value = True
            mock_cs.get_adapter_for_integration.return_value = mock_adapter

            start = time.perf_counter()
            NotificationService.on_execution_complete(
                execution_id="exec-timing",
                trigger_id="bot-security",
                status="success",
                duration_ms=1000,
            )
            # Wait for all background threads
            time.sleep(1.0)
            elapsed = time.perf_counter() - start

            assert elapsed < 30, f"Notification dispatch took {elapsed:.1f}s (>30s limit)"


# =============================================================================
# Integration CRUD route tests
# =============================================================================


class TestIntegrationRoutes:
    def test_create_integration_route(self, client):
        """POST /admin/integrations creates an integration."""
        resp = client.post(
            "/admin/integrations",
            json={
                "name": "Route Test",
                "type": "slack",
                "config": {"channel": "#test"},
            },
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["name"] == "Route Test"
        assert data["type"] == "slack"

    def test_list_integrations_route(self, client):
        """GET /admin/integrations lists integrations."""
        client.post("/admin/integrations", json={"name": "A", "type": "slack", "config": {}})
        resp = client.get("/admin/integrations")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) >= 1

    def test_get_integration_route(self, client):
        """GET /admin/integrations/<id> returns single integration."""
        create_resp = client.post(
            "/admin/integrations", json={"name": "Get Test", "type": "teams", "config": {}}
        )
        intg_id = create_resp.get_json()["id"]

        resp = client.get(f"/admin/integrations/{intg_id}")
        assert resp.status_code == 200
        assert resp.get_json()["name"] == "Get Test"

    def test_update_integration_route(self, client):
        """PUT /admin/integrations/<id> updates an integration."""
        create_resp = client.post(
            "/admin/integrations", json={"name": "Old", "type": "linear", "config": {}}
        )
        intg_id = create_resp.get_json()["id"]

        resp = client.put(f"/admin/integrations/{intg_id}", json={"name": "New", "enabled": False})
        assert resp.status_code == 200
        assert resp.get_json()["name"] == "New"

    def test_delete_integration_route(self, client):
        """DELETE /admin/integrations/<id> deletes an integration."""
        create_resp = client.post(
            "/admin/integrations", json={"name": "Delete Me", "type": "jira", "config": {}}
        )
        intg_id = create_resp.get_json()["id"]

        resp = client.delete(f"/admin/integrations/{intg_id}")
        assert resp.status_code == 200

        resp = client.get(f"/admin/integrations/{intg_id}")
        assert resp.status_code == 404

    def test_not_found(self, client):
        """GET /admin/integrations/nonexistent returns 404."""
        resp = client.get("/admin/integrations/intg-nonexistent")
        assert resp.status_code == 404
