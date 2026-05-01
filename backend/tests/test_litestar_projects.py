"""Smoke tests for the Litestar /admin/projects/* namespace (wave 55)."""

from litestar.testing import create_test_client

from app.db.rbac import create_user_role
from app_litestar.auth import provide_caller
from app_litestar.routes.health import health_router
from app_litestar.routes.projects import projects_router


def _client():
    return create_test_client(
        route_handlers=[health_router, projects_router],
        dependencies={"caller": provide_caller},
    )


def test_list_projects_bootstrap(isolated_db):
    with _client() as c:
        resp = c.get("/admin/projects/")
    assert resp.status_code == 200
    assert "projects" in resp.json()


def test_create_and_get_project(isolated_db):
    create_user_role("admin-key-pj", "Admin", "admin")
    with _client() as c:
        resp = c.post(
            "/admin/projects/",
            headers={"X-API-Key": "admin-key-pj"},
            json={"name": "MyProj", "description": "test"},
        )
        assert resp.status_code == 201
        project_id = resp.json()["project"]["id"]

        resp = c.get(
            f"/admin/projects/{project_id}",
            headers={"X-API-Key": "admin-key-pj"},
        )
    assert resp.status_code == 200
    assert resp.json()["name"] == "MyProj"


def test_create_project_rejects_empty(isolated_db):
    create_user_role("admin-key-pj2", "Admin", "admin")
    with _client() as c:
        resp = c.post(
            "/admin/projects/",
            headers={"X-API-Key": "admin-key-pj2"},
            json={},
        )
    assert resp.status_code == 400


def test_unknown_project_404(isolated_db):
    create_user_role("admin-key-pj3", "Admin", "admin")
    with _client() as c:
        resp = c.get(
            "/admin/projects/missing-id",
            headers={"X-API-Key": "admin-key-pj3"},
        )
    assert resp.status_code == 404


def test_list_skills_unknown_project(isolated_db):
    create_user_role("admin-key-pj4", "Admin", "admin")
    with _client() as c:
        resp = c.get(
            "/admin/projects/missing-id/skills",
            headers={"X-API-Key": "admin-key-pj4"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"skills": []}


def test_list_team_edges_unknown_project(isolated_db):
    create_user_role("admin-key-pj5", "Admin", "admin")
    with _client() as c:
        resp = c.get(
            "/admin/projects/missing-id/team-edges",
            headers={"X-API-Key": "admin-key-pj5"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"edges": []}


def test_list_sessions_unknown_project(isolated_db):
    create_user_role("admin-key-pj6", "Admin", "admin")
    with _client() as c:
        resp = c.get(
            "/admin/projects/missing-id/sessions",
            headers={"X-API-Key": "admin-key-pj6"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "sessions" in body


def test_install_validates_component_type(isolated_db):
    create_user_role("admin-key-pj7", "Admin", "admin")
    with _client() as c:
        resp = c.post(
            "/admin/projects/proj-x/install",
            headers={"X-API-Key": "admin-key-pj7"},
            json={"component_type": "ghost", "component_id": "x"},
        )
    assert resp.status_code == 400
