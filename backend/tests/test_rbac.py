"""Tests for RBAC (Role-Based Access Control) system.

Covers:
- Permission matrix (4 roles x 4 permissions = 16 combinations)
- @require_role() decorator enforcement
- Graceful bootstrap (no roles configured)
- Audit logging on RBAC denial
- DB CRUD operations for user roles
"""

from app.db.rbac import (
    count_user_roles,
    create_user_role,
    delete_user_role,
    get_role_for_api_key,
    get_user_role,
    list_user_roles,
    update_user_role,
)
from app.services.audit_log_service import AuditLogService
from app.services.rbac_service import (
    ROLE_PERMISSIONS,
    has_permission,
)

# =============================================================================
# Permission matrix tests (16 combinations)
# =============================================================================


class TestPermissionMatrix:
    """Verify the RBAC permission matrix maps roles to correct permissions."""

    def test_viewer_permissions(self):
        assert ROLE_PERMISSIONS["viewer"] == {"read"}

    def test_operator_permissions(self):
        assert ROLE_PERMISSIONS["operator"] == {"read", "execute"}

    def test_editor_permissions(self):
        assert ROLE_PERMISSIONS["editor"] == {"read", "execute", "edit"}

    def test_admin_permissions(self):
        assert ROLE_PERMISSIONS["admin"] == {"read", "execute", "edit", "manage"}

    def test_viewer_cannot_execute(self):
        assert "execute" not in ROLE_PERMISSIONS["viewer"]

    def test_viewer_cannot_edit(self):
        assert "edit" not in ROLE_PERMISSIONS["viewer"]

    def test_viewer_cannot_manage(self):
        assert "manage" not in ROLE_PERMISSIONS["viewer"]

    def test_operator_cannot_edit(self):
        assert "edit" not in ROLE_PERMISSIONS["operator"]

    def test_operator_cannot_manage(self):
        assert "manage" not in ROLE_PERMISSIONS["operator"]

    def test_editor_cannot_manage(self):
        assert "manage" not in ROLE_PERMISSIONS["editor"]


# =============================================================================
# DB CRUD tests
# =============================================================================


class TestUserRoleCRUD:
    """Test user_roles database operations."""

    def test_create_and_get_role(self, isolated_db):
        role_id = create_user_role("key-admin-1", "Admin Key", "admin")
        assert role_id is not None
        assert role_id.startswith("role-")

        role = get_user_role(role_id)
        assert role is not None
        assert role["api_key"] == "key-admin-1"
        assert role["label"] == "Admin Key"
        assert role["role"] == "admin"

    def test_get_role_for_api_key(self, isolated_db):
        create_user_role("key-viewer-1", "Viewer Key", "viewer")
        assert get_role_for_api_key("key-viewer-1") == "viewer"

    def test_get_role_for_unknown_key(self, isolated_db):
        assert get_role_for_api_key("nonexistent-key") is None

    def test_list_user_roles(self, isolated_db):
        create_user_role("key-a", "A", "viewer")
        create_user_role("key-b", "B", "admin")
        roles = list_user_roles()
        assert len(roles) == 2

    def test_update_user_role(self, isolated_db):
        role_id = create_user_role("key-up", "Old Label", "viewer")
        assert update_user_role(role_id, label="New Label", role="editor")
        role = get_user_role(role_id)
        assert role["label"] == "New Label"
        assert role["role"] == "editor"

    def test_update_invalid_role_rejected(self, isolated_db):
        role_id = create_user_role("key-inv", "Test", "viewer")
        assert not update_user_role(role_id, role="superadmin")

    def test_delete_user_role(self, isolated_db):
        role_id = create_user_role("key-del", "Delete Me", "viewer")
        assert delete_user_role(role_id)
        assert get_user_role(role_id) is None

    def test_create_duplicate_api_key_fails(self, isolated_db):
        create_user_role("key-dup", "First", "viewer")
        result = create_user_role("key-dup", "Second", "admin")
        assert result is None

    def test_create_invalid_role_fails(self, isolated_db):
        result = create_user_role("key-bad", "Bad", "superadmin")
        assert result is None

    def test_count_user_roles(self, isolated_db):
        assert count_user_roles() == 0
        create_user_role("key-c1", "C1", "viewer")
        assert count_user_roles() == 1
        create_user_role("key-c2", "C2", "admin")
        assert count_user_roles() == 2


# =============================================================================
# has_permission tests
# =============================================================================


