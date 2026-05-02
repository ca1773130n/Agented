"""Smoke tests for the wave 73 leaf CRUD batch."""

from litestar.testing import create_test_client

from app_litestar.auth import provide_caller
from app_litestar.routes.leaf_crud_h import (
    backends_router,
    utility_leftover_router,
)


def _client():
    return create_test_client(
        route_handlers=[utility_leftover_router, backends_router],
        dependencies={"caller": provide_caller},
    )


# Utility


def test_validate_github_url_requires_url(isolated_db):
    with _client() as c:
        resp = c.get("/api/validate-github-url")
    assert resp.status_code == 400


def test_validate_github_url_invalid(isolated_db):
    with _client() as c:
        resp = c.get("/api/validate-github-url?url=not-a-url")
    assert resp.status_code == 200
    assert resp.json()["valid"] is False


def test_resolve_issues_requires_summary(isolated_db):
    with _client() as c:
        resp = c.post("/api/resolve-issues", json={})
    assert resp.status_code == 400


def test_resolve_issues_requires_paths(isolated_db):
    with _client() as c:
        resp = c.post(
            "/api/resolve-issues",
            json={"audit_summary": "x"},
        )
    assert resp.status_code == 400


def test_discover_skills_unknown_trigger_404(isolated_db):
    with _client() as c:
        resp = c.get("/api/discover-skills?trigger_id=missing")
    assert resp.status_code == 404


def test_browse_directory_outside_allowed_403(isolated_db):
    with _client() as c:
        resp = c.get("/api/browse-directory?path=/etc")
    assert resp.status_code == 403


def test_create_directory_requires_path(isolated_db):
    with _client() as c:
        resp = c.post("/api/create-directory", json={})
    assert resp.status_code == 400


def test_create_directory_relative_400(isolated_db):
    with _client() as c:
        resp = c.post("/api/create-directory", json={"path": "relative/path"})
    assert resp.status_code == 400


# Backends


def test_unknown_session_respond_404(isolated_db):
    with _client() as c:
        resp = c.post(
            "/admin/backends/claude/connect/missing/respond",
            json={"interaction_id": "x", "response": "y"},
        )
    assert resp.status_code == 404


def test_unknown_session_cancel_404(isolated_db):
    with _client() as c:
        resp = c.delete("/admin/backends/claude/connect/missing")
    assert resp.status_code == 404


def test_proxy_callback_forward_requires_url(isolated_db):
    with _client() as c:
        resp = c.post("/admin/backends/proxy/callback-forward", json={})
    assert resp.status_code == 400


def test_proxy_callback_forward_no_code(isolated_db):
    with _client() as c:
        resp = c.post(
            "/admin/backends/proxy/callback-forward",
            json={"callback_url": "http://localhost:8085/callback"},
        )
    assert resp.status_code == 400


def test_gemini_auth_complete_requires_code(isolated_db):
    with _client() as c:
        resp = c.post("/admin/backends/gemini/auth-complete", json={})
    assert resp.status_code == 400


def test_gemini_auth_complete_invalid_state(isolated_db):
    with _client() as c:
        resp = c.post(
            "/admin/backends/gemini/auth-complete",
            json={"code": "abc", "state": "missing"},
        )
    assert resp.status_code == 400


def test_proxy_status(isolated_db):
    with _client() as c:
        resp = c.get("/admin/backends/proxy/status")
    assert resp.status_code == 200


def test_proxy_accounts_list(isolated_db):
    with _client() as c:
        resp = c.get("/admin/backends/proxy/accounts")
    assert resp.status_code == 200
