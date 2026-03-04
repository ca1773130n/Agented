"""AI Backends API routes."""

import subprocess
from http import HTTPStatus

from flask import Response, request
from flask_openapi3 import APIBlueprint

from ..models.backend import (
    BackendAccountPath,
    BackendPath,
    CreateAccountRequest,
    UpdateAccountRequest,
)
from ..models.backend_cli import (
    BackendConnectSessionPath,
    SessionResponseRequest,
    TestPromptRequest,
    TestStreamPath,
)
from ..services.backend_cli_service import BackendCLIService
from ..services.backend_service import BackendService

backends_bp = APIBlueprint("backends", __name__, url_prefix="/admin/backends")


# =============================================================================
# Backend CRUD Routes
# =============================================================================


@backends_bp.get("/")
def list_backends():
    """List all AI backends, auto-refreshing model lists via discovery."""
    result, status = BackendService.list_backends()
    return result, status


@backends_bp.get("/<backend_id>")
def get_backend(path: BackendPath):
    """Get a backend with its accounts."""
    result, status = BackendService.get_backend(path.backend_id)
    return result, status


@backends_bp.post("/<backend_id>/install")
def install_backend_cli(path: BackendPath):
    """Install the CLI for a backend that is not yet installed."""
    result, status = BackendService.install_backend_cli(path.backend_id)
    return result, status


@backends_bp.post("/<backend_id>/check")
def check_backend(path: BackendPath):
    """Check if a backend is installed and return capabilities."""
    result, status = BackendService.check_backend(path.backend_id)
    return result, status


@backends_bp.post("/<backend_id>/accounts")
def create_account(path: BackendPath, body: CreateAccountRequest):
    """Add an account to a backend."""
    result, status = BackendService.create_account(path.backend_id, body)
    return result, status


@backends_bp.put("/<backend_id>/accounts/<int:account_id>")
def update_account(path: BackendAccountPath, body: UpdateAccountRequest):
    """Update an account."""
    result, status = BackendService.update_account(path.backend_id, path.account_id, body)
    return result, status


@backends_bp.delete("/<backend_id>/accounts/<int:account_id>")
def delete_account(path: BackendAccountPath):
    """Delete an account."""
    result, status = BackendService.delete_account(path.backend_id, path.account_id)
    return result, status


# =============================================================================
# Backend CLI Connect Routes (OAuth login + usage)
# =============================================================================


@backends_bp.post("/<backend_id>/connect")
def start_connect(path: BackendPath):
    """Start an OAuth login session for a backend CLI."""
    body = request.get_json(silent=True) or {}
    config_path = body.get("config_path")
    result, status = BackendService.start_connect(path.backend_id, config_path=config_path)
    return result, status


@backends_bp.get("/<backend_id>/connect/<session_id>/stream")
def stream_connect(path: BackendConnectSessionPath):
    """SSE endpoint for real-time CLI login streaming."""
    status = BackendCLIService.get_status(path.session_id)
    if not status:
        return {"error": "Session not found"}, HTTPStatus.NOT_FOUND

    def generate():
        """Yield SSE events from the backend CLI session subscription."""
        for event in BackendCLIService.subscribe(path.session_id):
            yield event

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@backends_bp.post("/<backend_id>/connect/<session_id>/respond")
def respond_connect(path: BackendConnectSessionPath, body: SessionResponseRequest):
    """Submit a user response to an interactive CLI session."""
    status = BackendCLIService.get_status(path.session_id)
    if not status:
        return {"error": "Session not found"}, HTTPStatus.NOT_FOUND

    success = BackendCLIService.submit_response(
        session_id=path.session_id,
        interaction_id=body.interaction_id,
        response=body.response,
    )

    if not success:
        return {"error": "No pending interaction found"}, HTTPStatus.NOT_FOUND

    return {"status": "ok"}, HTTPStatus.OK


@backends_bp.delete("/<backend_id>/connect/<session_id>")
def cancel_connect(path: BackendConnectSessionPath):
    """Cancel a running CLI login session."""
    status = BackendCLIService.get_status(path.session_id)
    if not status:
        return {"error": "Session not found"}, HTTPStatus.NOT_FOUND

    BackendCLIService.cancel_session(path.session_id)
    return {"message": "Session cancelled"}, HTTPStatus.OK


@backends_bp.post("/<backend_id>/accounts/<int:account_id>/rate-limits")
def check_rate_limits(path: BackendAccountPath):
    """Check rate limits for a backend account via provider API."""
    result, status = BackendService.check_rate_limits(path.backend_id, path.account_id)
    return result, status


@backends_bp.post("/<backend_id>/accounts/<int:account_id>/usage")
def check_account_usage(path: BackendAccountPath):
    """Run a one-shot usage check for a backend account."""
    result, status = BackendService.check_account_usage(path.backend_id, path.account_id)
    return result, status


@backends_bp.get("/<backend_id>/auth-status")
def check_auth_status(path: BackendPath):
    """Check authentication status for a backend by probing stored credentials."""
    result, status = BackendService.check_auth_status(path.backend_id)
    return result, status


# =============================================================================
# Backend Test Routes (One-shot prompt testing with SSE streaming)
# =============================================================================


