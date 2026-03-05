"""Integration configuration service.

Handles creating, configuring, and testing integrations. Retrieves credentials
from SecretVaultService and instantiates the appropriate adapter.
"""

import logging
from typing import Optional, Tuple

from app.db import integrations as db_integrations
from app.models.integration import IntegrationCreate
from app.services.audit_log_service import AuditLogService
from app.services.integrations import IntegrationAdapter, get_adapter

logger = logging.getLogger(__name__)

# Credential keys expected by each adapter type
ADAPTER_CREDENTIAL_KEYS = {
    "slack": ["token"],
    "teams": ["webhook_url"],
    "jira": ["server", "email", "api_token"],
    "linear": ["api_key"],
}


class IntegrationConfigService:
    """Manage integration lifecycle: create, configure, test, get adapter."""

    @staticmethod
    def create_integration(data: IntegrationCreate) -> str:
        """Create an integration, validate its config, and store in DB.

        If secret_name is provided, verifies the secret exists in the vault.
        Returns the integration ID.
        """
        # Validate integration type is known
        if data.type not in ("slack", "teams", "jira", "linear"):
            raise ValueError(f"Unknown integration type: {data.type}")

        # If secret_name provided, verify it exists
        if data.secret_name:
            try:
                from app.services.secret_vault_service import SecretVaultService

                if SecretVaultService.is_configured():
                    from app.db import secrets as db_secrets

                    secret = db_secrets.get_secret_by_name(data.secret_name)
                    if not secret:
                        raise ValueError(f"Secret '{data.secret_name}' not found in vault")
            except ImportError:
                logger.warning("SecretVaultService not available; skipping secret verification")

        # Store config with secret_name reference (not the actual secret)
        config = dict(data.config)
        if data.secret_name:
            config["secret_name"] = data.secret_name

        integration_id = db_integrations.create_integration(
            name=data.name,
            integration_type=data.type,
            config=config,
            trigger_id=data.trigger_id,
            enabled=True,
        )

        AuditLogService.log(
            action="integration.create",
            entity_type="integration",
            entity_id=integration_id,
            outcome="created",
            details={"type": data.type, "name": data.name},
        )

        return integration_id

    @staticmethod
    def get_adapter_for_integration(integration_id: str) -> Optional[IntegrationAdapter]:
        """Load an integration from DB and return a configured adapter instance.

        Retrieves credentials from SecretVaultService if a secret_name is configured.
        """
        integration = db_integrations.get_integration(integration_id)
        if not integration:
            return None

        config = integration.get("config", {})
        adapter_type = integration["type"]
        credential_keys = ADAPTER_CREDENTIAL_KEYS.get(adapter_type, [])

        # Build kwargs from config
        kwargs = {}
        for key in credential_keys:
            if key in config:
                kwargs[key] = config[key]

        # If secret_name is set, retrieve credentials from vault
        secret_name = config.get("secret_name")
        if secret_name:
            try:
                from app.services.secret_vault_service import SecretVaultService

                if SecretVaultService.is_configured():
                    import json

                    from app.db import secrets as db_secrets

                    secret_record = db_secrets.get_secret_by_name(secret_name)
                    if secret_record:
                        plaintext = SecretVaultService.decrypt(
                            secret_record["encrypted_value"],
                            purpose=f"integration:{adapter_type}",
                            accessor="integration_config_service",
                        )
                        try:
                            creds = json.loads(plaintext)
                            kwargs.update(creds)
                        except json.JSONDecodeError:
                            # Single value secret (e.g., just a token)
                            if len(credential_keys) == 1:
                                kwargs[credential_keys[0]] = plaintext
            except ImportError:
                logger.warning("SecretVaultService not available; using config-only credentials")

        adapter = get_adapter(adapter_type, **kwargs)
        return adapter

    @staticmethod
    def test_integration(integration_id: str) -> Tuple[bool, str]:
        """Send a test notification via the integration.

        Returns (success, message).
        """
        adapter = IntegrationConfigService.get_adapter_for_integration(integration_id)
        if not adapter:
            return False, "Integration not found or adapter unavailable"

        integration = db_integrations.get_integration(integration_id)
        config = integration.get("config", {})
        channel = config.get("channel", config.get("webhook_url", "test"))

        try:
            success = adapter.send_notification(
                channel=channel,
                message="Agented integration test -- this message confirms your integration is working.",
                metadata={"status": "success", "bot_name": "Agented", "duration": "0s"},
            )
            if success:
                AuditLogService.log(
                    action="integration.test",
                    entity_type="integration",
                    entity_id=integration_id,
                    outcome="success",
                )
                return True, "Test notification sent successfully"
            else:
                return False, "Adapter returned failure"
        except Exception as e:
            logger.error("Integration test error: %s", e, exc_info=True)
            return False, f"Error: {str(e)}"
