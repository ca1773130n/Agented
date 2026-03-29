"""Backend management service."""

import logging
from dataclasses import asdict
from http import HTTPStatus
from typing import Optional, Tuple

from app.models.common import error_response

from ..db.backends import (
    auto_enable_monitoring_for_account,
    check_and_update_backend_installed,
    create_backend_account,
    delete_backend_account,
    get_account_with_backend,
    get_all_backends,
    get_backend_accounts,
    get_backend_accounts_for_auth,
    get_backend_by_id,
    get_backend_type,
    update_backend_account,
    update_backend_models,
    verify_account_exists,
)
from ..services.audit_log_service import AuditLogService
from ..services.backend_detection_service import detect_backend, get_capabilities, install_cli

logger = logging.getLogger(__name__)


def _resolve_backend_id(backend_id: str) -> str:
    """Resolve a backend ID, trying with 'backend-' prefix if not found."""
    if get_backend_by_id(backend_id):
        return backend_id
    prefixed = f"backend-{backend_id}"
    if get_backend_by_id(prefixed):
        return prefixed
    return backend_id


class BackendService:
    """Service for backend management and account operations."""

    @staticmethod
    def list_backends(limit=None, offset=0) -> Tuple[dict, HTTPStatus]:
        """List all backends with live-discovered model lists.

        Runs model discovery for all backends concurrently on every request.
        No caching — always returns fresh models from CLI introspection.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        from ..db.backends import count_all_backends
        from ..services.model_discovery_service import ModelDiscoveryService

        backends = get_all_backends(limit=limit, offset=offset)
        total_count = count_all_backends()

        # Build map of backend_type -> backend dict(s) for overlay
        type_to_backends: dict[str, list[dict]] = {}
        for backend in backends:
            btype = backend.get("type")
            if btype:
                type_to_backends.setdefault(btype, []).append(backend)

        # Discover models for all backend types concurrently
        def _discover(btype: str) -> tuple[str, list[str]]:
            try:
                return btype, ModelDiscoveryService.discover_models(btype)
            except Exception as e:
                logger.warning("Model discovery for %s failed: %s", btype, e)
                return btype, []

        if type_to_backends:
            with ThreadPoolExecutor(max_workers=len(type_to_backends)) as pool:
                futures = {pool.submit(_discover, bt): bt for bt in type_to_backends}
                for future in as_completed(futures):
                    btype, models = future.result()
                    for backend in type_to_backends.get(btype, []):
                        if models:
                            backend["models"] = models
                            update_backend_models(backend["id"], models)

        return {"backends": backends, "total_count": total_count}, HTTPStatus.OK

    @staticmethod
    def get_backend(backend_id: str) -> Tuple[dict, HTTPStatus]:
        """Get a backend with its accounts."""
        backend_id = _resolve_backend_id(backend_id)
        backend = get_backend_by_id(backend_id)
        if not backend:
            return error_response("NOT_FOUND", "Backend not found", HTTPStatus.NOT_FOUND)

        accounts = get_backend_accounts(backend_id)
        backend["accounts"] = accounts

        return backend, HTTPStatus.OK

    @staticmethod
    def check_backend(backend_id: str) -> Tuple[dict, HTTPStatus]:
        """Check if a backend is installed and return capabilities."""
        backend_id = _resolve_backend_id(backend_id)
        btype = get_backend_type(backend_id)
        if not btype:
            return error_response("NOT_FOUND", "Backend not found", HTTPStatus.NOT_FOUND)

        installed, version, cli_path = detect_backend(btype)

        # Update the database
        check_and_update_backend_installed(backend_id, installed, version)

        # Get capabilities from static config (deterministic per backend type)
        capabilities = get_capabilities(btype)
        caps_dict = asdict(capabilities) if capabilities else None

        return {
            "installed": installed,
            "version": version,
            "cli_path": cli_path,
            "capabilities": caps_dict,
        }, HTTPStatus.OK

    @staticmethod
    def create_account(backend_id: str, body) -> Tuple[dict, HTTPStatus]:
        """Add an account to a backend."""
        backend_id = _resolve_backend_id(backend_id)
        # Check backend exists
        backend = get_backend_by_id(backend_id)
        if not backend:
            return error_response("NOT_FOUND", "Backend not found", HTTPStatus.NOT_FOUND)

        account_id = create_backend_account(
            backend_id=backend_id,
            account_name=body.account_name,
            email=body.email,
            config_path=body.config_path,
            api_key_env=body.api_key_env,
            is_default=body.is_default,
            plan=body.plan,
            usage_data=body.usage_data,
        )

        # Auto-enable monitoring if global monitoring is on
        auto_enable_monitoring_for_account(account_id)

        AuditLogService.log(
            action="backend_account.create",
            entity_type="backend_account",
            entity_id=str(account_id),
            outcome="created",
            details={"backend_id": backend_id, "email": body.email, "plan": body.plan},
        )

        # Ensure global CLIProxyAPI is running for Claude Code accounts
        backend_type = get_backend_type(backend_id)
        if backend_type == "claude":
            try:
                from ..services.cliproxy_manager import CLIProxyManager

                if CLIProxyManager.install_if_needed():
                    CLIProxyManager.start()
            except Exception as e:
                logger.warning("CLIProxy start failed: %s", e)  # Non-fatal — proxy is optional

        # Install harness plugins into the Claude account's config directory
        if backend_type == "claude" and body.config_path:
            try:
                from .harness_plugin_installer import HarnessPluginInstaller

                HarnessPluginInstaller.ensure_plugins_installed(body.config_path)
            except Exception as e:
                logger.warning("Harness plugin install failed: %s", e)

        return {"message": "Account created", "account_id": account_id}, HTTPStatus.CREATED

    @staticmethod
    def update_account(backend_id: str, account_id: int, body) -> Tuple[dict, HTTPStatus]:
        """Update an account."""
        found = update_backend_account(
            account_id=account_id,
            backend_id=backend_id,
            account_name=body.account_name,
            email=body.email,
            config_path=body.config_path,
            api_key_env=body.api_key_env,
            is_default=body.is_default,
            plan=body.plan,
            usage_data=body.usage_data,
        )
        if not found:
            return error_response("NOT_FOUND", "Account not found", HTTPStatus.NOT_FOUND)

        # Check if any fields were actually provided
        has_updates = any(
            getattr(body, f) is not None
            for f in [
                "account_name",
                "email",
                "config_path",
                "api_key_env",
                "is_default",
                "plan",
                "usage_data",
            ]
        )
        if not has_updates:
            return {"message": "No updates provided"}, HTTPStatus.OK

        AuditLogService.log(
            action="backend_account.update",
            entity_type="backend_account",
            entity_id=str(account_id),
            outcome="updated",
            details={
                "backend_id": backend_id,
                "changed_fields": [
                    f
                    for f in [
                        "account_name",
                        "email",
                        "config_path",
                        "api_key_env",
                        "is_default",
                        "plan",
                        "usage_data",
                    ]
                    if getattr(body, f) is not None
                ],
            },
        )

        # Install harness plugins if config_path was updated on a Claude backend
        if body.config_path is not None:
            btype = get_backend_type(backend_id)
            if btype == "claude":
                try:
                    from .harness_plugin_installer import HarnessPluginInstaller

                    HarnessPluginInstaller.ensure_plugins_installed(body.config_path)
                except Exception as e:
                    logger.warning("Harness plugin install failed: %s", e)

        return {"message": "Account updated"}, HTTPStatus.OK

    @staticmethod
    def delete_account(backend_id: str, account_id: int) -> Tuple[dict, HTTPStatus]:
        """Delete an account."""
        deleted = delete_backend_account(account_id, backend_id)
        if not deleted:
            return error_response("NOT_FOUND", "Account not found", HTTPStatus.NOT_FOUND)

        AuditLogService.log(
            action="backend_account.delete",
            entity_type="backend_account",
            entity_id=str(account_id),
            outcome="deleted",
            details={"backend_id": backend_id},
        )

        return {"message": "Account deleted"}, HTTPStatus.OK

    @staticmethod
    def install_backend_cli(backend_id: str) -> Tuple[dict, HTTPStatus]:
        """Install a missing CLI for a backend."""
        backend_id = _resolve_backend_id(backend_id)
        btype = get_backend_type(backend_id)
        if not btype:
            return error_response("NOT_FOUND", "Backend not found", HTTPStatus.NOT_FOUND)

        # Check if already installed
        installed, version, _ = detect_backend(btype)
        if installed:
            return {
                "message": f"{btype} CLI is already installed",
                "version": version,
            }, HTTPStatus.OK

        result = install_cli(btype)
        if result["success"]:
            check_and_update_backend_installed(backend_id, True, result["version"])
            return {
                "message": f"{btype} CLI installed successfully",
                "version": result["version"],
            }, HTTPStatus.OK
        return {
            "error": f"Failed to install {btype} CLI: {result['error']}",
        }, HTTPStatus.INTERNAL_SERVER_ERROR

    @staticmethod
    def start_connect(
        backend_id: str, config_path: Optional[str] = None, email: Optional[str] = None,
        account_name: Optional[str] = None,
    ) -> Tuple[dict, HTTPStatus]:
        """Start an OAuth login session for a backend CLI."""
        from ..services.backend_cli_service import BACKEND_CLI_COMMANDS, BackendCLIService

        backend_id = _resolve_backend_id(backend_id)
        btype = get_backend_type(backend_id)
        if not btype:
            return error_response("NOT_FOUND", "Backend not found", HTTPStatus.NOT_FOUND)

        if btype not in BACKEND_CLI_COMMANDS:
            return {
                "error": f"Backend type '{btype}' does not support CLI login"
            }, HTTPStatus.BAD_REQUEST

        # Check CLI is installed
        installed, _, _ = detect_backend(btype)
        if not installed:
            return error_response(
                "BAD_REQUEST", f"{btype} CLI is not installed", HTTPStatus.BAD_REQUEST
            )

        try:
            session_id = BackendCLIService.start_session(
                backend_id=backend_id,
                backend_type=btype,
                action="login",
                config_path=config_path,
                email=email,
                account_name=account_name,
            )
        except ValueError as e:
            return error_response("BAD_REQUEST", str(e), HTTPStatus.BAD_REQUEST)
        except Exception as e:
            return error_response(
                "INTERNAL_SERVER_ERROR",
                f"Failed to start login: {e}",
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

        return {"session_id": session_id, "status": "running"}, HTTPStatus.CREATED

    @staticmethod
    def check_rate_limits(backend_id: str, account_id: int) -> Tuple[dict, HTTPStatus]:
        """Check rate limits for a backend account via provider API."""
        from ..services.provider_usage_client import ProviderUsageClient

        backend_id = _resolve_backend_id(backend_id)
        account = get_account_with_backend(account_id)
        if not account or account.get("backend_id") != backend_id:
            return error_response("NOT_FOUND", "Account not found", HTTPStatus.NOT_FOUND)

        backend_type = account.get("backend_type", "claude")

        try:
            windows = ProviderUsageClient.fetch_usage(account, backend_type)
        except Exception as e:
            return error_response(
                "INTERNAL_SERVER_ERROR", f"Provider API error: {e}", HTTPStatus.BAD_GATEWAY
            )

        if not windows:
            default_paths = {"claude": "~/.claude", "codex": "~/.codex", "gemini": "~/.gemini"}
            config_path = account.get("config_path", default_paths.get(backend_type, ""))
            hint = f"No credentials found at {config_path}. Use the Login button to authenticate."
            return {
                "windows": [],
                "message": hint,
                "needs_login": True,
                "account_id": account.get("id"),
            }, HTTPStatus.OK

        return {"windows": windows}, HTTPStatus.OK

    @staticmethod
    def check_account_usage(backend_id: str, account_id: int) -> Tuple[dict, HTTPStatus]:
        """Run a one-shot usage check for a backend account."""
        from ..services.backend_cli_service import BACKEND_CLI_COMMANDS, BackendCLIService

        backend_id = _resolve_backend_id(backend_id)
        btype = get_backend_type(backend_id)
        if not btype:
            return error_response("NOT_FOUND", "Backend not found", HTTPStatus.NOT_FOUND)

        if btype not in BACKEND_CLI_COMMANDS:
            return {
                "error": f"Backend type '{btype}' does not support usage check"
            }, HTTPStatus.BAD_REQUEST

        # Verify account exists
        if not verify_account_exists(account_id, backend_id):
            return error_response("NOT_FOUND", "Account not found", HTTPStatus.NOT_FOUND)

        # Check CLI is installed
        installed, _, _ = detect_backend(btype)
        if not installed:
            return error_response(
                "BAD_REQUEST", f"{btype} CLI is not installed", HTTPStatus.BAD_REQUEST
            )

        result = BackendCLIService.run_usage_oneshot(btype)
        return result, HTTPStatus.OK

    @staticmethod
    def check_auth_status(backend_id: str) -> Tuple[dict, HTTPStatus]:
        """Check authentication status for a backend by probing stored credentials."""
        from ..services.provider_usage_client import CredentialResolver

        backend_id = _resolve_backend_id(backend_id)
        btype = get_backend_type(backend_id)
        if not btype:
            return error_response("NOT_FOUND", "Backend not found", HTTPStatus.NOT_FOUND)

        # Get all accounts for this backend
        rows = get_backend_accounts_for_auth(backend_id)

        accounts = []
        for row in rows:
            account = row
            has_token = False
            email = account.get("email", "")

            if btype == "claude":
                token = CredentialResolver.get_claude_token(account)
                has_token = token is not None
            elif btype == "codex":
                token, _ = CredentialResolver.get_codex_token(account)
                has_token = token is not None
            elif btype == "gemini":
                token = CredentialResolver.get_gemini_token(account)
                has_token = token is not None

            accounts.append(
                {
                    "account_id": account["id"],
                    "name": account.get("account_name", ""),
                    "email": email,
                    "authenticated": has_token,
                }
            )

        return {
            "backend_type": btype,
            "accounts": accounts,
            "login_instruction": "Use the Login button on each account to authenticate.",
        }, HTTPStatus.OK

    @staticmethod
    def discover_models(backend_id: str) -> Tuple[dict, HTTPStatus]:
        """Discover available models for a backend via CLI introspection."""
        from ..services.model_discovery_service import ModelDiscoveryService

        backend_id = _resolve_backend_id(backend_id)
        btype = get_backend_type(backend_id)
        if not btype:
            return error_response("NOT_FOUND", "Backend not found", HTTPStatus.NOT_FOUND)

        models = ModelDiscoveryService.discover_models(btype)
        if models:
            update_backend_models(backend_id, models)

        return {"models": models, "backend_id": backend_id}, HTTPStatus.OK
