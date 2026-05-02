"""Smoke tests for the Litestar /admin/teams/* namespace (wave 53)."""

from litestar.testing import create_test_client

from app.db.rbac import create_user_role
from app_litestar.auth import provide_caller
from app_litestar.routes.health import health_router
from app_litestar.routes.teams import teams_router


def _client():
    return create_test_client(
        route_handlers=[health_router, teams_router],
        dependencies={"caller": provide_caller},
    )


def test_list_teams_bootstrap(isolated_db):
    with _client() as c:
        resp = c.get("/admin/teams/")
    assert resp.status_code == 200
    assert "teams" in resp.json()


def test_create_and_get_team(isolated_db):
    create_user_role("admin-key-tm", "Admin", "admin")
    with _client() as c:
        resp = c.post(
            "/admin/teams/",
            headers={"X-API-Key": "admin-key-tm"},
            json={"name": "Crew", "description": "test"},
        )
        assert resp.status_code == 201
        team_id = resp.json()["team"]["id"]

        resp = c.get(
            f"/admin/teams/{team_id}",
            headers={"X-API-Key": "admin-key-tm"},
        )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Crew"


def test_create_team_rejects_empty_name(isolated_db):
    create_user_role("admin-key-tm2", "Admin", "admin")
    with _client() as c:
        resp = c.post(
            "/admin/teams/",
            headers={"X-API-Key": "admin-key-tm2"},
            json={"name": ""},
        )
    assert resp.status_code == 400


def test_unknown_team_404(isolated_db):
    create_user_role("admin-key-tm3", "Admin", "admin")
    with _client() as c:
        resp = c.get(
            "/admin/teams/missing-id",
            headers={"X-API-Key": "admin-key-tm3"},
        )
    assert resp.status_code == 404


def test_list_team_members_works_for_unknown_team(isolated_db):
    """Stub returns empty members list when team has none — endpoint
    should not 500."""
    create_user_role("admin-key-tm4", "Admin", "admin")
    with _client() as c:
        resp = c.get(
            "/admin/teams/missing-id/members",
            headers={"X-API-Key": "admin-key-tm4"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"members": []}


def test_list_edges_unknown_team(isolated_db):
    create_user_role("admin-key-tm5", "Admin", "admin")
    with _client() as c:
        resp = c.get(
            "/admin/teams/missing-id/edges",
            headers={"X-API-Key": "admin-key-tm5"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"edges": []}


def test_list_connections_unknown_team(isolated_db):
    create_user_role("admin-key-tm6", "Admin", "admin")
    with _client() as c:
        resp = c.get(
            "/admin/teams/missing-id/connections",
            headers={"X-API-Key": "admin-key-tm6"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"connections": []}
