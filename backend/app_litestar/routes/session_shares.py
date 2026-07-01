"""Session live-share + co-drive routes (Phase 25, 25-01 / 25-02).

Two route families with DELIBERATELY different auth postures:

* MINT / REVOKE — ``/api/projects/{pid}/sessions/{sid}/share`` — an OWNER action,
  so it stays behind the normal X-API-Key gate (ApiKeyMiddleware). The minter is
  recorded as ``created_by``.
* ATTACH (read) / SEND (co-drive) — ``/api/shared-sessions/{token}/...`` — the
  share token IS the credential, so these paths are in the ApiKeyMiddleware
  bypass set (verified in-handler). A ``read`` token can only reach the read
  attach route (streams.py); the co-drive SEND route requires a ``chat`` scope.
"""

from __future__ import annotations

from typing import Any, Optional

from litestar import Request, Router, delete, post
from litestar.exceptions import ClientException, NotAuthorizedException, NotFoundException

from app.db.session_shares import (
    VALID_SCOPES,
    list_shares_for_session,
    mint_share_token,
    revoke_share_token,
)
from app.services.session_sharing_service import SessionSharingService
from app_litestar.auth import Caller

# ---------------------------------------------------------------------------
# Owner-gated mint / revoke (X-API-Key required)
# ---------------------------------------------------------------------------


@post("/{project_id:str}/sessions/{session_id:str}/share", status_code=201, sync_to_thread=False)
def mint_share(project_id: str, session_id: str, data: dict, caller: Caller) -> dict[str, Any]:
    """Mint a scoped share token for a running session (owner action).

    Body: ``{"scope": "read"|"chat", "ttl_seconds"?: int}``. Returns
    ``{token, scope, expires_at}``.
    """
    del project_id
    body = data or {}
    scope = body.get("scope", "read")
    if scope not in VALID_SCOPES:
        raise ClientException(detail=f"scope must be one of {VALID_SCOPES}")
    ttl = body.get("ttl_seconds")
    created_by = getattr(caller, "user_id", None) if caller else None
    kwargs: dict[str, Any] = {"scope": scope, "created_by": created_by}
    if ttl is not None:
        try:
            kwargs["ttl_seconds"] = int(ttl)
        except (TypeError, ValueError) as exc:
            raise ClientException(detail="ttl_seconds must be an integer") from exc
    token = mint_share_token(session_id, **kwargs)
    shares = list_shares_for_session(session_id)
    minted = next((s for s in shares if s["token"] == token), None)
    return {
        "token": token,
        "scope": scope,
        "expires_at": minted["expires_at"] if minted else None,
    }


@delete(
    "/{project_id:str}/sessions/{session_id:str}/share/{token:str}",
    status_code=200,
    sync_to_thread=False,
)
def revoke_share(project_id: str, session_id: str, token: str, caller: Caller) -> dict[str, Any]:
    """Revoke a previously-minted share token (owner action)."""
    del project_id, session_id, caller
    revoked = revoke_share_token(token)
    if not revoked:
        raise NotFoundException(detail="Share token not found or already revoked")
    return {"revoked": True}


session_shares_router = Router(
    path="/api/projects",
    route_handlers=[mint_share, revoke_share],
)


# ---------------------------------------------------------------------------
# Token-authorized co-drive SEND (auth bypassed; token is the credential) — 25-02
# ---------------------------------------------------------------------------


def _actor_user_id(request: Request, token: str) -> str:
    """Resolve the co-driver's actor id.

    A cookie/bearer session (a signed-in teammate) attributes the action to that
    user; otherwise the action is attributed to a stable anonymous id derived
    from the share token, so policy/attribution still has a non-null principal.
    """
    from app_litestar.cookie_auth import SESSION_COOKIE, parse_cookies

    auth = request.headers.get("Authorization", "")
    session_token: Optional[str] = None
    if auth.lower().startswith("bearer "):
        session_token = auth[7:].strip() or None
    if not session_token:
        cookies = parse_cookies(request.headers.get("cookie", ""))
        session_token = cookies.get(SESSION_COOKIE) or None
    if session_token:
        from app.db.sessions import get_session_by_token

        sess = get_session_by_token(session_token)
        if sess:
            return sess["user_id"]
    return f"share:{token[:12]}"


@post("/{token:str}/send", status_code=200, sync_to_thread=False)
def co_drive_send(token: str, data: dict, request: Request) -> dict[str, Any]:
    """A chat-scope teammate's message → policy gate → operator's running session.

    The message is policy-checked (Phase-23) BEFORE it reaches stdin: a DENY (or a
    never-approved / timed-out ASK) surfaces as HTTP 403 and the operator's session
    is untouched; a read-scope token is rejected 403; an unknown/expired token is
    404. The ``/api/shared-sessions`` prefix is in the ApiKeyMiddleware bypass set
    (25-01), so this route inherits it — the token is the credential.
    """
    from app.db.session_shares import resolve_share_token
    from app.services.policy_service import PolicyDenied
    from app.services.session_sharing_service import CoDriveScopeError

    body = data or {}
    text = (body.get("text") or "").strip()
    if not text:
        raise ClientException(detail="text is required")

    row = resolve_share_token(token)
    if not row:
        raise NotFoundException(detail="Share session not found")
    session_id = row["session_id"]

    actor_user_id = _actor_user_id(request, token)
    try:
        ok = SessionSharingService.co_drive(session_id, token, text, actor_user_id)
    except CoDriveScopeError as exc:
        # A read token on the write path — forbid.
        raise NotAuthorizedException(detail=str(exc)) from exc
    except PolicyDenied as exc:
        # DENY / never-approved ASK / bounded-ASK timeout (fail closed).
        verdict = getattr(exc, "verdict", {}) or {}
        reason = verdict.get("reason", str(exc))
        raise NotAuthorizedException(detail=f"policy denied co-drive: {reason}") from exc
    return {"sent": bool(ok), "actor_user_id": actor_user_id}


co_drive_router = Router(
    path="/api/shared-sessions",
    route_handlers=[co_drive_send],
)
