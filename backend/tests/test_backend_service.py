"""Tests for BackendService."""

from http import HTTPStatus
from unittest.mock import MagicMock, patch

import pytest

from app.services.backend_service import BackendService, _resolve_backend_id


# =============================================================================
# _resolve_backend_id() tests
# =============================================================================


class TestResolveBackendId:
    """Tests for the _resolve_backend_id helper."""

    @patch("app.services.backend_service.get_backend_by_id")
    def test_returns_id_when_found_directly(self, mock_get):
        mock_get.return_value = {"id": "backend-claude"}
        assert _resolve_backend_id("backend-claude") == "backend-claude"
        mock_get.assert_called_once_with("backend-claude")

    @patch("app.services.backend_service.get_backend_by_id")
    def test_tries_prefixed_id_when_not_found(self, mock_get):
        mock_get.side_effect = [None, {"id": "backend-claude"}]
        assert _resolve_backend_id("claude") == "backend-claude"

    @patch("app.services.backend_service.get_backend_by_id")
    def test_returns_original_when_neither_found(self, mock_get):
        mock_get.return_value = None
        assert _resolve_backend_id("nonexistent") == "nonexistent"


# =============================================================================
# BackendService.get_backend() tests
# =============================================================================


class TestGetBackend:
    """Tests for BackendService.get_backend()."""

    @patch("app.services.backend_service.get_backend_accounts")
    @patch("app.services.backend_service.get_backend_by_id")
    def test_returns_backend_with_accounts(self, mock_get_backend, mock_get_accounts):
        mock_get_backend.return_value = {"id": "backend-claude", "type": "claude"}
        mock_get_accounts.return_value = [{"id": 1, "email": "a@b.com"}]

        result, status = BackendService.get_backend("backend-claude")

        assert status == HTTPStatus.OK
        assert result["id"] == "backend-claude"
        assert result["accounts"] == [{"id": 1, "email": "a@b.com"}]

    @patch("app.services.backend_service.get_backend_by_id")
    def test_returns_not_found_for_missing_backend(self, mock_get_backend):
        mock_get_backend.return_value = None

        result, status = BackendService.get_backend("nonexistent")

        assert status == HTTPStatus.NOT_FOUND
        assert "error" in result or "code" in result


# =============================================================================
# BackendService.check_backend() tests
# =============================================================================


class TestCheckBackend:
    """Tests for BackendService.check_backend()."""

    @patch("app.services.backend_service.get_capabilities")
    @patch("app.services.backend_service.check_and_update_backend_installed")
    @patch("app.services.backend_service.detect_backend")
    @patch("app.services.backend_service.get_backend_type")
    @patch("app.services.backend_service.get_backend_by_id")
    def test_returns_installed_status(
        self, mock_resolve, mock_type, mock_detect, mock_update, mock_caps
    ):
        mock_resolve.return_value = {"id": "backend-claude"}
        mock_type.return_value = "claude"
        mock_detect.return_value = (True, "2.1.0", "/usr/bin/claude")
        mock_caps.return_value = None  # No capabilities, avoids asdict() on MagicMock

        result, status = BackendService.check_backend("backend-claude")

        assert status == HTTPStatus.OK
        assert result["installed"] is True
        assert result["version"] == "2.1.0"
        assert result["cli_path"] == "/usr/bin/claude"
        assert result["capabilities"] is None
        mock_update.assert_called_once_with("backend-claude", True, "2.1.0")

    @patch("app.services.backend_service.get_backend_type")
    @patch("app.services.backend_service.get_backend_by_id")
    def test_returns_not_found_for_unknown_type(self, mock_resolve, mock_type):
        mock_resolve.return_value = {"id": "backend-x"}
        mock_type.return_value = None

        result, status = BackendService.check_backend("backend-x")

        assert status == HTTPStatus.NOT_FOUND


# =============================================================================
# BackendService.create_account() tests
# =============================================================================


