"""Track A wave 23 — Litestar GET /admin/rbac/permissions parity tests."""

from litestar.testing import create_test_client

from app.db.rbac import create_user_role
from app_litestar.auth import provide_caller
from app_litestar.main import liveness
from app_litestar.routes.rbac import rbac_router


def _client(isolated_db):
    return create_test_client(
        route_handlers=[liveness, rbac_router],
        dependencies={"caller": provide_caller},
    )


def test_litestar_returns_permission_matrix_in_bootstrap_mode(isolated_db):
    # No roles → bootstrap mode → request without API key still allowed.
    with _client(isolated_db) as client:
        resp = client.get("/admin/rbac/permissions")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["permissions"].keys()) == {"viewer", "operator", "editor", "admin"}
    assert "manage" in body["permissions"]["admin"]
    assert "manage" not in body["permissions"]["viewer"]


def test_litestar_requires_auth_when_roles_configured(isolated_db):
    create_user_role("real-key", "Real", "admin")
    with _client(isolated_db) as client:
        resp = client.get("/admin/rbac/permissions")
    assert resp.status_code == 401


def test_litestar_accepts_valid_key(isolated_db):
    create_user_role("good-key", "Good", "viewer")
    with _client(isolated_db) as client:
        resp = client.get("/admin/rbac/permissions", headers={"X-API-Key": "good-key"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["permissions"]["viewer"] == ["read"]


class TestRotateRoleLitestar:
    """Wave 24 — POST /admin/rbac/roles/{id}/rotate."""

    def test_admin_can_rotate(self, isolated_db):
        from app.db.rbac import get_user_role
        admin_id = create_user_role("admin-key-ls", "Admin", "admin")
        target_id = create_user_role("stale-key-ls", "Edit", "editor")
        with _client(isolated_db) as ls:
            resp = ls.post(
                f"/admin/rbac/roles/{target_id}/rotate",
                headers={"X-API-Key": "admin-key-ls"},
            )
        assert resp.status_code == 201
        body = resp.json()
        assert body["role"]["label"] == "Edit"
        assert body["role"]["role"] == "editor"
        assert body["role"]["api_key"] != "stale-key-ls"
        assert len(body["role"]["api_key"]) == 64
        assert body["role"]["id"] != target_id
        assert get_user_role(target_id) is None
        assert get_user_role(body["role"]["id"]) is not None
        assert get_user_role(admin_id) is not None  # didn't accidentally rotate self

    def test_unknown_role_returns_404(self, isolated_db):
        create_user_role("admin-key-2", "Admin", "admin")
        with _client(isolated_db) as ls:
            resp = ls.post(
                "/admin/rbac/roles/role-missing/rotate",
                headers={"X-API-Key": "admin-key-2"},
            )
        assert resp.status_code == 404

    def test_non_admin_blocked(self, isolated_db):
        create_user_role("editor-key-ls", "Editor", "editor")
        target_id = create_user_role("victim-key", "Victim", "viewer")
        with _client(isolated_db) as ls:
            resp = ls.post(
                f"/admin/rbac/roles/{target_id}/rotate",
                headers={"X-API-Key": "editor-key-ls"},
            )
        assert resp.status_code == 403


# Wave 25: side-by-side parity test deleted — the Flask version of these
# routes was retired this wave, so there's nothing left to compare against.
# The remaining tests in this file are the canonical RBAC API contract.
