"""Track A wave 23 — Litestar GET /admin/rbac/permissions parity tests."""

from litestar.testing import create_test_client

from app.db.rbac import create_user_role
from app_litestar.auth import provide_caller
from app_litestar.routes.health import health_router
from app_litestar.routes.rbac import rbac_router


def _client(isolated_db):
    return create_test_client(
        route_handlers=[health_router, rbac_router],
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


class TestListRolesLitestar:
    """Wave 26 — GET /admin/rbac/roles."""

    def test_admin_can_list_empty(self, isolated_db):
        create_user_role("admin-list-empty", "Admin", "admin")
        with _client(isolated_db) as ls:
            resp = ls.get(
                "/admin/rbac/roles",
                headers={"X-API-Key": "admin-list-empty"},
            )
        assert resp.status_code == 200
        body = resp.json()
        # Only the admin we just created is present.
        labels = [r["label"] for r in body["roles"]]
        assert "Admin" in labels

    def test_admin_can_list_multiple(self, isolated_db):
        create_user_role("admin-list-multi", "Admin", "admin")
        create_user_role("editor-list", "Editor", "editor")
        create_user_role("viewer-list", "Viewer", "viewer")
        with _client(isolated_db) as ls:
            resp = ls.get(
                "/admin/rbac/roles",
                headers={"X-API-Key": "admin-list-multi"},
            )
        assert resp.status_code == 200
        labels = {r["label"] for r in resp.json()["roles"]}
        assert {"Admin", "Editor", "Viewer"} <= labels

    def test_non_admin_blocked(self, isolated_db):
        create_user_role("editor-list-block", "Editor", "editor")
        with _client(isolated_db) as ls:
            resp = ls.get(
                "/admin/rbac/roles",
                headers={"X-API-Key": "editor-list-block"},
            )
        assert resp.status_code == 403


class TestGetRoleDetailLitestar:
    """Wave 27 — GET /admin/rbac/roles/{role_id}."""

    def test_admin_gets_existing_role(self, isolated_db):
        create_user_role("admin-detail", "Admin", "admin")
        target = create_user_role("target-detail", "Target", "viewer")
        with _client(isolated_db) as ls:
            resp = ls.get(
                f"/admin/rbac/roles/{target}",
                headers={"X-API-Key": "admin-detail"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == target
        assert body["label"] == "Target"
        assert body["role"] == "viewer"

    def test_unknown_id_returns_404(self, isolated_db):
        create_user_role("admin-detail-2", "Admin", "admin")
        with _client(isolated_db) as ls:
            resp = ls.get(
                "/admin/rbac/roles/role-missing",
                headers={"X-API-Key": "admin-detail-2"},
            )
        assert resp.status_code == 404

    def test_non_admin_blocked(self, isolated_db):
        create_user_role("editor-detail", "Editor", "editor")
        target = create_user_role("victim-detail", "Victim", "viewer")
        with _client(isolated_db) as ls:
            resp = ls.get(
                f"/admin/rbac/roles/{target}",
                headers={"X-API-Key": "editor-detail"},
            )
        assert resp.status_code == 403


class TestCreateRoleLitestar:
    """Wave 28 — POST /admin/rbac/roles."""

    def test_admin_creates_role(self, isolated_db):
        create_user_role("admin-create", "Admin", "admin")
        with _client(isolated_db) as ls:
            resp = ls.post(
                "/admin/rbac/roles",
                headers={"X-API-Key": "admin-create"},
                json={"api_key": "fresh-key", "label": "Fresh", "role": "operator"},
            )
        assert resp.status_code == 201
        body = resp.json()
        assert body["role"]["label"] == "Fresh"
        assert body["role"]["role"] == "operator"
        assert body["role"]["id"].startswith("role-")

    def test_invalid_role_value_returns_400(self, isolated_db):
        create_user_role("admin-create-bad", "Admin", "admin")
        with _client(isolated_db) as ls:
            resp = ls.post(
                "/admin/rbac/roles",
                headers={"X-API-Key": "admin-create-bad"},
                json={"api_key": "k", "label": "L", "role": "superadmin"},
            )
        assert resp.status_code == 400

    def test_duplicate_api_key_returns_400(self, isolated_db):
        create_user_role("admin-create-dup", "Admin", "admin")
        create_user_role("dup-key", "First", "viewer")
        with _client(isolated_db) as ls:
            resp = ls.post(
                "/admin/rbac/roles",
                headers={"X-API-Key": "admin-create-dup"},
                json={"api_key": "dup-key", "label": "Second", "role": "admin"},
            )
        assert resp.status_code == 400

    def test_non_admin_blocked(self, isolated_db):
        create_user_role("editor-create", "Editor", "editor")
        with _client(isolated_db) as ls:
            resp = ls.post(
                "/admin/rbac/roles",
                headers={"X-API-Key": "editor-create"},
                json={"api_key": "k", "label": "L", "role": "viewer"},
            )
        assert resp.status_code == 403


class TestUpdateRoleLitestar:
    """Wave 29 — PUT /admin/rbac/roles/{id}."""

    def test_admin_updates_label_and_role(self, isolated_db):
        create_user_role("admin-update", "Admin", "admin")
        target = create_user_role("update-key", "Old", "viewer")
        with _client(isolated_db) as ls:
            resp = ls.put(
                f"/admin/rbac/roles/{target}",
                headers={"X-API-Key": "admin-update"},
                json={"label": "New", "role": "editor"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["label"] == "New"
        assert body["role"] == "editor"

    def test_unknown_role_returns_404(self, isolated_db):
        create_user_role("admin-update-2", "Admin", "admin")
        with _client(isolated_db) as ls:
            resp = ls.put(
                "/admin/rbac/roles/role-missing",
                headers={"X-API-Key": "admin-update-2"},
                json={"label": "Anything"},
            )
        assert resp.status_code == 404

    def test_invalid_role_value_returns_400(self, isolated_db):
        create_user_role("admin-update-bad", "Admin", "admin")
        target = create_user_role("upd-bad-key", "L", "viewer")
        with _client(isolated_db) as ls:
            resp = ls.put(
                f"/admin/rbac/roles/{target}",
                headers={"X-API-Key": "admin-update-bad"},
                json={"role": "godmode"},
            )
        assert resp.status_code == 400


class TestDeleteRoleLitestar:
    """Wave 30 — DELETE /admin/rbac/roles/{id}."""

    def test_admin_deletes_role(self, isolated_db):
        from app.db.rbac import get_user_role

        create_user_role("admin-del", "Admin", "admin")
        target = create_user_role("del-key", "Doomed", "viewer")
        with _client(isolated_db) as ls:
            resp = ls.delete(
                f"/admin/rbac/roles/{target}",
                headers={"X-API-Key": "admin-del"},
            )
        assert resp.status_code == 200
        assert resp.json()["message"] == "Role deleted"
        assert get_user_role(target) is None

    def test_unknown_id_returns_404(self, isolated_db):
        create_user_role("admin-del-404", "Admin", "admin")
        with _client(isolated_db) as ls:
            resp = ls.delete(
                "/admin/rbac/roles/role-missing",
                headers={"X-API-Key": "admin-del-404"},
            )
        assert resp.status_code == 404

    def test_non_admin_blocked(self, isolated_db):
        create_user_role("editor-del", "Editor", "editor")
        target = create_user_role("survives-del", "Survives", "viewer")
        with _client(isolated_db) as ls:
            resp = ls.delete(
                f"/admin/rbac/roles/{target}",
                headers={"X-API-Key": "editor-del"},
            )
        assert resp.status_code == 403


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
