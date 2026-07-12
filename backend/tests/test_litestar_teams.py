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


def test_update_and_remove_member(isolated_db):
    """Regression for err-c5d3nq class: handlers passed team_id to db fns that don't take it.

    No keys are created, so ``provide_caller`` resolves the bootstrap admin and no
    ``X-API-Key`` header is needed — the point is exercising the update/remove route
    -> db-fn signatures, not auth.
    """
    from app.db.teams import add_team_member, create_team

    team_id = create_team("Crew5")
    member_id = add_team_member(team_id, name="Worker")
    with _client() as c:
        resp = c.put(
            f"/admin/teams/{team_id}/members/{member_id}",
            json={"role": "lead"},
        )
        assert resp.status_code == 200, resp.text

        resp = c.delete(f"/admin/teams/{team_id}/members/{member_id}")
        assert resp.status_code == 200, resp.text

        resp = c.get(f"/admin/teams/{team_id}/members")
    assert resp.json() == {"members": []}


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


def test_import_yaml_rejects_oversized_body(isolated_db):
    """An over-cap YAML import body is rejected at the route before parsing."""
    from app_litestar.routes.teams import _YAML_IMPORT_MAX_BYTES

    create_user_role("admin-key-tm7", "Admin", "admin")
    oversized = "a: " + ("x" * (_YAML_IMPORT_MAX_BYTES + 1))
    with _client() as c:
        resp = c.post(
            "/admin/teams/import-yaml",
            headers={"X-API-Key": "admin-key-tm7"},
            json={"yaml": oversized},
        )
    assert resp.status_code == 400
    assert "at most" in resp.json()["detail"]


def test_import_yaml_accepts_normal_team(isolated_db):
    """A normal-sized team YAML imports fine (the cap does not block real use)."""
    from app.services import yaml_authoring_service as yas

    create_user_role("admin-key-tm8", "Admin", "admin")
    cfg = {
        "version": yas.CONFIG_VERSION,
        "kind": yas.CONFIG_KIND,
        "metadata": {"name": "Import Crew"},
        "spec": {
            "topology": "coordinator",
            "topology_config": {"coordinator": "lead", "workers": ["w1"]},
            "members": [
                {"ref": "lead", "name": "lead", "role": "leader", "layer": "backend"},
                {"ref": "w1", "name": "w1", "role": "member", "layer": "backend"},
            ],
            "edges": [{"source": "lead", "target": "w1", "edge_type": "delegation", "weight": 1}],
        },
    }
    text = yas.dump_team_config(cfg)
    with _client() as c:
        resp = c.post(
            "/admin/teams/import-yaml",
            headers={"X-API-Key": "admin-key-tm8"},
            json={"yaml": text},
        )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "created"
