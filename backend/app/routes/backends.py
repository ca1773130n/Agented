"""AI Backends API routes."""

import logging
import subprocess
from http import HTTPStatus

logger = logging.getLogger(__name__)

from flask import Response, request
from flask_openapi3 import APIBlueprint

from app.models.common import error_response

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
from ..models.common import PaginationQuery
from ..services.backend_cli_service import BackendCLIService
from ..services.backend_service import BackendService

backends_bp = APIBlueprint("backends", __name__, url_prefix="/admin/backends")


# =============================================================================
# Backend CRUD Routes
# =============================================================================


@backends_bp.get("/")
def list_backends(query: PaginationQuery):
    """List all AI backends, auto-refreshing model lists via discovery."""
    result, status = BackendService.list_backends(limit=query.limit, offset=query.offset or 0)
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
    user_email = body.get("email")
    account_name = body.get("account_name")
    result, status = BackendService.start_connect(
        path.backend_id,
        config_path=config_path,
        email=user_email,
        account_name=account_name,
    )
    return result, status


@backends_bp.get("/<backend_id>/connect/<session_id>/stream")
def stream_connect(path: BackendConnectSessionPath):
    """SSE endpoint for real-time CLI login streaming."""
    status = BackendCLIService.get_status(path.session_id)
    if not status:
        return error_response("NOT_FOUND", "Session not found", HTTPStatus.NOT_FOUND)

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
        return error_response("NOT_FOUND", "Session not found", HTTPStatus.NOT_FOUND)

    success = BackendCLIService.submit_response(
        session_id=path.session_id,
        interaction_id=body.interaction_id,
        response=body.response,
    )

    if not success:
        return error_response("NOT_FOUND", "No pending interaction found", HTTPStatus.NOT_FOUND)

    return {"status": "ok"}, HTTPStatus.OK


@backends_bp.delete("/<backend_id>/connect/<session_id>")
def cancel_connect(path: BackendConnectSessionPath):
    """Cancel a running CLI login session."""
    status = BackendCLIService.get_status(path.session_id)
    if not status:
        return error_response("NOT_FOUND", "Session not found", HTTPStatus.NOT_FOUND)

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
    except ValueError as exc:
        return {
            "status": "unsupported",
            "message": str(exc),
        }, HTTPStatus.OK
    except Exception as exc:
        logger.warning("Proxy login failed: %s", exc, exc_info=True)
        return {
            "status": "skipped",
            "message": f"Proxy login unavailable: {exc}",
        }, HTTPStatus.OK

    # Token import (Gemini) — creds written directly, no OAuth needed
    if auth_info.get("imported"):
        try:
            proc.kill()
        except Exception:
            pass
        return {
            "status": "ok",
            "message": f"Imported credentials for {auth_info.get('email', 'account')} into API proxy",
        }, HTTPStatus.OK

    auth_url = auth_info.get("url")
    if not auth_url:
        try:
            proc.kill()
        except Exception:
            logger.debug("Failed to kill cliproxy process during cleanup", exc_info=True)
        return {
            "status": "skipped",
            "message": "Proxy login: could not capture auth URL (account may already be authenticated)",
        }, HTTPStatus.OK

    # Keep the process alive in background — it's listening for the OAuth
    # callback on its local port (claude) or polling device auth (codex).
    def _wait_bg():
        try:
            proc.wait(timeout=300)
        except subprocess.TimeoutExpired:
            proc.kill()
        except Exception:
            logger.debug("Background cliproxy wait failed", exc_info=True)

    threading.Thread(target=_wait_bg, daemon=True).start()

    # Store the callback port from the redirect_uri so the callback-forward
    # endpoint knows where to proxy (for remote deployments).
    if auth_url:
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(auth_url).query)
        redirect_uri = qs.get("redirect_uri", [""])[0]
        if redirect_uri and "localhost" in redirect_uri:
            callback_port = urlparse(redirect_uri).port or 8085
            from ..services.backend_cli_service import BackendCLIService

            BackendCLIService.set_callback_port(callback_port)

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
        return error_response("BAD_REQUEST", "callback_url is required", HTTPStatus.BAD_REQUEST)

    # Parse code and state from the callback URL
    parsed = urlparse(callback_url)
    qs = parse_qs(parsed.query)
    code = qs.get("code", [""])[0]
    state = qs.get("state", [""])[0]
    port = parsed.port or 54545

    if not code:
        return error_response(
            "BAD_REQUEST", "No 'code' parameter found in URL", HTTPStatus.BAD_REQUEST
        )

    # Forward to the local callback server. Try IPv6 first (Claude CLI binds
    # to ::1 on newer versions), then fall back to IPv4.
    last_exc = None
    for host in ("[::1]", "127.0.0.1", "localhost"):
        try:
            resp = httpx.get(
                f"http://{host}:{port}{parsed.path}",
                params={"code": code, "state": state},
                timeout=15,
                follow_redirects=True,
            )
            if resp.status_code < 400:
                return {
                    "status": "completed",
                    "message": "Callback forwarded successfully",
                }, HTTPStatus.OK
            return {
                "status": "error",
                "message": f"Callback server returned {resp.status_code}",
            }, HTTPStatus.BAD_GATEWAY
        except Exception as exc:
            last_exc = exc
            logger.debug("Callback forward to %s:%d failed: %s", host, port, exc)
            continue
    return {
        "status": "error",
        "message": f"Failed to reach callback server: {last_exc}",
    }, HTTPStatus.BAD_GATEWAY


