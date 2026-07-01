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

import hmac
import os
from typing import Any, Optional
from urllib.parse import urlsplit

from litestar import Request, Router, delete, post
from litestar.exceptions import (
    ClientException,
    NotAuthorizedException,
    NotFoundException,
    PermissionDeniedException,
)

from app.db.session_shares import (
    VALID_SCOPES,
    get_project_session_owner,
    mint_share_token,
    resolve_share_token,
    revoke_share_token,
)
from app.services.session_sharing_service import SessionSharingService
from app_litestar.auth import Caller

# The co-drive SEND route is auth-bypassed (the share token is the credential),
# so the token MUST also be echoed in this header to defeat a cross-site forged
# POST that only knows a leaked share URL (see ``_enforce_co_drive_csrf``).
SHARE_TOKEN_HEADER = "x-share-token"

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
    created_by = getattr(caller, "user_id", None) if caller else None
    role = getattr(caller, "role", None) if caller else None

    # SECURITY (25 BLOCKER — ownership gate): minting a share token hands out
    # access to a session, so ONLY the session's owner (or an admin) may mint
    # one. Fail CLOSED: an unknown owner (no ``created_by`` recorded) or a
    # caller who isn't that owner is forbidden — a non-owner must never be able
    # to fabricate a share for a session they don't own.
    if role != "admin":
        owner = get_project_session_owner(session_id)
        if owner is None or created_by is None or created_by != owner:
            raise PermissionDeniedException(
                detail="Only the session owner may mint a share token"
            )

    ttl = body.get("ttl_seconds")
    kwargs: dict[str, Any] = {"scope": scope, "created_by": created_by}
    if ttl is not None:
        try:
            kwargs["ttl_seconds"] = int(ttl)
        except (TypeError, ValueError) as exc:
            raise ClientException(detail="ttl_seconds must be an integer") from exc
    token = mint_share_token(session_id, **kwargs)
    # Resolve the freshly-minted (live) token to surface its expiry. Tokens are
    # stored hashed, so we can't match the raw token against a listing.
    minted = resolve_share_token(token)
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


def _trusted_origin_hosts() -> set[str]:
    """Hosts whose ``Origin`` is treated as same-site for the co-drive POST.

    Localhost is trusted so ``vite dev`` keeps working: its proxy sets
    ``changeOrigin`` (rewriting Host to the backend) while the browser Origin
    stays ``localhost:3000``, which would otherwise look cross-site. Deployments
    behind a different hostname can widen this via ``AGENTED_TRUSTED_ORIGINS``
    (comma-separated hosts or origins).
    """
    hosts = {"localhost", "127.0.0.1", "[::1]", "::1"}
    for part in (os.environ.get("AGENTED_TRUSTED_ORIGINS", "") or "").split(","):
        h = part.strip().lower()
        if h:
            hosts.add((urlsplit(h).hostname or h))
    return hosts


def _enforce_co_drive_csrf(request: Request, token: str) -> None:
    """Reject a forged / cross-site co-drive POST (25 MAJOR — CSRF on send route).

    The co-drive route is auth-bypassed (the share token is the credential), so a
    page that merely learns a leaked share URL must NOT be able to drive the
    operator's session from the teammate's browser. Two independent,
    defense-in-depth checks — neither weakens the token model:

      1) The share token MUST be echoed in the ``X-Share-Token`` request HEADER and
         match the path token (constant-time). Setting a custom header on a
         cross-origin ``fetch`` forces a CORS preflight the server never
         green-lights, so a forged cross-site POST cannot carry it — while the
         same-origin ``SharedSessionView`` sets it freely. Token in the URL path
         ALONE is no longer sufficient.
      2) If an ``Origin`` header is present it must not be cross-site: the
         same-origin SPA passes; an explicit foreign Origin is rejected.
    """
    header_token = request.headers.get(SHARE_TOKEN_HEADER, "") or ""
    if not header_token or not hmac.compare_digest(header_token, token):
        raise PermissionDeniedException(
            detail="co-drive requires the share token in the X-Share-Token header"
        )
    origin = request.headers.get("origin") or ""
    if origin:
        origin_host = (urlsplit(origin).hostname or "").lower()
        host = (request.headers.get("host") or "").split(":")[0].lower()
        fwd = (request.headers.get("x-forwarded-host") or "").split(":")[0].lower()
        if origin_host and origin_host not in {host, fwd} and origin_host not in _trusted_origin_hosts():
            raise PermissionDeniedException(detail="cross-site co-drive rejected")


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
    from app.services.policy_service import PolicyDenied
    from app.services.session_sharing_service import CoDriveScopeError

    # CSRF / cross-site guard BEFORE any lookup or IO (the token is the credential
    # and this route is auth-bypassed) — a forged cross-site POST is rejected here.
    _enforce_co_drive_csrf(request, token)

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
