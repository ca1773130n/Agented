"""Wave 73 — leaf CRUD batch H (~21 routes).

utility leftover + backends CRUD (sans SSE).

Streaming endpoints (`/connect/{session}/stream`, `/test/{id}/stream`) stay
on Flask until the dedicated streaming wave so we lift the Litestar
`Stream` pattern across all backend streams in one pass.
"""

from __future__ import annotations

import base64
import hashlib
import json as _json
import logging
import os
import secrets
import subprocess
import threading
from http import HTTPStatus
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from litestar import Router, delete, get, post
from litestar.exceptions import (
    ClientException,
    HTTPException,
    NotFoundException,
)

from app.config import PROJECT_ROOT
from app.database import get_paths_for_trigger, get_trigger
from app.services.audit_log_service import AuditLogService
from app.services.backend_cli_service import BackendCLIService
from app.services.backend_service import BackendService
from app.services.execution_service import ExecutionService
from app.services.github_service import GitHubService
from app.services.skill_discovery_service import SkillDiscoveryService
from app_litestar.auth_guards import requires_role
from app_litestar.rate_limit_guard import requires_rate_limit

logger = logging.getLogger(__name__)


def _result_or_raise(payload: tuple[Any, int]) -> Any:
    body, status = payload
    if status >= 400:
        msg = body.get("error") if isinstance(body, dict) else body
        if status == 404:
            raise NotFoundException(detail=str(msg))
        raise HTTPException(status_code=status, detail=str(msg))
    return body


# ===========================================================================
# /api/* utility leftover (5)
# ===========================================================================


@get("/validate-github-url", sync_to_thread=False)
def validate_github_url(url: str = "") -> dict[str, Any]:
    if not url:
        raise ClientException(detail="url parameter required")
    valid = GitHubService.validate_repo_url(url)
    owner = repo = None
    try:
        owner, repo = GitHubService.parse_repo_url(url)
    except ValueError:
        pass
    return {"url": url, "valid": valid, "owner": owner, "repo": repo}


@post("/resolve-issues", status_code=202, sync_to_thread=False)
def resolve_issues(data: dict) -> dict[str, Any]:
    if not data:
        raise ClientException(detail="JSON body required")
    audit_summary = data.get("audit_summary", "")
    project_paths = data.get("project_paths", [])
    if not audit_summary:
        raise ClientException(detail="audit_summary required")
    if not project_paths:
        raise ClientException(detail="project_paths required")
    threading.Thread(
        target=ExecutionService.run_resolve_command,
        args=(audit_summary, project_paths),
        daemon=True,
    ).start()
    return {
        "message": "Resolution started",
        "status": "running",
        "project_count": len(project_paths),
    }


_ALLOWED_BASES = [Path.home(), Path("/tmp"), Path("/opt")]


def _is_path_allowed(resolved: Path) -> bool:
    resolved_str = str(resolved)
    return any(
        resolved_str == str(base) or resolved_str.startswith(str(base) + os.sep)
        for base in _ALLOWED_BASES
    )


@get("/discover-skills", sync_to_thread=False)
def discover_skills(trigger_id: str = "", paths: str = "") -> dict[str, Any]:
    scan_paths: list[str] = []
    if trigger_id:
        if not get_trigger(trigger_id):
            raise NotFoundException(detail="Trigger not found")
        scan_paths = get_paths_for_trigger(trigger_id)
    elif paths:
        # 07.L3 — validate each client-supplied scan path through the same
        # allowlist gate browse_directory uses; reject arbitrary host paths.
        for raw in (p.strip() for p in paths.split(",") if p.strip()):
            try:
                resolved = Path(raw).expanduser().resolve()
            except (OSError, ValueError) as e:
                raise ClientException(detail="Invalid path") from e
            if not _is_path_allowed(resolved):
                raise HTTPException(
                    status_code=403,
                    detail="Path must be under home directory, /tmp, or /opt",
                )
            scan_paths.append(str(resolved))
    if PROJECT_ROOT not in scan_paths:
        scan_paths.append(PROJECT_ROOT)
    return {"skills": SkillDiscoveryService.discover_cli_skills(scan_paths)}