class TestCreateAccount:
    """Tests for BackendService.create_account()."""

    @patch("app.services.backend_service.get_backend_type")
    @patch("app.services.backend_service.AuditLogService")
    @patch("app.services.backend_service.auto_enable_monitoring_for_account")
    @patch("app.services.backend_service.create_backend_account")
    @patch("app.services.backend_service.get_backend_by_id")
    def test_creates_account_successfully(
        self, mock_get_backend, mock_create, mock_auto_mon, mock_audit, mock_btype
    ):
        mock_get_backend.return_value = {"id": "backend-claude"}
        mock_create.return_value = 42
        mock_btype.return_value = "opencode"  # Not claude, so no CLIProxy logic

        body = MagicMock()
        body.account_name = "Test"
        body.email = "test@test.com"
        body.config_path = None
        body.api_key_env = None
        body.is_default = False
        body.plan = "free"
        body.usage_data = None

        result, status = BackendService.create_account("backend-claude", body)

        assert status == HTTPStatus.CREATED
        assert result["account_id"] == 42
        mock_create.assert_called_once()
        mock_auto_mon.assert_called_once_with(42)

    @patch("app.services.backend_service.get_backend_by_id")
    def test_create_account_backend_not_found(self, mock_get_backend):
        mock_get_backend.return_value = None

        body = MagicMock()
        result, status = BackendService.create_account("nonexistent", body)

        assert status == HTTPStatus.NOT_FOUND


# =============================================================================
# BackendService.update_account() tests
# =============================================================================


class TestUpdateAccount:
    """Tests for BackendService.update_account()."""

    @patch("app.services.backend_service.get_backend_type")
    @patch("app.services.backend_service.AuditLogService")
    @patch("app.services.backend_service.update_backend_account")
    def test_updates_account_successfully(self, mock_update, mock_audit, mock_btype):
        mock_update.return_value = True
        mock_btype.return_value = "opencode"

        body = MagicMock()
        body.account_name = "Updated"
        body.email = "new@test.com"
        body.config_path = None
        body.api_key_env = None
        body.is_default = None
        body.plan = None
        body.usage_data = None

        result, status = BackendService.update_account("backend-claude", 1, body)

        assert status == HTTPStatus.OK
        assert result["message"] == "Account updated"

    @patch("app.services.backend_service.update_backend_account")
    def test_update_account_not_found(self, mock_update):
        mock_update.return_value = False

        body = MagicMock()
        result, status = BackendService.update_account("backend-claude", 999, body)

        assert status == HTTPStatus.NOT_FOUND

    @patch("app.services.backend_service.update_backend_account")
    def test_update_account_no_updates_provided(self, mock_update):
        mock_update.return_value = True

        body = MagicMock()
        body.account_name = None
        body.email = None
        body.config_path = None
        body.api_key_env = None
        body.is_default = None
        body.plan = None
        body.usage_data = None

        result, status = BackendService.update_account("backend-claude", 1, body)

        assert status == HTTPStatus.OK
        assert result["message"] == "No updates provided"


# =============================================================================
# BackendService.delete_account() tests
# =============================================================================


class TestDeleteAccount:
    """Tests for BackendService.delete_account()."""

    @patch("app.services.backend_service.AuditLogService")
    @patch("app.services.backend_service.delete_backend_account")
    def test_deletes_account_successfully(self, mock_delete, mock_audit):
        mock_delete.return_value = True

        result, status = BackendService.delete_account("backend-claude", 1)

        assert status == HTTPStatus.OK
        assert result["message"] == "Account deleted"
        mock_delete.assert_called_once_with(1, "backend-claude")

    @patch("app.services.backend_service.delete_backend_account")
    def test_delete_account_not_found(self, mock_delete):
        mock_delete.return_value = False

        result, status = BackendService.delete_account("backend-claude", 999)

        assert status == HTTPStatus.NOT_FOUND


# =============================================================================
# BackendService.install_backend_cli() tests
# =============================================================================


