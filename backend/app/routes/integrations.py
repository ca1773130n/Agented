"""Integration management and Slack slash command API endpoints."""

import logging
import threading
from http import HTTPStatus
from urllib.parse import parse_qs

from flask import jsonify, request
from flask_openapi3 import APIBlueprint, Tag

from ..db import integrations as db_integrations
from ..models.integration import (
    IntegrationCreate,
    IntegrationPath,
    IntegrationQuery,
    IntegrationUpdate,
    TriggerIntegrationPath,
)
from ..services.audit_log_service import AuditLogService
from ..services.integration_config_service import IntegrationConfigService

logger = logging.getLogger(__name__)

tag = Tag(name="integrations", description="Integration management and notifications")

# Admin blueprint for CRUD operations
integrations_bp = APIBlueprint("integrations", __name__, url_prefix="/admin", abp_tags=[tag])

# API blueprint for public webhook endpoints (Slack slash commands)
slack_command_tag = Tag(name="slack-commands", description="Slack slash command webhook")
slack_command_bp = APIBlueprint(
    "slack_commands", __name__, url_prefix="/api/integrations", abp_tags=[slack_command_tag]
)


# =============================================================================
# Integration CRUD (admin routes)
# =============================================================================


@integrations_bp.post("/integrations")
def create_integration(body: IntegrationCreate):
    """Create a new integration configuration."""
    try:
        integration_id = IntegrationConfigService.create_integration(body)
        integration = db_integrations.get_integration(integration_id)
        return jsonify(integration), HTTPStatus.CREATED
    except ValueError as e:
        return jsonify({"error": str(e)}), HTTPStatus.BAD_REQUEST


@integrations_bp.get("/integrations")
def list_integrations(query: IntegrationQuery):
    """List all integrations with optional type/trigger filters."""
    results = db_integrations.list_integrations(
        integration_type=query.type,
        trigger_id=query.trigger_id,
    )
    return jsonify(results)


@integrations_bp.get("/integrations/<integration_id>")
def get_integration(path: IntegrationPath):
    """Get a single integration by ID."""
    integration = db_integrations.get_integration(path.integration_id)
    if not integration:
        return jsonify({"error": "Integration not found"}), HTTPStatus.NOT_FOUND
    return jsonify(integration)


@integrations_bp.put("/integrations/<integration_id>")
def update_integration(path: IntegrationPath, body: IntegrationUpdate):
    """Update an integration configuration."""
    updated = db_integrations.update_integration(
        path.integration_id,
        name=body.name,
        config=body.config,
        trigger_id=body.trigger_id,
        enabled=body.enabled,
    )
    if not updated:
        return jsonify({"error": "Integration not found"}), HTTPStatus.NOT_FOUND

    AuditLogService.log(
        action="integration.update",
        entity_type="integration",
        entity_id=path.integration_id,
        outcome="updated",
    )

    integration = db_integrations.get_integration(path.integration_id)
    return jsonify(integration)


@integrations_bp.delete("/integrations/<integration_id>")
def delete_integration(path: IntegrationPath):
    """Delete an integration."""
    deleted = db_integrations.delete_integration(path.integration_id)
    if not deleted:
        return jsonify({"error": "Integration not found"}), HTTPStatus.NOT_FOUND

    AuditLogService.log(
        action="integration.delete",
        entity_type="integration",
        entity_id=path.integration_id,
        outcome="deleted",
    )
    return jsonify({"status": "deleted"}), HTTPStatus.OK


@integrations_bp.post("/integrations/<integration_id>/test")
def test_integration(path: IntegrationPath):
    """Send a test notification via the integration."""
    success, message = IntegrationConfigService.test_integration(path.integration_id)
    status_code = HTTPStatus.OK if success else HTTPStatus.BAD_REQUEST
    return jsonify({"success": success, "message": message}), status_code


@integrations_bp.get("/triggers/<trigger_id>/integrations")
def list_trigger_integrations(path: TriggerIntegrationPath):
    """List integrations linked to a specific trigger."""
    results = db_integrations.list_integrations_for_trigger(path.trigger_id)
    return jsonify(results)


# =============================================================================
# Slack slash command webhook (public API route)
# =============================================================================