@get(
    "/browse-directory",
    sync_to_thread=False,
    guards=[requires_role("admin")],  # 07.L2 — filesystem browse is admin-only
)
def browse_directory(path: Optional[str] = None) -> dict[str, Any]:
    raw_path = path or str(Path.home())
    try:
        resolved = Path(raw_path).resolve()
    except (OSError, ValueError) as e:
        raise ClientException(detail="Invalid path") from e
    if not _is_path_allowed(resolved):
        raise HTTPException(
            status_code=403,
            detail="Path must be under home directory, /tmp, or /opt",
        )
    if not resolved.is_dir():
        raise NotFoundException(detail="Directory does not exist")

    # 07.L2 — audit filesystem browse access.
    AuditLogService.log(
        action="filesystem.browse",
        entity_type="directory",
        entity_id=str(resolved),
        outcome="read",
    )

    parent = resolved.parent
    parent_path = str(parent) if _is_path_allowed(parent) else None
    entries: list[dict[str, Any]] = []
    try:
        for entry in sorted(resolved.iterdir(), key=lambda e: e.name.lower()):
            try:
                entry_resolved = entry.resolve()
            except (OSError, ValueError):
                continue
            if not entry_resolved.is_dir():
                continue
            if entry.name.startswith("."):
                continue
            if entry.is_symlink() and not _is_path_allowed(entry_resolved):
                continue
            if not os.access(entry_resolved, os.R_OK):
                continue
            entries.append({"name": entry.name, "path": str(entry_resolved), "type": "directory"})
    except PermissionError as e:
        raise HTTPException(status_code=403, detail="Cannot read directory contents") from e
    return {"current_path": str(resolved), "parent_path": parent_path, "entries": entries}


@post(
    "/create-directory",
    status_code=201,
    sync_to_thread=False,
    guards=[requires_role("admin")],  # 07.L2 — filesystem mkdir is admin-only
)
def create_directory(data: dict) -> dict[str, Any]:
    if not data or not data.get("path"):
        raise ClientException(detail="path is required in JSON body")
    path_obj = Path(data["path"]).expanduser()
    if not path_obj.is_absolute():
        raise ClientException(detail="Path must be absolute")
    try:
        resolved = path_obj.resolve()
    except (OSError, ValueError) as e:
        raise ClientException(detail="Invalid path") from e
    if not _is_path_allowed(resolved):
        raise HTTPException(
            status_code=403,
            detail="Path must be under home directory, /tmp, or /opt",
        )
    try:
        resolved.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        raise HTTPException(
            status_code=403, detail="Permission denied when creating directory"
        ) from e
    except OSError as exc:
        raise ClientException(detail=f"Cannot create directory: {exc}") from exc
    # 07.L2 — audit filesystem mkdir.
    AuditLogService.log(
        action="filesystem.create_directory",
        entity_type="directory",
        entity_id=str(resolved),
        outcome="created",
    )
    return {"created": True, "path": str(resolved)}


utility_leftover_router = Router(
    path="/api",
    route_handlers=[
        validate_github_url,
        resolve_issues,
        discover_skills,
        browse_directory,
        create_directory,
    ],
)


# ===========================================================================
# /admin/backends/* CRUD (16; 2 SSE streams stay on Flask)
# ===========================================================================


@post(
    "/{backend_id:str}/install",
    sync_to_thread=False,
    guards=[requires_role("admin"), requires_rate_limit(10, 3600.0)],
)
def install_backend_cli(backend_id: str) -> Any:
    return _result_or_raise(BackendService.install_backend_cli(backend_id))


@post("/{backend_id:str}/check", sync_to_thread=False)
def check_backend(backend_id: str) -> Any:
    return _result_or_raise(BackendService.check_backend(backend_id))


@post("/{backend_id:str}/connect", sync_to_thread=False)
def start_connect(backend_id: str, data: dict) -> Any:
    body = data or {}
    return _result_or_raise(
        BackendService.start_connect(
            backend_id,
            config_path=body.get("config_path"),
            email=body.get("email"),
            account_name=body.get("account_name"),
        )
    )


@post(
    "/{backend_id:str}/connect/{session_id:str}/respond",
    sync_to_thread=False,
)
def respond_connect(backend_id: str, session_id: str, data: dict) -> dict[str, Any]:
    del backend_id
    if not BackendCLIService.get_status(session_id):
        raise NotFoundException(detail="Session not found")
    body = data or {}
    if not BackendCLIService.submit_response(
        session_id=session_id,
        interaction_id=body.get("interaction_id"),
        response=body.get("response", ""),
    ):
        raise NotFoundException(detail="No pending interaction found")
    return {"status": "ok"}


@delete(
    "/{backend_id:str}/connect/{session_id:str}",
    status_code=200,
    sync_to_thread=False,
)
def cancel_connect(backend_id: str, session_id: str) -> dict[str, Any]:
    del backend_id
    if not BackendCLIService.get_status(session_id):
        raise NotFoundException(detail="Session not found")
    BackendCLIService.cancel_session(session_id)
    return {"message": "Session cancelled"}


