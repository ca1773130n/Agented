"""Tests verifying audit logging is called for destructive operations.

Covers TriggerService (create/update/delete), BackendService (account create/
update/delete), and SecretVaultService (create/update/delete/access).

Each test mocks out the DB layer and verifies that AuditLogService.log() or
AuditLogService.log_field_changes() is invoked with the correct parameters.
"""

from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# TriggerService — audit log coverage
# ---------------------------------------------------------------------------


class TestTriggerServiceAuditLogging:
    """Verify AuditLogService.log() is called for trigger create, update, delete."""

    @patch("app.services.trigger_service.AuditLogService")
    @patch("app.services.trigger_service.get_trigger_by_name", return_value=None)
    @patch("app.services.trigger_service.db_create_trigger", return_value="trg-abc123")
    def test_create_trigger_logs_audit_event(self, mock_create, mock_get_by_name, mock_audit):
        from app.services.trigger_service import TriggerService

        data = {
            "name": "Test Trigger",
            "prompt_template": "Do something with {paths}",
            "backend_type": "claude",
            "trigger_source": "manual",
        }

        result, status = TriggerService.create_trigger(data)

        assert status == HTTPStatus.CREATED
        mock_audit.log.assert_called_once_with(
            action="trigger.create",
            entity_type="trigger",
            entity_id="trg-abc123",
            outcome="created",
            details={
                "name": "Test Trigger",
                "backend_type": "claude",
                "trigger_source": "manual",
            },
        )

    @patch("app.services.trigger_service.AuditLogService")
    @patch("app.services.trigger_service.get_trigger_by_name", return_value=None)
    @patch("app.services.trigger_service.db_create_trigger", return_value=None)
    def test_create_trigger_no_audit_on_failure(self, mock_create, mock_get_by_name, mock_audit):
        """When trigger creation fails in DB, no audit event should be logged."""
        from app.services.trigger_service import TriggerService

        data = {
            "name": "Fail Trigger",
            "prompt_template": "template",
            "backend_type": "claude",
            "trigger_source": "manual",
        }

        result, status = TriggerService.create_trigger(data)

        assert status == HTTPStatus.INTERNAL_SERVER_ERROR
        mock_audit.log.assert_not_called()

    @patch("app.services.trigger_service.SchedulerService")
    @patch("app.services.trigger_service.AuditLogService")
    @patch("app.services.trigger_service.update_trigger", return_value=True)
    @patch(
        "app.services.trigger_service.get_trigger",
        side_effect=[
            # First call: existing trigger lookup
            {
                "id": "trg-001",
                "name": "Old Name",
                "prompt_template": "old",
                "is_predefined": False,
                "enabled": True,
            },
            # Second call: after update
            {
                "id": "trg-001",
                "name": "New Name",
                "prompt_template": "old",
                "is_predefined": False,
                "enabled": True,
            },
        ],
    )
    def test_update_trigger_logs_field_changes(
        self, mock_get, mock_update, mock_audit, mock_scheduler
    ):
        from app.services.trigger_service import TriggerService

        result, status = TriggerService.update_trigger("trg-001", {"name": "New Name"})

        assert status == HTTPStatus.OK
        mock_audit.log_field_changes.assert_called_once()
        call_kwargs = mock_audit.log_field_changes.call_args[1]
        assert call_kwargs["action"] == "trigger.update"
        assert call_kwargs["entity_type"] == "trigger"
        assert call_kwargs["entity_id"] == "trg-001"

    @patch("app.services.trigger_service.SchedulerService")
    @patch("app.services.trigger_service.AuditLogService")
    @patch("app.services.trigger_service.delete_trigger", return_value=True)
    @patch(
        "app.services.trigger_service.get_trigger",
        return_value={
            "id": "trg-del",
            "name": "Doomed Trigger",
            "is_predefined": False,
            "trigger_source": "webhook",
        },
    )
    def test_delete_trigger_logs_audit_event(
        self, mock_get, mock_delete, mock_audit, mock_scheduler
    ):
        from app.services.trigger_service import TriggerService

        result, status = TriggerService.delete_trigger("trg-del")

        assert status == HTTPStatus.OK
        mock_audit.log.assert_called_once_with(
            action="trigger.delete",
            entity_type="trigger",
            entity_id="trg-del",
            outcome="deleted",
            details={
                "name": "Doomed Trigger",
                "trigger_source": "webhook",
            },
        )

    @patch("app.services.trigger_service.SchedulerService")
    @patch("app.services.trigger_service.AuditLogService")
    @patch("app.services.trigger_service.delete_trigger", return_value=False)
    @patch(
        "app.services.trigger_service.get_trigger",
        return_value={
            "id": "trg-fail",
            "name": "Fail",
            "is_predefined": False,
            "trigger_source": "manual",
        },
    )
    def test_delete_trigger_no_audit_on_db_failure(
        self, mock_get, mock_delete, mock_audit, mock_scheduler
    ):
        """When the DB delete fails, no audit event should be logged."""
        from app.services.trigger_service import TriggerService

        result, status = TriggerService.delete_trigger("trg-fail")

        assert status == HTTPStatus.INTERNAL_SERVER_ERROR
        mock_audit.log.assert_not_called()

    @patch("app.services.trigger_service.AuditLogService")
    @patch(
        "app.services.trigger_service.get_trigger",
        return_value={
            "id": "trg-pre",
            "name": "Predefined",
            "is_predefined": True,
        },
    )
    def test_delete_predefined_trigger_no_audit(self, mock_get, mock_audit):
        """Predefined triggers cannot be deleted; no audit event should fire."""
        from app.services.trigger_service import TriggerService

        result, status = TriggerService.delete_trigger("trg-pre")

        assert status == HTTPStatus.FORBIDDEN
        mock_audit.log.assert_not_called()


