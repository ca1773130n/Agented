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