@backends_bp.post("/test")
def test_backend_prompt(body: TestPromptRequest):
    """Start a one-shot prompt test against a backend CLI."""
    from ..services.backend_test_service import BackendTestService

    result, status = BackendTestService.test_prompt(
        backend_type=body.backend_type,
        prompt=body.prompt,
        account_id=body.account_id,
        model=body.model,
    )
    return result, status


@backends_bp.get("/test/<test_id>/stream")
def stream_backend_test(path: TestStreamPath):
    """SSE endpoint for real-time backend test output streaming."""
    from ..services.backend_test_service import BackendTestService

    def generate():
        """Yield SSE events from the backend test subscription."""
        for event in BackendTestService.subscribe_test(path.test_id):
            yield event

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@backends_bp.post("/proxy/login")
def start_proxy_login():
    """Start CLIProxyAPI ``--claude-login`` for OAuth account addition.

    A fake ``open`` command intercepts the browser call, captures the OAuth
    URL, and keeps the fake "browser" alive so cliproxyapi maintains its
    callback HTTP server.  The captured URL is returned to the frontend
    which opens it in the user's browser.
    """
    import threading

    from ..services.cliproxy_manager import CLIProxyManager

    body = request.get_json(silent=True) or {}
    proxy_config_dir = body.get("config_path")
    proxy_backend_type = body.get("backend_type", "claude")

    try:
        proc, auth_info = CLIProxyManager.start_login(
            backend_type=proxy_backend_type,
            config_dir=proxy_config_dir,
        )
    except FileNotFoundError:
        return {
            "status": "error",
            "message": "cliproxyapi binary not found",
        }, HTTPStatus.NOT_FOUND
    except Exception as exc:
        return {
            "status": "error",
            "message": str(exc),
        }, HTTPStatus.INTERNAL_SERVER_ERROR

    auth_url = auth_info.get("url")
    if not auth_url:
        try:
            proc.kill()
        except Exception:
            pass
        return {
            "status": "error",
            "message": "Failed to capture auth URL from cliproxyapi",
        }, HTTPStatus.INTERNAL_SERVER_ERROR

    # Keep the process alive in background — it's listening for the OAuth
    # callback on its local port (claude) or polling device auth (codex).
    def _wait_bg():
        try:
            proc.wait(timeout=300)
        except subprocess.TimeoutExpired:
            proc.kill()
        except Exception:
            pass

    threading.Thread(target=_wait_bg, daemon=True).start()
    result = {
        "status": "started",
        "message": "Complete login in the browser",
        "oauth_url": auth_url,
    }
    if auth_info.get("device_code"):
        result["device_code"] = auth_info["device_code"]
    if auth_info.get("output"):
        result["output"] = auth_info["output"]
    return result, HTTPStatus.OK


@backends_bp.post("/proxy/callback-forward")
def proxy_callback_forward():
    """Forward an OAuth callback URL to cliproxyapi's local server.

    When the user is remote, the OAuth redirect to localhost fails in their
    browser.  They paste the failed URL here and we forward it to cliproxyapi
    on the server where it's actually listening.
    """
    from urllib.parse import parse_qs, urlparse

    import httpx

    body = request.get_json(silent=True) or {}
    callback_url = body.get("callback_url", "")
    if not callback_url:
        return {"error": "callback_url is required"}, HTTPStatus.BAD_REQUEST

    # Parse code and state from the callback URL
    parsed = urlparse(callback_url)
    qs = parse_qs(parsed.query)
    code = qs.get("code", [""])[0]
    state = qs.get("state", [""])[0]
    port = parsed.port or 54545

    if not code:
        return {"error": "No 'code' parameter found in URL"}, HTTPStatus.BAD_REQUEST

    # Forward to cliproxyapi's local callback server on the server
    try:
        resp = httpx.get(
            f"http://127.0.0.1:{port}{parsed.path}",
            params={"code": code, "state": state},
            timeout=15,
            follow_redirects=True,
        )
        if resp.status_code < 400:
            return {"status": "completed", "message": "Callback forwarded successfully"}, HTTPStatus.OK
        return {
            "status": "error",
            "message": f"Callback server returned {resp.status_code}",
        }, HTTPStatus.BAD_GATEWAY
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to reach callback server: {exc}",
        }, HTTPStatus.BAD_GATEWAY


@backends_bp.get("/proxy/status")
def proxy_status():
    """Check CLIProxyAPI availability and account count."""
    from ..services.cliproxy_manager import CLIProxyManager

    healthy = CLIProxyManager.is_healthy()
    accounts = CLIProxyManager.list_accounts() if healthy else []
    return {
        "available": healthy,
        "account_count": len(accounts),
        "accounts": accounts,
    }, HTTPStatus.OK


@backends_bp.get("/proxy/accounts")
def list_proxy_accounts():
    """List CLIProxyAPI credential accounts from ~/.cli-proxy-api/."""
    from ..services.cliproxy_manager import CLIProxyManager

    accounts = CLIProxyManager.list_accounts()
    return {"accounts": accounts}, HTTPStatus.OK


@backends_bp.post("/<backend_id>/discover-models")
def discover_models(path: BackendPath):
    """Discover available models for a backend via CLI introspection."""
    result, status = BackendService.discover_models(path.backend_id)
    return result, status