# ---------------------------------------------------------------------------
# BackendService — audit log coverage
# ---------------------------------------------------------------------------


class TestBackendServiceAuditLogging:
    """Verify AuditLogService.log() is called for account create, update, delete."""

    def _make_body(self, **overrides):
        """Create a SimpleNamespace that mimics the request body model."""
        defaults = {
            "account_name": "test-account",
            "email": "test@example.com",
            "config_path": "/tmp/config",
            "api_key_env": None,
            "is_default": False,
            "plan": "pro",
            "usage_data": None,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    @patch("app.services.backend_service.get_backend_type", return_value="claude")
    @patch("app.services.backend_service.auto_enable_monitoring_for_account")
    @patch("app.services.backend_service.AuditLogService")
    @patch("app.services.backend_service.create_backend_account", return_value=42)
    @patch(
        "app.services.backend_service.get_backend_by_id",
        return_value={"id": "backend-claude", "type": "claude"},
    )
    def test_create_account_logs_audit_event(
        self, mock_get_backend, mock_create, mock_audit, mock_auto_mon, mock_get_type
    ):
        from app.services.backend_service import BackendService

        body = self._make_body()
        result, status = BackendService.create_account("backend-claude", body)

        assert status == HTTPStatus.CREATED
        mock_audit.log.assert_called_once_with(
            action="backend_account.create",
            entity_type="backend_account",
            entity_id="42",
            outcome="created",
            details={
                "backend_id": "backend-claude",
                "email": "test@example.com",
                "plan": "pro",
            },
        )

    @patch("app.services.backend_service.get_backend_type", return_value="claude")
    @patch("app.services.backend_service.AuditLogService")
    @patch("app.services.backend_service.update_backend_account", return_value=True)
    @patch(
        "app.services.backend_service.get_backend_by_id",
        return_value={"id": "backend-claude", "type": "claude"},
    )
    def test_update_account_logs_audit_event(
        self, mock_get_backend, mock_update, mock_audit, mock_get_type
    ):
        from app.services.backend_service import BackendService

        body = self._make_body(email="new@example.com")
        result, status = BackendService.update_account("backend-claude", 42, body)

        assert status == HTTPStatus.OK
        mock_audit.log.assert_called_once()
        call_kwargs = mock_audit.log.call_args[1]
        assert call_kwargs["action"] == "backend_account.update"
        assert call_kwargs["entity_type"] == "backend_account"
        assert call_kwargs["entity_id"] == "42"
        assert call_kwargs["outcome"] == "updated"
        assert "changed_fields" in call_kwargs["details"]

    @patch("app.services.backend_service.AuditLogService")
    @patch("app.services.backend_service.update_backend_account", return_value=False)
    @patch("app.services.backend_service.get_backend_by_id", return_value=None)
    def test_update_account_no_audit_when_not_found(
        self, mock_get_backend, mock_update, mock_audit
    ):
        from app.services.backend_service import BackendService

        body = self._make_body()
        result, status = BackendService.update_account("backend-missing", 99, body)

        assert status == HTTPStatus.NOT_FOUND
        mock_audit.log.assert_not_called()

    @patch("app.services.backend_service.AuditLogService")
    @patch("app.services.backend_service.delete_backend_account", return_value=True)
    @patch(
        "app.services.backend_service.get_backend_by_id",
        return_value={"id": "backend-claude"},
    )
    def test_delete_account_logs_audit_event(self, mock_get_backend, mock_delete, mock_audit):
        from app.services.backend_service import BackendService

        result, status = BackendService.delete_account("backend-claude", 42)

        assert status == HTTPStatus.OK
        mock_audit.log.assert_called_once_with(
            action="backend_account.delete",
            entity_type="backend_account",
            entity_id="42",
            outcome="deleted",
            details={"backend_id": "backend-claude"},
        )

    @patch("app.services.backend_service.AuditLogService")
    @patch("app.services.backend_service.delete_backend_account", return_value=False)
    @patch(
        "app.services.backend_service.get_backend_by_id",
        return_value={"id": "backend-claude"},
    )
    def test_delete_account_no_audit_when_not_found(
        self, mock_get_backend, mock_delete, mock_audit
    ):
        from app.services.backend_service import BackendService

        result, status = BackendService.delete_account("backend-claude", 999)

        assert status == HTTPStatus.NOT_FOUND
        mock_audit.log.assert_not_called()


# ---------------------------------------------------------------------------
# SecretVaultService — audit log coverage
# ---------------------------------------------------------------------------


class TestSecretVaultServiceAuditLogging:
    """Verify AuditLogService.log() / log_field_changes() is called for secret CRUD."""

    @pytest.fixture(autouse=True)
    def setup_vault_key(self, monkeypatch):
        """Provide a valid Fernet key for the vault."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        monkeypatch.setenv("AGENTED_VAULT_KEYS", key)
        from app.services.secret_vault_service import SecretVaultService

        SecretVaultService.reset()
        yield
        SecretVaultService.reset()

    @patch("app.services.secret_vault_service.AuditLogService")
    @patch("app.services.secret_vault_service.db_secrets")
    def test_create_secret_logs_audit_event(self, mock_db, mock_audit):
        from app.services.secret_vault_service import SecretVaultService

        mock_db.create_secret.return_value = "sec-abc123"

        secret_id = SecretVaultService.create_secret(
            name="MY_API_KEY",
            value="super-secret-value",
            description="Test key",
            scope="global",
            created_by="admin",
        )

        assert secret_id == "sec-abc123"
        mock_audit.log.assert_called_once_with(
            action="secret.create",
            entity_type="secret",
            entity_id="sec-abc123",
            outcome="created",
            details={
                "name": "MY_API_KEY",
                "scope": "global",
                "created_by": "admin",
            },
        )

    @patch("app.services.secret_vault_service.AuditLogService")
    @patch("app.services.secret_vault_service.db_secrets")
    def test_update_secret_logs_field_changes_and_rotation(self, mock_db, mock_audit):
        from app.services.secret_vault_service import SecretVaultService

        mock_db.get_secret.return_value = {
            "id": "sec-upd",
            "name": "KEY",
            "description": "old desc",
            "scope": "global",
            "encrypted_value": SecretVaultService.encrypt("old-value"),
        }
        mock_db.update_secret.return_value = True

        updated = SecretVaultService.update_secret(
            secret_id="sec-upd",
            value="new-value",
            description="new desc",
            actor="admin",
        )

        assert updated is True
        # Should call log_field_changes for metadata diff
        mock_audit.log_field_changes.assert_called_once()
        fc_kwargs = mock_audit.log_field_changes.call_args[1]
        assert fc_kwargs["action"] == "secret.update"
        assert fc_kwargs["entity_type"] == "secret"
        assert fc_kwargs["entity_id"] == "sec-upd"

        # Should also call log for value rotation
        mock_audit.log.assert_called_once_with(
            action="secret.value_rotated",
            entity_type="secret",
            entity_id="sec-upd",
            outcome="rotated",
            details={"actor": "admin"},
        )

    @patch("app.services.secret_vault_service.AuditLogService")
    @patch("app.services.secret_vault_service.db_secrets")
    def test_update_secret_no_rotation_log_without_value(self, mock_db, mock_audit):
        """When only description changes (no new value), no rotation event is logged."""
        from app.services.secret_vault_service import SecretVaultService

        mock_db.get_secret.return_value = {
            "id": "sec-meta",
            "name": "KEY",
            "description": "old",
            "scope": "global",
            "encrypted_value": SecretVaultService.encrypt("val"),
        }
        mock_db.update_secret.return_value = True

        updated = SecretVaultService.update_secret(
            secret_id="sec-meta",
            description="new description",
        )

        assert updated is True
        mock_audit.log_field_changes.assert_called_once()
        # No value rotation log
        mock_audit.log.assert_not_called()

    @patch("app.services.secret_vault_service.AuditLogService")
    @patch("app.services.secret_vault_service.db_secrets")
    def test_update_secret_no_audit_when_not_found(self, mock_db, mock_audit):
        from app.services.secret_vault_service import SecretVaultService

        mock_db.get_secret.return_value = None

        updated = SecretVaultService.update_secret(secret_id="sec-missing", value="val")

        assert updated is False
        mock_audit.log.assert_not_called()
        mock_audit.log_field_changes.assert_not_called()

    @patch("app.services.secret_vault_service.AuditLogService")
    @patch("app.services.secret_vault_service.db_secrets")
    def test_delete_secret_logs_field_changes(self, mock_db, mock_audit):
        from app.services.secret_vault_service import SecretVaultService

        mock_db.get_secret.return_value = {
            "id": "sec-del",
            "name": "DOOMED_KEY",
            "description": "will be deleted",
            "scope": "global",
            "created_by": "admin",
        }
        mock_db.delete_secret.return_value = True

        deleted = SecretVaultService.delete_secret("sec-del", actor="admin")

        assert deleted is True
        mock_audit.log_field_changes.assert_called_once()
        fc_kwargs = mock_audit.log_field_changes.call_args[1]
        assert fc_kwargs["action"] == "secret.delete"
        assert fc_kwargs["entity_type"] == "secret"
        assert fc_kwargs["entity_id"] == "sec-del"
        # old_entity should contain metadata, new_entity should be empty
        assert fc_kwargs["old_entity"]["name"] == "DOOMED_KEY"
        assert fc_kwargs["new_entity"] == {}

    @patch("app.services.secret_vault_service.AuditLogService")
    @patch("app.services.secret_vault_service.db_secrets")
    def test_delete_secret_no_audit_when_not_found(self, mock_db, mock_audit):
        from app.services.secret_vault_service import SecretVaultService

        mock_db.get_secret.return_value = None

        deleted = SecretVaultService.delete_secret("sec-gone")

        assert deleted is False
        mock_audit.log_field_changes.assert_not_called()

    @patch("app.services.secret_vault_service.AuditLogService")
    @patch("app.services.secret_vault_service.db_secrets")
    def test_delete_secret_no_audit_on_db_failure(self, mock_db, mock_audit):
        """When DB delete returns False, no audit event should fire."""
        from app.services.secret_vault_service import SecretVaultService

        mock_db.get_secret.return_value = {
            "id": "sec-fail",
            "name": "KEY",
            "description": "",
            "scope": "global",
            "created_by": "system",
        }
        mock_db.delete_secret.return_value = False

        deleted = SecretVaultService.delete_secret("sec-fail")

        assert deleted is False
        mock_audit.log_field_changes.assert_not_called()

    @patch("app.services.secret_vault_service.AuditLogService")
    @patch("app.services.secret_vault_service.db_secrets")
    def test_decrypt_logs_access_event(self, mock_db, mock_audit):
        """Every decrypt call should audit-log the access."""
        from app.services.secret_vault_service import SecretVaultService

        ciphertext = SecretVaultService.encrypt("plaintext-value")

        SecretVaultService.decrypt(
            ciphertext, purpose="sec-access-test", accessor="execution_service"
        )

        mock_audit.log.assert_called_once_with(
            action="secret.access",
            entity_type="secret",
            entity_id="sec-access-test",
            outcome="accessed",
            details={"accessor": "execution_service"},
        )

    @patch("app.services.secret_vault_service.AuditLogService")
    @patch("app.services.secret_vault_service.db_secrets")
    def test_rotate_key_logs_audit_event(self, mock_db, mock_audit):
        from app.services.secret_vault_service import SecretVaultService

        mock_db.list_secrets.return_value = []

        count = SecretVaultService.rotate_key("unused-arg")

        assert count == 0
        mock_audit.log.assert_called_once_with(
            action="secret.key_rotation",
            entity_type="vault",
            entity_id="vault",
            outcome="rotated",
            details={"secrets_rotated": 0},
        )
