"""Smoke tests for the super_agents cluster (wave 63)."""

from litestar.testing import create_test_client

from app_litestar.auth import provide_caller
from app_litestar.routes.super_agents_cluster import (
    super_agent_exports_router,
    super_agents_router,
)


def _client():
    return create_test_client(
        route_handlers=[super_agents_router, super_agent_exports_router],
        dependencies={"caller": provide_caller},
    )


def test_list_super_agents(isolated_db):
    with _client() as c:
        resp = c.get("/admin/super-agents/")
    assert resp.status_code == 200
    assert "super_agents" in resp.json()


def test_create_requires_name(isolated_db):
    with _client() as c:
        resp = c.post("/admin/super-agents/", json={})
    assert resp.status_code == 400


def test_unknown_super_agent_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/super-agents/missing-id")
    assert resp.status_code == 404


def test_unknown_psa_instance_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/super-agents/psa-missing")
    assert resp.status_code == 404


def test_list_sessions_for_unknown_returns_empty(isolated_db):
    with _client() as c:
        resp = c.get("/admin/super-agents/missing-id/sessions")
    assert resp.status_code == 200


def test_unknown_session_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/super-agents/sa-x/sessions/missing-id")
    assert resp.status_code == 404


def test_message_requires_body(isolated_db):
    with _client() as c:
        resp = c.post(
            "/admin/super-agents/sa-x/sessions/sess-x/message",
            json={},
        )
    assert resp.status_code == 400


def test_git_action_invalid(isolated_db):
    with _client() as c:
        resp = c.post(
            "/admin/super-agents/sa-x/sessions/sess-x/git-action",
            json={"action": "ghost"},
        )
    assert resp.status_code == 400


def test_list_documents_for_unknown_returns_empty(isolated_db):
    with _client() as c:
        resp = c.get("/admin/super-agents/missing-id/documents")
    assert resp.status_code == 200
    assert resp.json() == {"documents": []}


def test_create_document_requires_doc_type(isolated_db):
    with _client() as c:
        resp = c.post(
            "/admin/super-agents/sa-x/documents",
            json={"title": "x"},
        )
    assert resp.status_code == 400


def test_unknown_document_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/super-agents/sa-x/documents/9999")
    assert resp.status_code == 404


def test_export_requires_super_agent_id(isolated_db):
    with _client() as c:
        resp = c.post("/admin/super-agent-exports/export", json={})
    assert resp.status_code == 400


def test_export_invalid_format(isolated_db):
    with _client() as c:
        resp = c.post(
            "/admin/super-agent-exports/export",
            json={"super_agent_id": "sa-x", "export_format": "tar"},
        )
    assert resp.status_code == 400


def test_import_requires_source(isolated_db):
    with _client() as c:
        resp = c.post("/admin/super-agent-exports/import", json={})
    assert resp.status_code == 400


def test_validate_requires_source(isolated_db):
    with _client() as c:
        resp = c.post("/admin/super-agent-exports/validate", json={})
    assert resp.status_code == 400
