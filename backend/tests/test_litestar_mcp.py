"""Smoke tests for the Litestar mcp_servers + project_mcp routers (wave 56)."""

from litestar.testing import create_test_client

from app.db.rbac import create_user_role
from app_litestar.auth import provide_caller
from app_litestar.routes.health import health_router
from app_litestar.routes.mcp_servers import mcp_servers_router, project_mcp_router


def _client():
    return create_test_client(
        route_handlers=[health_router, mcp_servers_router, project_mcp_router],
        dependencies={"caller": provide_caller},
    )


def test_list_mcp_servers_bootstrap(isolated_db):
    with _client() as c:
        resp = c.get("/admin/mcp-servers/")
    assert resp.status_code == 200
    assert "servers" in resp.json()


def test_create_and_get_mcp_server(isolated_db):
    create_user_role("admin-key-mcp", "Admin", "admin")
    with _client() as c:
        resp = c.post(
            "/admin/mcp-servers/",
            headers={"X-API-Key": "admin-key-mcp"},
            json={"name": "MyServer", "server_type": "stdio", "command": "/bin/true"},
        )
        assert resp.status_code == 201
        sid = resp.json()["id"]

        resp = c.get(
            f"/admin/mcp-servers/{sid}",
            headers={"X-API-Key": "admin-key-mcp"},
        )
    assert resp.status_code == 200
    assert resp.json()["name"] == "MyServer"


def test_create_rejects_empty_name(isolated_db):
    create_user_role("admin-key-mcp2", "Admin", "admin")
    with _client() as c:
        resp = c.post(
            "/admin/mcp-servers/",
            headers={"X-API-Key": "admin-key-mcp2"},
            json={},
        )
    assert resp.status_code == 400


def test_unknown_server_404(isolated_db):
    create_user_role("admin-key-mcp3", "Admin", "admin")
    with _client() as c:
        resp = c.get(
            "/admin/mcp-servers/missing-id",
            headers={"X-API-Key": "admin-key-mcp3"},
        )
    assert resp.status_code == 404


def test_list_project_mcp_servers(isolated_db):
    create_user_role("admin-key-mcp4", "Admin", "admin")
    with _client() as c:
        resp = c.get(
            "/admin/projects/proj-x/mcp-servers",
            headers={"X-API-Key": "admin-key-mcp4"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"servers": []}


def test_unassign_unknown_returns_404(isolated_db):
    create_user_role("admin-key-mcp5", "Admin", "admin")
    with _client() as c:
        resp = c.delete(
            "/admin/projects/proj-x/mcp-servers/server-x",
            headers={"X-API-Key": "admin-key-mcp5"},
        )
    assert resp.status_code == 404
