"""Smoke tests for the wave 76 leaf CRUD batch."""

from litestar.testing import create_test_client

from app_litestar.auth import provide_caller
from app_litestar.routes.leaf_crud_i import (
    chunks_router,
    setup_router,
    super_agent_chat_router,
    super_agent_messages_router,
    team_generation_router,
)


def _client():
    return create_test_client(
        route_handlers=[
            setup_router,
            super_agent_messages_router,
            team_generation_router,
            chunks_router,
            super_agent_chat_router,
        ],
        dependencies={"caller": provide_caller},
    )


# Setup


def test_start_setup_requires_project(isolated_db):
    with _client() as c:
        resp = c.post("/api/setup/start", json={})
    assert resp.status_code == 400


def test_start_setup_unknown_project_404(isolated_db):
    with _client() as c:
        resp = c.post(
            "/api/setup/start",
            json={"project_id": "missing", "command": "init"},
        )
    assert resp.status_code == 404


def test_unknown_setup_status_404(isolated_db):
    with _client() as c:
        resp = c.get("/api/setup/missing/status")
    assert resp.status_code == 404


def test_unknown_setup_respond_404(isolated_db):
    with _client() as c:
        resp = c.post(
            "/api/setup/missing/respond",
            json={"interaction_id": "x", "response": "y"},
        )
    assert resp.status_code == 404


def test_unknown_setup_cancel_404(isolated_db):
    with _client() as c:
        resp = c.delete("/api/setup/missing")
    assert resp.status_code == 404


# Super-agent messages


def test_send_message_requires_content(isolated_db):
    with _client() as c:
        resp = c.post("/admin/super-agents/sa-x/messages", json={})
    assert resp.status_code == 400


def test_inbox_empty(isolated_db):
    with _client() as c:
        resp = c.get("/admin/super-agents/sa-x/messages/inbox")
    assert resp.status_code == 200


def test_outbox_empty(isolated_db):
    with _client() as c:
        resp = c.get("/admin/super-agents/sa-x/messages/outbox")
    assert resp.status_code == 200


def test_mark_unknown_message_404(isolated_db):
    with _client() as c:
        resp = c.post(
            "/admin/super-agents/sa-x/messages/missing/read", json={}
        )
    assert resp.status_code == 404


def test_delete_agent_message_success(isolated_db):
    """DELETE removes a message that belongs to the given super-agent inbox."""
    from app.db.messages import add_agent_message, get_inbox_messages
    from app.db.super_agents import create_super_agent

    sender_id = create_super_agent(name="sender")
    owner_id = create_super_agent(name="owner")
    msg_id = add_agent_message(
        from_agent_id=sender_id,
        to_agent_id=owner_id,
        content="hello",
    )
    assert msg_id is not None

    with _client() as c:
        resp = c.delete(f"/admin/super-agents/{owner_id}/messages/{msg_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["message"] == "Message deleted"
    assert get_inbox_messages(owner_id) == []


def test_delete_agent_message_wrong_owner_returns_404(isolated_db):
    """DELETE refuses to remove a message owned by a different super-agent."""
    from app.db.messages import add_agent_message, get_inbox_messages
    from app.db.super_agents import create_super_agent

    sender_id = create_super_agent(name="sender2")
    owner_a = create_super_agent(name="owner-A")
    owner_b = create_super_agent(name="owner-B")
    msg_id = add_agent_message(
        from_agent_id=sender_id,
        to_agent_id=owner_a,
        content="hello",
    )
    assert msg_id is not None

    with _client() as c:
        resp = c.delete(f"/admin/super-agents/{owner_b}/messages/{msg_id}")
    assert resp.status_code == 404
    # Row still present in the real owner's inbox.
    assert len(get_inbox_messages(owner_a)) == 1


def test_delete_agent_message_not_found(isolated_db):
    with _client() as c:
        resp = c.delete("/admin/super-agents/sa-x/messages/missing-msg")
    assert resp.status_code == 404


# Team generation


def test_generate_requires_description(isolated_db):
    with _client() as c:
        resp = c.post("/admin/teams/generate", json={})
    assert resp.status_code == 400


def test_generate_too_short(isolated_db):
    with _client() as c:
        resp = c.post(
            "/admin/teams/generate", json={"description": "short"}
        )
    assert resp.status_code == 400


def test_get_unknown_job_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/teams/generate/missing")
    assert resp.status_code == 404


# Chunks


def test_run_chunked_unknown_bot_404(isolated_db):
    with _client() as c:
        resp = c.post(
            "/admin/bots/missing/run-chunked",
            json={"content": "hello"},
        )
    assert resp.status_code == 404


def test_chunked_status_unknown_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/chunked-executions/missing")
    assert resp.status_code == 404


def test_chunked_results_unknown_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/chunked-executions/missing/results")
    assert resp.status_code == 404


# Super-agent chat


def test_send_chat_requires_content(isolated_db):
    with _client() as c:
        resp = c.post(
            "/admin/super-agents/sa-x/sessions/sess-x/chat", json={}
        )
    assert resp.status_code == 400


def test_send_chat_unknown_session_404(isolated_db):
    with _client() as c:
        resp = c.post(
            "/admin/super-agents/sa-x/sessions/missing/chat",
            json={"content": "hi"},
        )
    assert resp.status_code == 404


def test_send_chat_forwards_use_cli_agent_override(isolated_db, monkeypatch):
    """`use_cli_agent` in body must reach `run_streaming_response`.

    Pins the AiChatPanel toggle's plumbing on the super-agent chat
    endpoint (Playground / WorkflowPlaygroundPage). Bool values flow
    through; non-bool falls back to None so the global YOLO setting
    decides — keeps the override unambiguous.
    """
    from app.db.super_agents import create_super_agent
    from app.services.super_agent_session_service import SuperAgentSessionService
    from app_litestar.routes import leaf_crud_i

    sa_id = create_super_agent(name="t")
    session_id, _ = SuperAgentSessionService.create_session(sa_id)

    captured: list[dict] = []

    def _fake_run(**kwargs):
        captured.append(kwargs)

    monkeypatch.setattr(leaf_crud_i, "run_streaming_response", _fake_run, raising=False)
    # The route imports the helper inside the function body, so patch the
    # source module too.
    import app.services.streaming_helper as helper

    monkeypatch.setattr(helper, "run_streaming_response", _fake_run)

    with _client() as c:
        resp = c.post(
            f"/admin/super-agents/{sa_id}/sessions/{session_id}/chat",
            json={"content": "hi", "use_cli_agent": True},
        )
    assert resp.status_code in (200, 201), resp.text
    assert captured and captured[-1].get("use_cli_agent") is True

    captured.clear()
    with _client() as c:
        resp = c.post(
            f"/admin/super-agents/{sa_id}/sessions/{session_id}/chat",
            json={"content": "hi", "use_cli_agent": False},
        )
    assert captured and captured[-1].get("use_cli_agent") is False

    # Missing → None (defer to global YOLO).
    captured.clear()
    with _client() as c:
        resp = c.post(
            f"/admin/super-agents/{sa_id}/sessions/{session_id}/chat",
            json={"content": "hi"},
        )
    assert captured and captured[-1].get("use_cli_agent") is None

    # Non-bool → None (don't honor strings/numbers).
    captured.clear()
    with _client() as c:
        resp = c.post(
            f"/admin/super-agents/{sa_id}/sessions/{session_id}/chat",
            json={"content": "hi", "use_cli_agent": "yes"},
        )
    assert captured and captured[-1].get("use_cli_agent") is None
