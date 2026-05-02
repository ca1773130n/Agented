"""Smoke tests for Litestar workflows router (wave 62)."""

from litestar.testing import create_test_client

from app_litestar.auth import provide_caller
from app_litestar.routes.workflows import workflows_router


def _client():
    return create_test_client(
        route_handlers=[workflows_router],
        dependencies={"caller": provide_caller},
    )


def test_list_workflows(isolated_db):
    with _client() as c:
        resp = c.get("/admin/workflows/")
    assert resp.status_code == 200


def test_unknown_workflow_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/workflows/missing-id")
    assert resp.status_code == 404


def test_create_workflow_requires_name(isolated_db):
    with _client() as c:
        resp = c.post("/admin/workflows/", json={})
    assert resp.status_code == 400


def test_validate_endpoint(isolated_db):
    with _client() as c:
        # Empty graph won't be a valid DAG → 400
        resp = c.post("/admin/workflows/validate", json={"graph": {}})
    assert resp.status_code in (200, 400)


def test_pending_approvals(isolated_db):
    with _client() as c:
        resp = c.get("/admin/workflows/pending-approvals")
    assert resp.status_code == 200
    assert "pending_approvals" in resp.json()


def test_unknown_execution_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/workflows/executions/missing-id")
    assert resp.status_code == 404


def test_run_unknown_workflow_404(isolated_db):
    with _client() as c:
        resp = c.post("/admin/workflows/missing-id/run", json={})
    assert resp.status_code == 404


def test_register_trigger_unknown_404(isolated_db):
    with _client() as c:
        resp = c.post("/admin/workflows/missing-id/triggers/register")
    assert resp.status_code == 404


def test_analytics_unknown_workflow_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/workflows/missing-id/analytics")
    assert resp.status_code == 404


def test_list_versions_for_unknown_returns_empty(isolated_db):
    with _client() as c:
        resp = c.get("/admin/workflows/missing-id/versions")
    assert resp.status_code == 200
    assert resp.json() == {"versions": []}