@post(
    "/{backend_id:str}/accounts/{account_id:int}/rate-limits",
    sync_to_thread=False,
)
def check_rate_limits(backend_id: str, account_id: int) -> Any:
    return _result_or_raise(BackendService.check_rate_limits(backend_id, account_id))


@post(
    "/{backend_id:str}/accounts/{account_id:int}/usage",
    sync_to_thread=False,
)
def check_account_usage(backend_id: str, account_id: int) -> Any:
    return _result_or_raise(BackendService.check_account_usage(backend_id, account_id))


@get("/{backend_id:str}/auth-status", sync_to_thread=False)
def check_auth_status(backend_id: str) -> Any:
    return _result_or_raise(BackendService.check_auth_status(backend_id))


@post("/test", sync_to_thread=False)
def test_backend_prompt(data: dict) -> Any:
    from app.services.backend_test_service import BackendTestService

    body = data or {}
    return _result_or_raise(
        BackendTestService.test_prompt(
            backend_type=body.get("backend_type"),
            prompt=body.get("prompt", ""),
            account_id=body.get("account_id"),
            model=body.get("model"),
        )
    )


@post("/proxy/login", sync_to_thread=False)
def start_proxy_login(data: dict) -> dict[str, Any]:
    from app.services.cliproxy_manager import CLIProxyManager

    body = data or {}
    proxy_config_dir = body.get("config_path")
    proxy_backend_type = body.get("backend_type", "claude")
    try:
        proc, auth_info = CLIProxyManager.start_login(
            backend_type=proxy_backend_type,
            config_dir=proxy_config_dir,
        )
    except FileNotFoundError as e:
        raise NotFoundException(detail="cliproxyapi binary not found") from e
    except ValueError as exc:
        return {"status": "unsupported", "message": str(exc)}
    except Exception as exc:
        logger.warning("Proxy login failed: %s", exc, exc_info=True)
        return {"status": "skipped", "message": f"Proxy login unavailable: {exc}"}

    if auth_info.get("imported"):
        try:
            proc.kill()
        except Exception:
            pass
        return {
            "status": "ok",
            "message": (
                f"Imported credentials for {auth_info.get('email', 'account')} into API proxy"
            ),
        }

    auth_url = auth_info.get("url")
    if not auth_url:
        try:
            proc.kill()
        except Exception:
            logger.debug("Failed to kill cliproxy process during cleanup", exc_info=True)
        return {
            "status": "skipped",
            "message": (
                "Proxy login: could not capture auth URL (account may already be authenticated)"
            ),
        }

    def _wait_bg() -> None:
        try:
            proc.wait(timeout=300)
        except subprocess.TimeoutExpired:
            proc.kill()
        except Exception:
            logger.debug("Background cliproxy wait failed", exc_info=True)

    threading.Thread(target=_wait_bg, daemon=True).start()

    if auth_url:
        qs = parse_qs(urlparse(auth_url).query)
        redirect_uri = qs.get("redirect_uri", [""])[0]
        if redirect_uri and "localhost" in redirect_uri:
            callback_port = urlparse(redirect_uri).port or 8085
            BackendCLIService.set_callback_port(callback_port)

    result: dict[str, Any] = {
        "status": "started",
        "message": "Complete login in the browser",
        "oauth_url": auth_url,
    }
    if auth_info.get("device_code"):
        result["device_code"] = auth_info["device_code"]
    if auth_info.get("output"):
        result["output"] = auth_info["output"]
    return result


@post("/proxy/callback-forward", sync_to_thread=False)
def proxy_callback_forward(data: dict) -> dict[str, Any]:
    body = data or {}
    callback_url = body.get("callback_url", "")
    if not callback_url:
        raise ClientException(detail="callback_url is required")

    parsed = urlparse(callback_url)
    qs = parse_qs(parsed.query)
    code = qs.get("code", [""])[0]
    state = qs.get("state", [""])[0]
    # SSRF hardening (H5): never trust the URL's port/path. The port is pinned to
    # the value captured when the proxy login started; the path is constrained to
    # the known OAuth callback path. Otherwise this becomes a loopback
    # port-scanner / request-forger against any local service (e.g. the sidecar).
    port = BackendCLIService.get_callback_port()
    _ALLOWED_CALLBACK_PATHS = ("/callback", "/oauth/callback", "/")
    path = parsed.path if parsed.path in _ALLOWED_CALLBACK_PATHS else "/callback"

    if not code:
        raise ClientException(detail="No 'code' parameter found in URL")

    last_exc: Optional[Exception] = None
    for host in ("[::1]", "127.0.0.1", "localhost"):
        try:
            resp = httpx.get(
                f"http://{host}:{port}{path}",
                params={"code": code, "state": state},
                timeout=15,
                follow_redirects=False,
            )
            if resp.status_code < 400:
                return {"status": "completed", "message": "Callback forwarded successfully"}
            raise HTTPException(
                status_code=HTTPStatus.BAD_GATEWAY,
                detail=f"Callback server returned {resp.status_code}",
            )
        except HTTPException:
            raise
        except Exception as exc:
            last_exc = exc
            logger.debug("Callback forward to %s:%d failed: %s", host, port, exc)
            continue
    raise HTTPException(
        status_code=HTTPStatus.BAD_GATEWAY,
        detail=f"Failed to reach callback server: {last_exc}",
    )


