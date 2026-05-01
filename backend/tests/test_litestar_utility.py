"""Tests for the Litestar utility routes (wave 45)."""

from litestar.testing import create_test_client

from app_litestar.routes.utility import utility_router


def _client():
    return create_test_client(route_handlers=[utility_router])


class TestVersion:
    def test_returns_some_version_string(self, isolated_db):
        with _client() as c:
            resp = c.get("/api/version")
        assert resp.status_code == 200
        body = resp.json()
        assert "version" in body
        assert isinstance(body["version"], str)


class TestCheckBackend:
    def test_invalid_backend_400(self, isolated_db):
        with _client() as c:
            resp = c.get("/api/check-backend?backend=ghost")
        assert resp.status_code == 400

    def test_known_backend_returns_install_info(self, isolated_db):
        with _client() as c:
            resp = c.get("/api/check-backend?backend=claude")
        assert resp.status_code == 200
        body = resp.json()
        assert body["backend"] == "claude"
        assert "installed" in body and "version" in body and "path" in body


class TestValidatePath:
    def test_missing_path_400(self, isolated_db):
        with _client() as c:
            resp = c.get("/api/validate-path?path=")
        assert resp.status_code == 400

    def test_disallowed_path_returns_error_field(self, isolated_db):
        with _client() as c:
            resp = c.get("/api/validate-path?path=/etc")
        body = resp.json()
        # Either 200 with error field (current behavior) or any 4xx status —
        # both are valid no-list-system-paths outcomes.
        assert "error" in body or resp.status_code >= 400

    def test_home_dir_resolves(self, isolated_db, tmp_path):
        with _client() as c:
            resp = c.get(f"/api/validate-path?path={str(tmp_path)}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["exists"] is True
        assert body["is_directory"] is True
