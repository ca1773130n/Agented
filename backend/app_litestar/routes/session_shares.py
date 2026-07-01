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

from typing import Any

from litestar import Router, delete, post
from litestar.exceptions import ClientException, NotFoundException

from app.db.session_shares import (
    VALID_SCOPES,
    list_shares_for_session,
    mint_share_token,
    revoke_share_token,
)
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