@backends_bp.post("/gemini/auth-start")
def gemini_auth_start():
    """Start a Google OAuth PKCE flow for Gemini CLI + CLIProxyAPI.

    Returns the OAuth URL and stores the code_verifier for token exchange.
    This bypasses the Gemini CLI's broken TUI auth.
    """
    import base64
    import hashlib
    import secrets

    body = request.get_json(silent=True) or {}
    config_path = body.get("config_path")
    email = body.get("email", "")

    # Generate PKCE code_verifier + code_challenge
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    state = secrets.token_hex(32)

    # Store for later exchange
    from ..services.backend_cli_service import BackendCLIService

    with BackendCLIService._lock:
        if not hasattr(BackendCLIService, "_gemini_auth_pending"):
            BackendCLIService._gemini_auth_pending = {}
        BackendCLIService._gemini_auth_pending[state] = {
            "code_verifier": code_verifier,
            "config_path": config_path,
            "email": email,
        }

    client_id = "681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com"
    scopes = "https://www.googleapis.com/auth/cloud-platform https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile"

    from urllib.parse import urlencode

    oauth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
        {
            "client_id": client_id,
            "redirect_uri": "https://codeassist.google.com/authcode",
            "response_type": "code",
            "scope": scopes,
            "access_type": "offline",
            "code_challenge_method": "S256",
            "code_challenge": code_challenge,
            "state": state,
            # select_account: force Google to show account picker (even if signed in)
            # consent: force consent screen (ensures refresh_token is returned)
            "prompt": "select_account consent",
        }
    )

    return {
        "status": "started",
        "oauth_url": oauth_url,
        "state": state,
    }, HTTPStatus.OK


@backends_bp.post("/gemini/auth-complete")
def gemini_auth_complete():
    """Exchange the Google OAuth code for tokens and save to Gemini CLI + CLIProxyAPI."""
    import json as _json

    import httpx

    body = request.get_json(silent=True) or {}
    auth_code = body.get("code", "").strip()
    state = body.get("state", "")

    if not auth_code:
        return error_response(
            "BAD_REQUEST", "Authorization code is required", HTTPStatus.BAD_REQUEST
        )

    # Retrieve stored PKCE verifier
    from ..services.backend_cli_service import BackendCLIService

    # Peek at pending state (don't pop yet — keep it for retries on failure)
    with BackendCLIService._lock:
        pending = getattr(BackendCLIService, "_gemini_auth_pending", {}).get(state)

    if not pending:
        return error_response("BAD_REQUEST", "Invalid or expired state", HTTPStatus.BAD_REQUEST)

    code_verifier = pending["code_verifier"]
    config_path = pending.get("config_path")
    email = pending.get("email", "")

    # Gemini CLI OAuth client credentials.
    # This client_id is registered as a web app; Google requires client_secret
    # even with PKCE. The secret is publicly embedded in Gemini CLI itself.
    client_id = "681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com"
    client_secret = "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"

    try:
        resp = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": auth_code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": "https://codeassist.google.com/authcode",
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
            timeout=15,
        )
        if resp.status_code != 200:
            err_data = (
                resp.json()
                if resp.headers.get("content-type", "").startswith("application/json")
                else {}
            )
            err_msg = err_data.get("error_description", err_data.get("error", resp.text[:200]))
            return error_response(
                "BAD_REQUEST", f"Token exchange failed: {err_msg}", HTTPStatus.BAD_REQUEST
            )
        tokens = resp.json()
    except Exception as exc:
        return error_response(
            "INTERNAL_SERVER_ERROR",
            f"Token exchange error: {exc}",
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    # Success — remove pending state so it can't be reused
    with BackendCLIService._lock:
        getattr(BackendCLIService, "_gemini_auth_pending", {}).pop(state, None)

    # Save to Gemini CLI config
    import os
    from pathlib import Path

    if config_path:
        gemini_dir = Path(os.path.expanduser(config_path)) / ".gemini"
    else:
        gemini_dir = Path.home() / ".gemini"
    gemini_dir.mkdir(parents=True, exist_ok=True)

    creds_file = gemini_dir / "oauth_creds.json"
    creds_file.write_text(
        _json.dumps(
            {
                "access_token": tokens.get("access_token", ""),
                "refresh_token": tokens.get("refresh_token", ""),
                "scope": tokens.get("scope", ""),
                "token_type": tokens.get("token_type", "Bearer"),
                "id_token": tokens.get("id_token", ""),
                "expiry_date": int(__import__("time").time() * 1000)
                + tokens.get("expires_in", 3599) * 1000,
            },
            indent=2,
        )
    )
    logger.info("Gemini CLI creds saved to %s", creds_file)

    # Save to CLIProxyAPI
    proxy_dir = Path.home() / ".cli-proxy-api"
    if proxy_dir.exists():
        # Read client_secret from existing proxy cred if available
        client_secret = ""
        for f in proxy_dir.glob("gemini-*.json"):
            try:
                existing = _json.loads(f.read_text())
                cs = existing.get("token", {}).get("client_secret")
                if cs:
                    client_secret = cs
                    break
            except Exception:
                pass

        proxy_cred = proxy_dir / f"gemini-{email or 'default'}.json"
        proxy_cred.write_text(
            _json.dumps(
                {
                    "auto": False,
                    "checked": True,
                    "email": email,
                    "project_id": "",
                    "type": "gemini",
                    "token": {
                        "access_token": tokens.get("access_token", ""),
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "expires_in": tokens.get("expires_in", 3599),
                        "expiry": "",
                        "refresh_token": tokens.get("refresh_token", ""),
                        "scopes": tokens.get("scope", "").split(" "),
                        "token_type": "Bearer",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "universe_domain": "googleapis.com",
                    },
                },
                indent=2,
            )
        )
        logger.info("CLIProxyAPI Gemini creds saved to %s", proxy_cred)

    return {
        "status": "ok",
        "message": f"Signed in with Google and registered with API proxy",
    }, HTTPStatus.OK


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