class TestHasPermission:
    """Test the has_permission utility function."""

    def test_admin_has_manage(self, isolated_db):
        create_user_role("key-hp-admin", "Admin", "admin")
        assert has_permission("key-hp-admin", "manage") is True

    def test_viewer_no_execute(self, isolated_db):
        create_user_role("key-hp-viewer", "Viewer", "viewer")
        assert has_permission("key-hp-viewer", "execute") is False

    def test_unknown_key_no_permission(self, isolated_db):
        assert has_permission("unknown-key", "read") is False

    def test_editor_has_edit(self, isolated_db):
        create_user_role("key-hp-editor", "Editor", "editor")
        assert has_permission("key-hp-editor", "edit") is True

    def test_operator_has_execute(self, isolated_db):
        create_user_role("key-hp-op", "Operator", "operator")
        assert has_permission("key-hp-op", "execute") is True


# =============================================================================
# @require_role decorator tests (using Flask test client)
# =============================================================================


class TestRequireRoleDecorator:
    """Test the @require_role() decorator with Flask test client."""

    def test_decorator_blocks_unauthorized_role(self, client, isolated_db):
        """Viewer cannot access admin-only endpoint."""
        create_user_role("key-viewer-dec", "Viewer", "viewer")
        # RBAC routes require admin -- try to list roles as viewer
        resp = client.get(
            "/admin/rbac/roles",
            headers={"X-API-Key": "key-viewer-dec"},
        )
        assert resp.status_code == 403

    def test_decorator_allows_authorized_role(self, client, isolated_db):
        """Admin can access admin-only endpoint."""
        create_user_role("key-admin-dec", "Admin", "admin")
        resp = client.get(
            "/admin/rbac/roles",
            headers={"X-API-Key": "key-admin-dec"},
        )
        assert resp.status_code == 200

    def test_decorator_missing_api_key_returns_403(self, client, isolated_db):
        """Missing API key returns 403 when RBAC is active."""
        create_user_role("key-active", "Active", "admin")
        resp = client.get("/admin/rbac/roles")
        assert resp.status_code == 403

    def test_decorator_invalid_api_key_returns_403(self, client, isolated_db):
        """Unknown API key returns 403."""
        create_user_role("key-known", "Known", "admin")
        resp = client.get(
            "/admin/rbac/roles",
            headers={"X-API-Key": "key-unknown-xyz"},
        )
        assert resp.status_code == 403

    def test_graceful_bootstrap_no_roles(self, client, isolated_db):
        """When no roles exist in DB, all requests pass through (bootstrap mode)."""
        assert count_user_roles() == 0
        resp = client.get("/admin/rbac/roles")
        assert resp.status_code == 200

    def test_audit_log_on_denial(self, client, isolated_db):
        """RBAC denial creates an audit log entry."""
        create_user_role("key-audit-test", "Viewer", "viewer")

        # Record count before denial
        from app.services.audit_log_service import _recent_events

        len(_recent_events)

        client.get(
            "/admin/rbac/roles",
            headers={"X-API-Key": "key-audit-test"},
        )

        # Check that a new audit event was logged
        events = AuditLogService.get_recent_events(limit=50)
        rbac_events = [e for e in events if e.get("action") == "rbac.denied"]
        assert len(rbac_events) > 0
        assert rbac_events[0]["outcome"] == "denied"


# =============================================================================
# Integration tests: RBAC on existing trigger/team routes
# =============================================================================


class TestRBACOnTriggerRoutes:
    """Test RBAC enforcement on existing trigger management routes."""

    def test_viewer_cannot_create_trigger(self, client, isolated_db):
        """Viewer blocked from POST /admin/triggers/."""
        create_user_role("key-trig-viewer", "Viewer", "viewer")
        resp = client.post(
            "/admin/triggers/",
            json={"name": "test", "prompt_template": "test"},
            headers={"X-API-Key": "key-trig-viewer"},
        )
        assert resp.status_code == 403

    def test_operator_cannot_update_trigger(self, client, isolated_db):
        """Operator blocked from PUT /admin/triggers/<id>."""
        create_user_role("key-trig-op", "Operator", "operator")
        resp = client.put(
            "/admin/triggers/trig-abc123",
            json={"name": "updated"},
            headers={"X-API-Key": "key-trig-op"},
        )
        assert resp.status_code == 403

    def test_editor_can_create_trigger(self, client, isolated_db):
        """Editor can POST /admin/triggers/."""
        create_user_role("key-trig-editor", "Editor", "editor")
        resp = client.post(
            "/admin/triggers/",
            json={"name": "test-trigger", "prompt_template": "test prompt"},
            headers={"X-API-Key": "key-trig-editor"},
        )
        # Should not be 403 -- might be 201 or 400 depending on validation
        assert resp.status_code != 403

    def test_viewer_can_list_triggers(self, client, isolated_db):
        """Viewer can GET /admin/triggers/."""
        create_user_role("key-trig-viewer-list", "Viewer", "viewer")
        resp = client.get(
            "/admin/triggers/",
            headers={"X-API-Key": "key-trig-viewer-list"},
        )
        assert resp.status_code == 200

    def test_viewer_cannot_delete_trigger(self, client, isolated_db):
        """Viewer blocked from DELETE /admin/triggers/<id>."""
        create_user_role("key-trig-viewer-del", "Viewer", "viewer")
        resp = client.delete(
            "/admin/triggers/trig-abc123",
            headers={"X-API-Key": "key-trig-viewer-del"},
        )
        assert resp.status_code == 403

    def test_viewer_cannot_run_trigger(self, client, isolated_db):
        """Viewer blocked from POST /admin/triggers/<id>/run (requires operator+)."""
        create_user_role("key-trig-viewer-run", "Viewer", "viewer")
        resp = client.post(
            "/admin/triggers/bot-security/run",
            json={},
            headers={"X-API-Key": "key-trig-viewer-run"},
        )
        assert resp.status_code == 403

    def test_no_roles_allows_all(self, client, isolated_db):
        """When no roles exist (bootstrap mode), all requests pass through."""
        assert count_user_roles() == 0
        resp = client.get("/admin/triggers/")
        assert resp.status_code == 200
        resp = client.post(
            "/admin/triggers/",
            json={"name": "test", "prompt_template": "test"},
        )
        # Should not be 403 in bootstrap mode
        assert resp.status_code != 403