@post("/gemini/auth-start", sync_to_thread=False)
def gemini_auth_start(data: dict) -> dict[str, Any]:
    body = data or {}
    config_path = body.get("config_path")
    email = body.get("email", "")

    code_verifier = secrets.token_urlsafe(64)
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    state = secrets.token_hex(32)

    with BackendCLIService._lock:
        if not hasattr(BackendCLIService, "_gemini_auth_pending"):
            BackendCLIService._gemini_auth_pending = {}
        BackendCLIService._gemini_auth_pending[state] = {
            "code_verifier": code_verifier,
            "config_path": config_path,
            "email": email,
        }

    client_id = "681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com"
    scopes = (
        "https://www.googleapis.com/auth/cloud-platform "
        "https://www.googleapis.com/auth/userinfo.email "
        "https://www.googleapis.com/auth/userinfo.profile"
    )
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
            "prompt": "select_account consent",
        }
    )
    return {"status": "started", "oauth_url": oauth_url, "state": state}


@post("/gemini/auth-complete", sync_to_thread=False)
def gemini_auth_complete(data: dict) -> dict[str, Any]:
    body = data or {}
    auth_code = (body.get("code") or "").strip()
    state = body.get("state", "")

    if not auth_code:
        raise ClientException(detail="Authorization code is required")

    with BackendCLIService._lock:
        pending = getattr(BackendCLIService, "_gemini_auth_pending", {}).get(state)

    if not pending:
        raise ClientException(detail="Invalid or expired state")

    code_verifier = pending["code_verifier"]
    config_path = pending.get("config_path")
    email = pending.get("email", "")

    # Gemini CLI's published installed-app OAuth credentials (PKCE-protected,
    # not a confidential secret). Single source of truth lives in
    # provider_usage_client; overridable via AGENTED_GEMINI_CLIENT_* env.
    from app.services.provider_usage_client import (
        GEMINI_CLI_CLIENT_ID as client_id,
    )
    from app.services.provider_usage_client import (
        GEMINI_CLI_CLIENT_SECRET as client_secret,
    )

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
            raise ClientException(detail=f"Token exchange failed: {err_msg}")
        tokens = resp.json()
    except ClientException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Token exchange error: {exc}") from exc

    with BackendCLIService._lock:
        getattr(BackendCLIService, "_gemini_auth_pending", {}).pop(state, None)

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

    proxy_dir = Path.home() / ".cli-proxy-api"
    if proxy_dir.exists():
        proxy_client_secret = ""
        for f in proxy_dir.glob("gemini-*.json"):
            try:
                existing = _json.loads(f.read_text())
                cs = existing.get("token", {}).get("client_secret")
                if cs:
                    proxy_client_secret = cs
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
                        "client_secret": proxy_client_secret,
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

    return {"status": "ok", "message": "Signed in with Google and registered with API proxy"}


@get("/proxy/status", sync_to_thread=False)
def proxy_status() -> dict[str, Any]:
    from app.services.cliproxy_manager import CLIProxyManager

    healthy = CLIProxyManager.is_healthy()
    accounts = CLIProxyManager.list_accounts() if healthy else []
    return {"available": healthy, "account_count": len(accounts), "accounts": accounts}


@get("/proxy/accounts", sync_to_thread=False)
def list_proxy_accounts() -> dict[str, Any]:
    from app.services.cliproxy_manager import CLIProxyManager

    return {"accounts": CLIProxyManager.list_accounts()}


@post("/{backend_id:str}/discover-models", sync_to_thread=False)
def discover_models(backend_id: str) -> Any:
    return _result_or_raise(BackendService.discover_models(backend_id))


backends_router = Router(
    path="/admin/backends",
    route_handlers=[
        install_backend_cli,
        check_backend,
        start_connect,
        respond_connect,
        cancel_connect,
        check_rate_limits,
        check_account_usage,
        check_auth_status,
        test_backend_prompt,
        start_proxy_login,
        proxy_callback_forward,
        gemini_auth_start,
        gemini_auth_complete,
        proxy_status,
        list_proxy_accounts,
        discover_models,
    ],
)