class TestInstallBackendCli:
    """Tests for BackendService.install_backend_cli()."""

    @patch("app.services.backend_service.detect_backend")
    @patch("app.services.backend_service.get_backend_type")
    @patch("app.services.backend_service.get_backend_by_id")
    def test_returns_already_installed(self, mock_resolve, mock_type, mock_detect):
        mock_resolve.return_value = {"id": "backend-claude"}
        mock_type.return_value = "claude"
        mock_detect.return_value = (True, "2.1.0", "/usr/bin/claude")

        result, status = BackendService.install_backend_cli("backend-claude")

        assert status == HTTPStatus.OK
        assert "already installed" in result["message"]

    @patch("app.services.backend_service.check_and_update_backend_installed")
    @patch("app.services.backend_service.install_cli")
    @patch("app.services.backend_service.detect_backend")
    @patch("app.services.backend_service.get_backend_type")
    @patch("app.services.backend_service.get_backend_by_id")
    def test_installs_cli_successfully(
        self, mock_resolve, mock_type, mock_detect, mock_install, mock_update
    ):
        mock_resolve.return_value = {"id": "backend-claude"}
        mock_type.return_value = "claude"
        mock_detect.return_value = (False, None, None)
        mock_install.return_value = {"success": True, "version": "2.1.0"}

        result, status = BackendService.install_backend_cli("backend-claude")

        assert status == HTTPStatus.OK
        assert "installed successfully" in result["message"]
        mock_update.assert_called_once()

    @patch("app.services.backend_service.install_cli")
    @patch("app.services.backend_service.detect_backend")
    @patch("app.services.backend_service.get_backend_type")
    @patch("app.services.backend_service.get_backend_by_id")
    def test_install_cli_failure(self, mock_resolve, mock_type, mock_detect, mock_install):
        mock_resolve.return_value = {"id": "backend-claude"}
        mock_type.return_value = "claude"
        mock_detect.return_value = (False, None, None)
        mock_install.return_value = {"success": False, "error": "npm not found"}

        result, status = BackendService.install_backend_cli("backend-claude")

        assert status == HTTPStatus.INTERNAL_SERVER_ERROR
        assert "error" in result

    @patch("app.services.backend_service.get_backend_type")
    @patch("app.services.backend_service.get_backend_by_id")
    def test_install_cli_backend_not_found(self, mock_resolve, mock_type):
        mock_resolve.return_value = None
        mock_type.return_value = None

        result, status = BackendService.install_backend_cli("nonexistent")

        assert status == HTTPStatus.NOT_FOUND


# =============================================================================
# BackendService.discover_models() tests
# =============================================================================


class TestDiscoverModels:
    """Tests for BackendService.discover_models()."""

    @patch("app.services.backend_service.update_backend_models")
    @patch("app.services.backend_service.get_backend_type")
    @patch("app.services.backend_service.get_backend_by_id")
    def test_discovers_models(self, mock_resolve, mock_type, mock_update):
        mock_resolve.return_value = {"id": "backend-claude"}
        mock_type.return_value = "claude"

        with patch(
            "app.services.model_discovery_service.ModelDiscoveryService.discover_models",
            return_value=["claude-3-opus", "claude-3-sonnet"],
        ):
            result, status = BackendService.discover_models("backend-claude")

        assert status == HTTPStatus.OK
        assert result["models"] == ["claude-3-opus", "claude-3-sonnet"]
        mock_update.assert_called_once()

    @patch("app.services.backend_service.get_backend_type")
    @patch("app.services.backend_service.get_backend_by_id")
    def test_discover_models_backend_not_found(self, mock_resolve, mock_type):
        mock_resolve.return_value = None
        mock_type.return_value = None

        result, status = BackendService.discover_models("nonexistent")

        assert status == HTTPStatus.NOT_FOUND

    @patch("app.services.backend_service.update_backend_models")
    @patch("app.services.backend_service.get_backend_type")
    @patch("app.services.backend_service.get_backend_by_id")
    def test_discover_models_empty_list(self, mock_resolve, mock_type, mock_update):
        mock_resolve.return_value = {"id": "backend-claude"}
        mock_type.return_value = "claude"

        with patch(
            "app.services.model_discovery_service.ModelDiscoveryService.discover_models",
            return_value=[],
        ):
            result, status = BackendService.discover_models("backend-claude")

        assert status == HTTPStatus.OK
        assert result["models"] == []
        mock_update.assert_not_called()
