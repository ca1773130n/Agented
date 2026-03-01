"""Backend management service."""

import logging
from dataclasses import asdict
from http import HTTPStatus
from typing import Tuple

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
from ..services.backend_detection_service import detect_backend, get_capabilities

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
    def list_backends() -> Tuple[dict, HTTPStatus]:
        """List all backends with DB-cached model lists.

        Model discovery is intentionally NOT triggered here — it runs
        subprocess/PTY calls that take 15+ seconds per backend and would
        block the single gevent worker.  The frontend calls the separate
        POST /discover-models endpoint via autoCheckBackends() instead.
        """
        backends = get_all_backends()
        return {"backends": backends}, HTTPStatus.OK

    @staticmethod
    def get_backend(backend_id: str) -> Tuple[dict, HTTPStatus]:
        """Get a backend with its accounts."""
        backend_id = _resolve_backend_id(backend_id)
        backend = get_backend_by_id(backend_id)
        if not backend:
            return {"error": "Backend not found"}, HTTPStatus.NOT_FOUND

        accounts = get_backend_accounts(backend_id)
        backend["accounts"] = accounts

        return backend, HTTPStatus.OK

    @staticmethod
    def check_backend(backend_id: str) -> Tuple[dict, HTTPStatus]:
        """Check if a backend is installed and return capabilities."""
        backend_id = _resolve_backend_id(backend_id)
        btype = get_backend_type(backend_id)
        if not btype:
            return {"error": "Backend not found"}, HTTPStatus.NOT_FOUND

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
            return {"error": "Backend not found"}, HTTPStatus.NOT_FOUND

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
            return {"error": "Account not found"}, HTTPStatus.NOT_FOUND

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

        return {"message": "Account updated"}, HTTPStatus.OK

    @staticmethod
    def delete_account(backend_id: str, account_id: int) -> Tuple[dict, HTTPStatus]:
        """Delete an account."""
        deleted = delete_backend_account(account_id, backend_id)
        if not deleted:
            return {"error": "Account not found"}, HTTPStatus.NOT_FOUND

        AuditLogService.log(
            action="backend_account.delete",
            entity_type="backend_account",
            entity_id=str(account_id),
            outcome="deleted",
            details={"backend_id": backend_id},
        )

        return {"message": "Account deleted"}, HTTPStatus.OK

    @staticmethod
    def start_connect(backend_id: str) -> Tuple[dict, HTTPStatus]:
        """Start an OAuth login session for a backend CLI."""
        from ..services.backend_cli_service import BACKEND_CLI_COMMANDS, BackendCLIService

        backend_id = _resolve_backend_id(backend_id)
        btype = get_backend_type(backend_id)
        if not btype:
            return {"error": "Backend not found"}, HTTPStatus.NOT_FOUND

        if btype not in BACKEND_CLI_COMMANDS:
            return {
                "error": f"Backend type '{btype}' does not support CLI login"
            }, HTTPStatus.BAD_REQUEST

        # Check CLI is installed
        installed, _, _ = detect_backend(btype)
        if not installed:
            return {"error": f"{btype} CLI is not installed"}, HTTPStatus.BAD_REQUEST

        try:
            session_id = BackendCLIService.start_session(
                backend_id=backend_id,
                backend_type=btype,
                action="login",
            )
        except ValueError as e:
            return {"error": str(e)}, HTTPStatus.BAD_REQUEST
        except Exception as e:
            return {"error": f"Failed to start login: {e}"}, HTTPStatus.INTERNAL_SERVER_ERROR

        return {"session_id": session_id, "status": "running"}, HTTPStatus.CREATED

    @staticmethod
    def check_rate_limits(backend_id: str, account_id: int) -> Tuple[dict, HTTPStatus]:
        """Check rate limits for a backend account via provider API."""
        from ..services.provider_usage_client import ProviderUsageClient

        backend_id = _resolve_backend_id(backend_id)
        account = get_account_with_backend(account_id)
        if not account or account.get("backend_id") != backend_id:
            return {"error": "Account not found"}, HTTPStatus.NOT_FOUND

        backend_type = account.get("backend_type", "claude")

        try:
            windows = ProviderUsageClient.fetch_usage(account, backend_type)
        except Exception as e:
            return {"error": f"Provider API error: {e}"}, HTTPStatus.BAD_GATEWAY

        if not windows:
            default_paths = {"claude": "~/.claude", "gemini": "~/.gemini"}
            config_path = account.get("config_path", default_paths.get(backend_type, ""))
            hint = f"No credentials found at {config_path}."
            if backend_type == "claude" and config_path and config_path != "~/.claude":
                hint += f" Run: CLAUDE_CONFIG_DIR={config_path} claude"
            elif backend_type == "claude":
                hint += " Run `claude` in your terminal to authenticate."
            elif backend_type == "codex":
                hint += " Run `codex login` to authenticate."
            elif backend_type == "gemini" and config_path and config_path != "~/.gemini":
                hint += f" Run: GEMINI_CLI_HOME={config_path} gemini"
            elif backend_type == "gemini":
                hint += " Run `gemini` to authenticate."
            return {
                "windows": [],
                "message": hint,
            }, HTTPStatus.OK

        return {"windows": windows}, HTTPStatus.OK

    @staticmethod
    def check_account_usage(backend_id: str, account_id: int) -> Tuple[dict, HTTPStatus]:
        """Run a one-shot usage check for a backend account."""
        from ..services.backend_cli_service import BACKEND_CLI_COMMANDS, BackendCLIService

        backend_id = _resolve_backend_id(backend_id)
        btype = get_backend_type(backend_id)
        if not btype:
            return {"error": "Backend not found"}, HTTPStatus.NOT_FOUND

        if btype not in BACKEND_CLI_COMMANDS:
            return {
                "error": f"Backend type '{btype}' does not support usage check"
            }, HTTPStatus.BAD_REQUEST

        # Verify account exists
        if not verify_account_exists(account_id, backend_id):
            return {"error": "Account not found"}, HTTPStatus.NOT_FOUND

        # Check CLI is installed
        installed, _, _ = detect_backend(btype)
        if not installed:
            return {"error": f"{btype} CLI is not installed"}, HTTPStatus.BAD_REQUEST

        result = BackendCLIService.run_usage_oneshot(btype)
        return result, HTTPStatus.OK

    @staticmethod
    def check_auth_status(backend_id: str) -> Tuple[dict, HTTPStatus]:
        """Check authentication status for a backend by probing stored credentials."""
        from ..services.provider_usage_client import CredentialResolver

        backend_id = _resolve_backend_id(backend_id)
        btype = get_backend_type(backend_id)
        if not btype:
            return {"error": "Backend not found"}, HTTPStatus.NOT_FOUND

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

        # Terminal instructions per backend type
        instructions = {
            "claude": "Run `claude` in your terminal to trigger the OAuth login flow.",
            "codex": "Run `codex login` in your terminal to authenticate.",
            "gemini": "Run `gemini` in your terminal to trigger the OAuth login flow.",
        }

        return {
            "backend_type": btype,
            "accounts": accounts,
            "login_instruction": instructions.get(btype, f"Run the {btype} CLI to authenticate."),
        }, HTTPStatus.OK

    @staticmethod
    def discover_models(backend_id: str) -> Tuple[dict, HTTPStatus]:
        """Discover available models for a backend via CLI introspection."""
        from ..services.model_discovery_service import ModelDiscoveryService

        backend_id = _resolve_backend_id(backend_id)
        btype = get_backend_type(backend_id)
        if not btype:
            return {"error": "Backend not found"}, HTTPStatus.NOT_FOUND

        models = ModelDiscoveryService.discover_models(btype)
        if models:
            update_backend_models(backend_id, models)

        return {"models": models, "backend_id": backend_id}, HTTPStatus.OK
