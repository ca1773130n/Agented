"""Phase 25 BLOCKER ITEM 2 — session ownership stamped from the resolved Caller.

A session created via the (cookie-authenticated) SPA path must record a non-NULL
``project_sessions.created_by`` so the owner-gated SSE stream admits its owner and
denies everyone else.

Before the fix the ``create_session`` backfill read ``current_user_var``, which
``RequestContextMiddleware`` only set for API-key / bearer auth — so a
cookie-authenticated create (the normal browser flow) left ``created_by`` NULL and
``stream_project_session`` then treated the session as unowned → streamable by any
authenticated caller who knew the id.

The authoritative fix stamps from ``caller.user_id`` (populated for EVERY auth
method by ``provide_caller``); the middleware additionally now resolves the session
cookie into ``current_user_var`` (defense-in-depth). These tests call the route with
``current_user_var`` intentionally UNSET, proving the owner comes from the Caller.
"""

from types import SimpleNamespace

import pytest
from litestar.exceptions import NotFoundException
from litestar.response import Stream

from app.db.connection import get_connection
from app.db.session_shares import get_project_session_owner
from app.db.sessions import create_session as create_login_session
from app.db.users import create_user
from app_litestar.auth import Caller
from app_litestar.cookie_auth import SESSION_COOKIE
from app_litestar.middleware import _resolve_cookie_user
from app_litestar.routes.grd_routes import create_session
from app_litestar.routes.streams import stream_project_session


def _caller(user_id, role="member"):
    return Caller(api_key="k", role=role, user_id=user_id, auth_method="api_key")


def _request(share_token=None):
    return SimpleNamespace(query_params=SimpleNamespace(get=lambda key, default=None: share_token))


def _seed_project(pid="proj-own"):
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name) VALUES (?, 'Owner Stamp')", (pid,))
        conn.commit()


def _stub_handler(monkeypatch, session_id, project_id="proj-own"):
    """Stub DirectExecutionHandler.start to insert an OWNER-LESS project_sessions row.

    Mirrors the real handler: it inserts the row with NO ``created_by`` — the route
    is what must backfill the owner (from the Caller), which is exactly what we pin.
    """
    from app.services.execution_type_handler import DirectExecutionHandler

    def fake_start(self, config):  # noqa: ARG001
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO project_sessions (id, project_id, status) VALUES (?, ?, 'active')",
                (session_id, config.get("project_id", project_id)),
            )
            conn.commit()
        return {"session_id": session_id, "pid": 1234, "status": "active"}

    monkeypatch.setattr(DirectExecutionHandler, "start", fake_start)


def test_cookie_auth_create_stamps_created_by_from_caller(isolated_db, monkeypatch):
    _seed_project()
    _stub_handler(monkeypatch, "psess-own1")
    body = {"cmd": ["claude"], "cwd": "/tmp", "yolo_mode": True, "execution_type": "direct"}
    # current_user_var is intentionally NOT set — the owner MUST come from caller.
    result = create_session.fn("proj-own", body, _caller("owner-42"))
    assert result["session_id"] == "psess-own1"
    assert get_project_session_owner("psess-own1") == "owner-42"


def test_owner_and_admin_stream_cookie_created_session_nonowner_denied(isolated_db, monkeypatch):
    _seed_project()
    _stub_handler(monkeypatch, "psess-own2")
    create_session.fn(
        "proj-own",
        {"cmd": ["claude"], "cwd": "/tmp", "yolo_mode": True},
        _caller("owner-42"),
    )
    # Non-owner is denied (would have STREAMED before the fix — NULL owner was open).
    with pytest.raises(NotFoundException):
        stream_project_session.fn("proj-own", "psess-own2", _caller("intruder"), _request())
    # The owner and an admin are admitted.
    assert isinstance(
        stream_project_session.fn("proj-own", "psess-own2", _caller("owner-42"), _request()),
        Stream,
    )
    assert isinstance(
        stream_project_session.fn(
            "proj-own", "psess-own2", _caller("root", role="admin"), _request()
        ),
        Stream,
    )


def test_middleware_resolves_cookie_user(isolated_db):
    # Defense-in-depth: current_user_var is now populated for cookie auth too.
    uid = create_user("cookie-user@example.com")
    sess = create_login_session(uid)
    assert sess is not None
    cookie = f"{SESSION_COOKIE}={sess['token']}"
    assert _resolve_cookie_user(cookie) == uid
    assert _resolve_cookie_user("") is None
    assert _resolve_cookie_user(None) is None
    assert _resolve_cookie_user(f"{SESSION_COOKIE}=bogus-token") is None