class TestGenerateApiKey:
    """Tests for API key generation."""

    def test_generate_api_key_returns_64_hex_chars(self):
        from app.db.rbac import generate_api_key

        key = generate_api_key()
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_generate_api_key_unique(self):
        from app.db.rbac import generate_api_key

        keys = {generate_api_key() for _ in range(100)}
        assert len(keys) == 100


class TestHasAnyKeys:
    """Tests for cached has_any_keys check."""

    def test_false_when_empty(self, isolated_db):
        from app.db.rbac import _has_any_keys_cache, has_any_keys

        _has_any_keys_cache.clear()
        assert has_any_keys() is False

    def test_true_after_create(self, isolated_db):
        from app.db.rbac import _has_any_keys_cache, has_any_keys

        _has_any_keys_cache.clear()
        create_user_role("k1", "Admin", "admin")
        _has_any_keys_cache.clear()
        assert has_any_keys() is True


class TestRBACOnTeamRoutes:
    """Test RBAC enforcement on existing team management routes."""

    def test_viewer_cannot_create_team(self, client, isolated_db):
        """Viewer blocked from POST /admin/teams/."""
        create_user_role("key-team-viewer", "Viewer", "viewer")
        resp = client.post(
            "/admin/teams/",
            json={"name": "Test Team"},
            headers={"X-API-Key": "key-team-viewer"},
        )
        assert resp.status_code == 403

    def test_editor_cannot_delete_team(self, client, isolated_db):
        """Editor blocked from DELETE /admin/teams/<id> (admin only)."""
        create_user_role("key-team-editor", "Editor", "editor")
        resp = client.delete(
            "/admin/teams/team-abc123",
            headers={"X-API-Key": "key-team-editor"},
        )
        assert resp.status_code == 403

    def test_editor_can_update_team(self, client, isolated_db):
        """Editor can PUT /admin/teams/<id>."""
        create_user_role("key-team-editor-up", "Editor", "editor")
        resp = client.put(
            "/admin/teams/team-abc123",
            json={"name": "Updated"},
            headers={"X-API-Key": "key-team-editor-up"},
        )
        # Not 403 -- might be 404 if team doesn't exist
        assert resp.status_code != 403

    def test_viewer_can_list_teams(self, client, isolated_db):
        """Viewer can GET /admin/teams/."""
        create_user_role("key-team-viewer-list", "Viewer", "viewer")
        resp = client.get(
            "/admin/teams/",
            headers={"X-API-Key": "key-team-viewer-list"},
        )
        assert resp.status_code == 200

    def test_editor_cannot_manage_members(self, client, isolated_db):
        """Editor blocked from POST /admin/teams/<id>/members (admin only)."""
        create_user_role("key-team-editor-mem", "Editor", "editor")
        resp = client.post(
            "/admin/teams/team-abc123/members",
            json={"name": "New Member"},
            headers={"X-API-Key": "key-team-editor-mem"},
        )
        assert resp.status_code == 403

    def test_admin_can_manage_members(self, client, isolated_db):
        """Admin can POST /admin/teams/<id>/members."""
        create_user_role("key-team-admin", "Admin", "admin")
        resp = client.post(
            "/admin/teams/team-abc123/members",
            json={"name": "New Member"},
            headers={"X-API-Key": "key-team-admin"},
        )
        # Not 403 -- might be 500 if team doesn't exist, that's fine
        assert resp.status_code != 403
