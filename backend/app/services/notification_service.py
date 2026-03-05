"""Unified notification dispatch service.

Dispatches notifications to all configured integrations for a given trigger.
Uses background threads to avoid blocking webhook responses.
"""

import logging
import threading
from typing import Optional

from app.db import integrations as db_integrations
from app.services.audit_log_service import AuditLogService
from app.services.integration_config_service import IntegrationConfigService

logger = logging.getLogger(__name__)


class NotificationService:
    """Dispatch notifications and create tickets across configured integrations."""

    @staticmethod
    def on_execution_complete(
        execution_id: str,
        trigger_id: str,
        status: str,
        duration_ms: int,
        summary: str = "",
    ):
        """Notify all configured integrations when an execution completes.

        Spawns a background thread for each integration to avoid blocking.

        Args:
            execution_id: The execution that completed.
            trigger_id: The trigger that was executed.
            status: Execution status (success, failed, etc.).
            duration_ms: Duration in milliseconds.
            summary: Summary text to include in notification.
        """
        integrations = db_integrations.list_integrations_for_trigger(trigger_id)
        if not integrations:
            return

        duration_str = f"{duration_ms / 1000:.1f}s"
        message = summary or f"Execution {execution_id} completed with status: {status}"
        metadata = {
            "status": status,
            "bot_name": "Agented",
            "duration": duration_str,
            "execution_id": execution_id,
        }

        for integration in integrations:
            thread = threading.Thread(
                target=NotificationService._send_to_integration,
                args=(integration, message, metadata),
                daemon=True,
            )
            thread.start()

    @staticmethod
    def _send_to_integration(integration: dict, message: str, metadata: dict):
        """Send notification to a single integration (runs in background thread)."""
        integration_id = integration["id"]
        try:
            adapter = IntegrationConfigService.get_adapter_for_integration(integration_id)
            if not adapter:
                logger.warning("No adapter for integration %s", integration_id)
                return

            config = integration.get("config", {})
            channel = config.get("channel", config.get("webhook_url", ""))

            success = adapter.send_notification(
                channel=channel,
                message=message,
                metadata=metadata,
            )

            AuditLogService.log(
                action="notification.send",
                entity_type="integration",
                entity_id=integration_id,
                outcome="success" if success else "failed",
                details={
                    "execution_id": metadata.get("execution_id"),
                    "status": metadata.get("status"),
                },
            )
        except Exception as e:
            logger.error("Notification to %s failed: %s", integration_id, e)
            AuditLogService.log(
                action="notification.send",
                entity_type="integration",
                entity_id=integration_id,
                outcome="error",
                details={"error": str(e)},
            )

    @staticmethod
    def create_tickets_from_findings(trigger_id: str, findings: list) -> list:
        """Create tickets from findings using ticket-capable integrations (JIRA, Linear).

        Args:
            trigger_id: Trigger that generated findings.
            findings: List of dicts with title, description, severity, source.

        Returns:
            List of created ticket IDs/URLs.
        """
        integrations = db_integrations.list_integrations_for_trigger(trigger_id)
        ticket_integrations = [i for i in integrations if i["type"] in ("jira", "linear")]

        if not ticket_integrations:
            return []

        created_tickets = []
        for integration in ticket_integrations:
            adapter = IntegrationConfigService.get_adapter_for_integration(integration["id"])
            if not adapter:
                continue

            config = integration.get("config", {})
            project_key = config.get("project_key", config.get("team_id", ""))

            for finding in findings:
                ticket_id = adapter.create_ticket(project_key, finding)
                if ticket_id:
                    created_tickets.append(ticket_id)
                    AuditLogService.log(
                        action="ticket.create",
                        entity_type="integration",
                        entity_id=integration["id"],
                        outcome="success",
                        details={
                            "ticket_id": ticket_id,
                            "finding_title": finding.get("title"),
                        },
                    )

        return created_tickets

    @staticmethod
    def dispatch_notification(
        integration_id: str,
        message: str,
        metadata: Optional[dict] = None,
    ) -> bool:
        """Send a notification to a single integration (synchronous).

        Used for manual sends and testing.
        """
        adapter = IntegrationConfigService.get_adapter_for_integration(integration_id)
        if not adapter:
            return False

        integration = db_integrations.get_integration(integration_id)
        if not integration:
            return False

        config = integration.get("config", {})
        channel = config.get("channel", config.get("webhook_url", ""))

        return adapter.send_notification(
            channel=channel,
            message=message,
            metadata=metadata,
        )
