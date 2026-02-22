"""AI Backends API routes."""

from http import HTTPStatus

from flask import Response
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
    result, status = BackendService.start_connect(path.backend_id)
    return result, status


@backends_bp.get("/<backend_id>/connect/<session_id>/stream")
def stream_connect(path: BackendConnectSessionPath):
    """SSE endpoint for real-time CLI login streaming."""
    status = BackendCLIService.get_status(path.session_id)
    if not status:
        return {"error": "Session not found"}, HTTPStatus.NOT_FOUND

    def generate():
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
    """Start CLIProxyAPI ``--claude-login`` for interactive OAuth account addition."""
    from ..services.cliproxy_manager import CLIProxyManager

    try:
        proc = CLIProxyManager.start_login()
        # Wait for process to finish (login is interactive via browser)
        stdout, stderr = proc.communicate(timeout=120)
        if proc.returncode == 0:
            return {
                "status": "completed",
                "message": "Login completed successfully",
                "output": stdout.strip() if stdout else "",
            }, HTTPStatus.OK
        else:
            return {
                "status": "failed",
                "message": "Login failed",
                "error": stderr.strip() if stderr else "Unknown error",
            }, HTTPStatus.INTERNAL_SERVER_ERROR
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
