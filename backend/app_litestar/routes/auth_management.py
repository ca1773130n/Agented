"""v0.5.12: auth-management routes (logout, admin-revoke, session events read)."""

from __future__ import annotations

from typing import Any, Optional

from litestar import Request, Router, get, post

from app.db import sessions as _sessions
from app.db.session_events import list_session_events
from app_litestar.auth_guards import requires_role


@post("/auth/logout", status_code=200, sync_to_thread=False)
def logout(request: Request) -> dict[str, Any]:
    """Revoke ALL of the caller's bearer sessions.

    Why all: middleware rotates the token on every request, so the
    bearer in the auth header may already be in `rotated_from_token`
    by the time this handler runs. Revoking by user_id covers both
    current and rotated-from token states reliably.
    """
    principal = request.scope.get("state", {}).get("principal")
    if not principal or not principal.get("user_id"):
        return {"revoked_count": 0}
    n = _sessions.revoke_user_sessions(principal["user_id"], reason="logout")
    return {"revoked_count": n}


@post(
    "/users/{user_id:str}/sessions/revoke",
    status_code=200,
    sync_to_thread=False,
    guards=[requires_role("admin")],
)
def admin_revoke_user_sessions(user_id: str) -> dict[str, Any]:
    """Admin-only: revoke every active session for the given user.

    Returns `{"revoked_count": 0}` if the user has no active sessions
    or doesn't exist — by design, so admins can call this idempotently
    without first checking user existence.
    """
    n = _sessions.revoke_user_sessions(user_id, reason="admin")
    return {"revoked_count": n}


SESSION_EVENTS_MAX_LIMIT = 500


@get(
    "/auth/session-events",
    sync_to_thread=False,
    guards=[requires_role("admin")],
)
def admin_list_session_events(
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Admin-only: read the session-event audit log with filters."""
    capped_limit = max(1, min(limit, SESSION_EVENTS_MAX_LIMIT))
    events = list_session_events(
        user_id=user_id,
        session_id=session_id,
        event_type=event_type,
        limit=capped_limit,
        offset=max(0, offset),
    )
    return {"events": events, "count": len(events)}


auth_management_router = Router(
    path="/admin",
    route_handlers=[logout, admin_revoke_user_sessions, admin_list_session_events],
)
