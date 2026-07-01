"""stream_project_session owner/token gate (Phase 25, 25-01 locked decision #5).

Previously ANY authenticated caller could stream ANY project session. The gate
now allows only the session owner (``project_sessions.created_by``) OR a valid
scoped share token; a tokenless non-owner gets a 404 (NotFoundException). A
session with a NULL owner (legacy/autonomous) stays streamable — this test
covers the OWNED-session path where the gate is active.
"""

from types import SimpleNamespace

import pytest
from litestar.exceptions import NotFoundException
from litestar.response import Stream

from app.db.connection import get_connection
from app.db.session_shares import mint_share_token
from app_litestar.auth import Caller
from app_litestar.routes.streams import stream_project_session


def _seed_owned_session(session_id="psess-owned", owner="user-owner"):
    """Insert a minimal project_sessions row with an explicit owner."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name) VALUES (?, ?)",
            ("proj-x", "Gate Test Project"),
        )
        conn.execute(
            "INSERT INTO project_sessions (id, project_id, status, created_by) "
            "VALUES (?, ?, 'active', ?)",
            (session_id, "proj-x", owner),
        )
        conn.commit()


def _caller(user_id):
    return Caller(api_key="k", role="admin", user_id=user_id, auth_method="api_key")


def _request(share_token=None):
    return SimpleNamespace(query_params=SimpleNamespace(get=lambda key, default=None: share_token))


def test_non_owner_without_token_gets_404(isolated_db):
    _seed_owned_session()
    with pytest.raises(NotFoundException):
        stream_project_session.fn("proj-x", "psess-owned", _caller("user-intruder"), _request())


def test_owner_streams(isolated_db):
    _seed_owned_session()
    # The owner is allowed — the handler returns a Stream (generator not consumed).
    resp = stream_project_session.fn("proj-x", "psess-owned", _caller("user-owner"), _request())
    assert isinstance(resp, Stream)


def test_non_owner_with_valid_share_token_streams(isolated_db):
    _seed_owned_session()
    token = mint_share_token("psess-owned", scope="read")
    resp = stream_project_session.fn(
        "proj-x", "psess-owned", _caller("user-intruder"), _request(share_token=token)
    )
    assert isinstance(resp, Stream)


def test_unowned_session_streamable_by_anyone(isolated_db):
    # A NULL-owner (legacy/autonomous) session is not owner-gated.
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name) VALUES ('proj-y', 'p')")
        conn.execute(
            "INSERT INTO project_sessions (id, project_id, status) VALUES "
            "('psess-legacy', 'proj-y', 'active')"
        )
        conn.commit()
    resp = stream_project_session.fn("proj-y", "psess-legacy", _caller("anyone"), _request())
    assert isinstance(resp, Stream)
