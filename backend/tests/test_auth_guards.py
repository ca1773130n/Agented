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

    def test_health_is_public(self):
        from app_litestar.auth_guards import required_role
        assert required_role("GET", "/health/liveness") is None

    def test_login_endpoint_is_public(self):
        from app_litestar.auth_guards import required_role
        assert required_role("POST", "/admin/auth/login") is None

    def test_unmapped_paths_default_public(self):
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
