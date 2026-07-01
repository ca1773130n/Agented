"""stream_project_session owner/token gate (Phase 25, 25-01 locked decision #5).

SECURITY (25 BLOCKER — fail CLOSED): a caller may stream a project session ONLY
when they are an ``admin``, the recorded owner (``project_sessions.created_by``),
or a holder of a valid scoped share token. A NULL/unknown owner grants NOTHING
to a non-admin, non-token caller — an unattributed session is treated as
forbidden (was previously streamable by anyone, a fail-OPEN hole). Every denied
path raises 404 (``NotFoundException``).
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


def _caller(user_id, role="member"):
    """A non-admin caller by default (so the owner check is what grants access)."""
    return Caller(api_key="k", role=role, user_id=user_id, auth_method="api_key")


def _request(share_token=None):
    return SimpleNamespace(query_params=SimpleNamespace(get=lambda key, default=None: share_token))


def test_non_owner_without_token_gets_404(isolated_db):
    _seed_owned_session()
    with pytest.raises(NotFoundException):
        stream_project_session.fn("proj-x", "psess-owned", _caller("user-intruder"), _request())


def test_owner_streams(isolated_db):
    _seed_owned_session()
    # The owner (non-admin) is allowed — the handler returns a Stream.
    resp = stream_project_session.fn("proj-x", "psess-owned", _caller("user-owner"), _request())
    assert isinstance(resp, Stream)


def test_admin_streams_any_session(isolated_db):
    _seed_owned_session()
    # An admin who is NOT the owner may still stream (explicit admin bypass).
    resp = stream_project_session.fn(
        "proj-x", "psess-owned", _caller("some-admin", role="admin"), _request()
    )
    assert isinstance(resp, Stream)


def test_non_owner_with_valid_share_token_streams(isolated_db):
    _seed_owned_session()
    token = mint_share_token("psess-owned", scope="read")
    resp = stream_project_session.fn(
        "proj-x", "psess-owned", _caller("user-intruder"), _request(share_token=token)
    )
    assert isinstance(resp, Stream)


def _seed_unowned_session():
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name) VALUES ('proj-y', 'p')")
        conn.execute(
            "INSERT INTO project_sessions (id, project_id, status) VALUES "
            "('psess-legacy', 'proj-y', 'active')"
        )
        conn.commit()


def test_unowned_session_denied_for_non_admin_without_token(isolated_db):
    # FAIL CLOSED: a NULL-owner (legacy/autonomous) session is NOT public. A
    # non-admin caller with no share token is denied (previously streamed).
    _seed_unowned_session()
    with pytest.raises(NotFoundException):
        stream_project_session.fn("proj-y", "psess-legacy", _caller("anyone"), _request())


def test_unowned_session_streamable_by_admin(isolated_db):
    # An admin can still stream an unattributed session (admin bypass).
    _seed_unowned_session()
    resp = stream_project_session.fn(
        "proj-y", "psess-legacy", _caller("root", role="admin"), _request()
    )
    assert isinstance(resp, Stream)


def test_unowned_session_streamable_with_share_token(isolated_db):
    # A valid share token also admits a non-admin to an unattributed session.
    _seed_unowned_session()
    token = mint_share_token("psess-legacy", scope="read")
    resp = stream_project_session.fn(
        "proj-y", "psess-legacy", _caller("anyone"), _request(share_token=token)
    )
    assert isinstance(resp, Stream)
