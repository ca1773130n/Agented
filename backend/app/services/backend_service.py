"""Backend management service."""

import logging
from dataclasses import asdict
from http import HTTPStatus
from typing import Optional, Tuple

from app.models.common import error_response

from ..db.backends import (
    check_and_update_backend_installed,
    get_account_with_backend,
    get_backend_accounts_for_auth,
    get_backend_by_id,
    get_backend_type,
    update_backend_models,
    verify_account_exists,
)
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
        backend_id: str,
        config_path: Optional[str] = None,
        email: Optional[str] = None,
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
