"""GET /admin/super-agents/activity-status — coverage.

The endpoint powers the activity pill on the SA list page and the
"working now" badge on the project dashboard's session cards. Pin the
contract so a future refactor of either ChatStateService or the
session DB can't silently break the UI.
"""

from __future__ import annotations

from litestar.testing import create_test_client

from app_litestar.auth import provide_caller
from app_litestar.routes.super_agents_cluster import super_agents_router


def _client():
    return create_test_client(
        route_handlers=[super_agents_router],
        dependencies={"caller": provide_caller},
    )


def test_activity_status_empty_when_no_sessions(isolated_db):
    with _client() as c:
        resp = c.get("/admin/super-agents/activity-status")
    assert resp.status_code == 200
    assert resp.json() == {"statuses": {}}


def test_activity_status_counts_active_sessions(isolated_db):
    """Each SA's row reflects the count of ``status='active'`` rows in
    ``super_agent_sessions``. SAs with only completed sessions don't
    appear in the map."""
    from app.db.super_agents import create_super_agent
    from app.services.super_agent_session_service import SuperAgentSessionService

    sa_a = create_super_agent(name="agent-a")
    sa_b = create_super_agent(name="agent-b")
    sa_c = create_super_agent(name="agent-c")

    SuperAgentSessionService.create_session(sa_a)
    SuperAgentSessionService.create_session(sa_a)
    SuperAgentSessionService.create_session(sa_b)
    # sa_c gets no sessions.

    with _client() as c:
        body = c.get("/admin/super-agents/activity-status").json()

    statuses = body["statuses"]
    assert statuses[sa_a]["active_sessions"] == 2
    assert statuses[sa_a]["is_streaming"] is False
    assert statuses[sa_b]["active_sessions"] == 1
    assert statuses[sa_b]["is_streaming"] is False
    assert sa_c not in statuses


def test_activity_status_flags_streaming_sa(isolated_db):
    """When a session in ``ChatStateService`` is in ``streaming`` state,
    the SA the session belongs to is flagged ``is_streaming=true``."""
    from app.db.super_agents import create_super_agent
    from app.services.chat_state_service import ChatStateService
    from app.services.super_agent_session_service import SuperAgentSessionService

    sa_id = create_super_agent(name="streamer")
    session_id, _ = SuperAgentSessionService.create_session(sa_id)
    ChatStateService.init_session(session_id)
    ChatStateService.push_status(session_id, "streaming")

    try:
        with _client() as c:
            statuses = c.get("/admin/super-agents/activity-status").json()["statuses"]
    finally:
        ChatStateService.remove_session(session_id)

    assert statuses[sa_id]["is_streaming"] is True
    assert statuses[sa_id]["active_sessions"] == 1


def test_activity_status_idle_session_not_streaming(isolated_db):
    """An ``idle`` ChatStateService session doesn't trip the streaming flag."""
    from app.db.super_agents import create_super_agent
    from app.services.chat_state_service import ChatStateService
    from app.services.super_agent_session_service import SuperAgentSessionService

    sa_id = create_super_agent(name="idler")
    session_id, _ = SuperAgentSessionService.create_session(sa_id)
    ChatStateService.init_session(session_id)  # default status = "idle"

    try:
        with _client() as c:
            statuses = c.get("/admin/super-agents/activity-status").json()["statuses"]
    finally:
        ChatStateService.remove_session(session_id)

    assert statuses[sa_id]["is_streaming"] is False