@slack_command_bp.post("/slack/command")
def slack_slash_command():
    """Handle inbound Slack slash command (/agented).

    Verifies HMAC-SHA256 signature, parses the command, and dispatches
    execution in a background thread. Responds within 3 seconds per
    Slack requirements.
    """
    from ..services.integrations.slack_adapter import SlackAdapter

    # --- Signature verification ---
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")
    raw_body = request.get_data(as_text=True)

    # Retrieve signing secret from vault
    signing_secret = _get_slack_signing_secret()
    if not signing_secret:
        logger.error("Slack signing secret not configured")
        return jsonify({"response_type": "ephemeral", "text": "Server configuration error"}), 200

    if not SlackAdapter.verify_slack_signature(signing_secret, timestamp, raw_body, signature):
        return jsonify({"error": "Invalid signature"}), HTTPStatus.UNAUTHORIZED

    # --- Parse slash command payload ---
    # Slack sends form-encoded data
    form_data = parse_qs(raw_body)
    command = form_data.get("command", [""])[0]
    text = form_data.get("text", [""])[0].strip()
    user_id = form_data.get("user_id", [""])[0]
    channel_id = form_data.get("channel_id", [""])[0]
    response_url = form_data.get("response_url", [""])[0]

    AuditLogService.log(
        action="slash_command.received",
        entity_type="integration",
        entity_id="slack",
        outcome="received",
        details={
            "command": command,
            "text": text,
            "user_id": user_id,
            "channel_id": channel_id,
        },
    )

    # --- Parse command text ---
    # Expected: "run <trigger-name> on <target>"
    trigger_name, target, parse_error = _parse_run_command(text)
    if parse_error:
        return jsonify(
            {
                "response_type": "ephemeral",
                "text": parse_error,
            }
        ), 200

    # --- Look up trigger ---
    from ..db import triggers as db_triggers

    trigger = db_triggers.get_trigger_by_name(trigger_name)
    if not trigger:
        return jsonify(
            {
                "response_type": "ephemeral",
                "text": f"Unknown trigger: '{trigger_name}'. Use `/agented run <trigger-name> on <target>`.",
            }
        ), 200

    # --- Dispatch in background ---
    thread = threading.Thread(
        target=_dispatch_slash_command_execution,
        args=(trigger, target, response_url, user_id),
        daemon=True,
    )
    thread.start()

    # --- Immediate response (within 3 seconds) ---
    return jsonify(
        {
            "response_type": "ephemeral",
            "text": f"Starting {trigger_name} on {target}...",
        }
    ), 200


def _parse_run_command(text: str):
    """Parse 'run <trigger-name> on <target>' from slash command text.

    Returns: (trigger_name, target, error_message)
    """
    if not text:
        return None, None, "Usage: `/agented run <trigger-name> on <target>`"

    parts = text.split()
    if len(parts) < 4 or parts[0].lower() != "run":
        return None, None, "Usage: `/agented run <trigger-name> on <target>`"

    try:
        on_idx = parts.index("on")
    except ValueError:
        return None, None, "Usage: `/agented run <trigger-name> on <target>`"

    trigger_name = " ".join(parts[1:on_idx])
    target = " ".join(parts[on_idx + 1 :])

    if not trigger_name or not target:
        return None, None, "Usage: `/agented run <trigger-name> on <target>`"

    return trigger_name, target, None


def _get_slack_signing_secret() -> str:
    """Retrieve the Slack signing secret from the secrets vault."""
    try:
        from ..services.secret_vault_service import SecretVaultService

        if SecretVaultService.is_configured():
            from ..db import secrets as db_secrets

            secret = db_secrets.get_secret_by_name("slack_signing_secret")
            if secret:
                return SecretVaultService.decrypt(
                    secret["encrypted_value"],
                    purpose="slack_signature_verification",
                    accessor="slash_command_endpoint",
                )
    except (ImportError, Exception) as e:
        logger.warning("Could not retrieve Slack signing secret: %s", e)

    # Fallback to environment variable
    import os

    return os.environ.get("SLACK_SIGNING_SECRET", "")


def _dispatch_slash_command_execution(trigger: dict, target: str, response_url: str, user_id: str):
    """Run the trigger execution in a background thread and post results."""
    import httpx

    from ..services.execution_service import ExecutionService

    trigger_name = trigger["name"]
    try:
        execution_id = ExecutionService.run_trigger(
            trigger=trigger,
            message_text=target,
            trigger_type="slash_command",
        )

        result_text = (
            f"Execution `{execution_id}` for *{trigger_name}* completed."
            if execution_id
            else f"Failed to start *{trigger_name}*."
        )
    except Exception as e:
        logger.error("Slash command execution error: %s", e)
        result_text = f"Error running *{trigger_name}*: {str(e)[:200]}"

    # Post delayed response to Slack
    if response_url:
        try:
            httpx.post(
                response_url,
                json={
                    "response_type": "ephemeral",
                    "text": result_text,
                },
                timeout=10.0,
            )
        except Exception as e:
            logger.error("Failed to post delayed Slack response: %s", e)
