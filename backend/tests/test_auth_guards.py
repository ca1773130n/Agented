"""v0.5.12: auth_guards — coarse role table + per-route guard factory."""

import pytest


class TestRequiresRoleConstruction:
    def test_rejects_unknown_role_at_construction(self):
        from app_litestar.auth_guards import requires_role

        with pytest.raises(ValueError, match="unknown role"):
            requires_role("Admin")  # capital A — typo


class TestRequiredRole:
    def test_get_admin_requires_viewer(self):
        from app_litestar.auth_guards import required_role

        assert required_role("GET", "/admin/agents") == "viewer"

    def test_post_admin_requires_editor(self):
        from app_litestar.auth_guards import required_role

        assert required_role("POST", "/admin/agents") == "editor"

    def test_delete_admin_requires_admin(self):
        from app_litestar.auth_guards import required_role

        assert required_role("DELETE", "/admin/agents/x") == "admin"

    def test_get_api_requires_viewer(self):
        from app_litestar.auth_guards import required_role

        assert required_role("GET", "/api/foo") == "viewer"

    def test_post_api_requires_editor(self):
        """v0.5.12 fix: mutating /api/* must require at least editor."""
        from app_litestar.auth_guards import required_role

        assert required_role("POST", "/api/projects/p1/phases") == "editor"

    def test_put_api_requires_editor(self):
        from app_litestar.auth_guards import required_role

        assert required_role("PUT", "/api/settings/harness-plugin") == "editor"

    def test_patch_api_requires_editor(self):
        from app_litestar.auth_guards import required_role

        assert required_role("PATCH", "/api/agents/a1") == "editor"

    def test_delete_api_requires_admin(self):
        from app_litestar.auth_guards import required_role

        assert required_role("DELETE", "/api/agents/a1") == "admin"

    def test_health_is_public(self):
        from app_litestar.auth_guards import required_role

        assert required_role("GET", "/health/liveness") is None

    def test_logout_endpoints_are_public(self):
        """Logout must bypass the coarse role check so any authenticated
        principal (including viewer) can end their session."""
        from app_litestar.auth_guards import PUBLIC_PATHS, required_role

        assert "/admin/auth/logout" in PUBLIC_PATHS
        assert "/api/auth/logout" in PUBLIC_PATHS
        assert required_role("POST", "/admin/auth/logout") is None
        assert required_role("POST", "/api/auth/logout") is None

    def test_unmapped_paths_default_public(self):
        """Paths outside /api/ and /admin/ have no coarse rule (auth still
        enforced by middleware where applicable)."""
        from app_litestar.auth_guards import required_role

        assert required_role("GET", "/some/random/path") is None


class TestRoleRank:
    def test_admin_outranks_editor(self):
        from app_litestar.auth_guards import ROLE_RANK

        assert ROLE_RANK["admin"] > ROLE_RANK["editor"]

    def test_editor_outranks_operator(self):
        from app_litestar.auth_guards import ROLE_RANK

        assert ROLE_RANK["editor"] > ROLE_RANK["operator"]

    def test_operator_outranks_viewer(self):
        from app_litestar.auth_guards import ROLE_RANK

        assert ROLE_RANK["operator"] > ROLE_RANK["viewer"]
