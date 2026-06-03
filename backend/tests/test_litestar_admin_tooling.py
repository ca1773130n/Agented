"""Smoke tests for the wave 64 batch."""

from litestar.testing import create_test_client

from app_litestar.routes.admin_tooling import (
    gitops_router,
    secrets_router,
    settings_router,
    system_router,
    version_pins_router,
)
from app_litestar.routes.retention import retention_router


def _client():
    return create_test_client(
        route_handlers=[
            settings_router,
            system_router,
            secrets_router,
            gitops_router,
            version_pins_router,
            retention_router,
        ],
    )


# Settings
def test_list_settings(isolated_db):
    with _client() as c:
        resp = c.get("/api/settings/")
    assert resp.status_code == 200


def test_get_unset_setting_returns_empty(isolated_db):
    with _client() as c:
        resp = c.get("/api/settings/missing-key")
    assert resp.status_code == 200
    assert resp.json() == {"key": "missing-key", "value": ""}


def test_set_and_get_setting(isolated_db):
    with _client() as c:
        c.put("/api/settings/foo", json={"value": "bar"})
        resp = c.get("/api/settings/foo")
    assert resp.json() == {"key": "foo", "value": "bar"}


def test_delete_unknown_setting_404(isolated_db):
    with _client() as c:
        resp = c.delete("/api/settings/missing-key")
    assert resp.status_code == 404


def test_set_setting_requires_value(isolated_db):
    with _client() as c:
        resp = c.put("/api/settings/foo", json={})
    assert resp.status_code == 400


def test_harness_plugin_get(isolated_db):
    with _client() as c:
        resp = c.get("/api/settings/harness-plugin")
    assert resp.status_code == 200
    body = resp.json()
    assert "plugin_id" in body


def test_sensitive_setting_value_is_redacted(isolated_db):
    # H4: a viewer can read settings; credential-like values must be redacted.
    with _client() as c:
        c.put("/api/settings/github_api_token", json={"value": "ghp_supersecret"})
        single = c.get("/api/settings/github_api_token").json()
        listing = c.get("/api/settings/").json()["settings"]
    assert single["value"] != "ghp_supersecret"
    assert single["value"]  # redacted placeholder, not empty
    assert listing.get("github_api_token") != "ghp_supersecret"


def test_non_sensitive_setting_value_passthrough(isolated_db):
    with _client() as c:
        c.put("/api/settings/theme", json={"value": "dark"})
        single = c.get("/api/settings/theme").json()
    assert single["value"] == "dark"


# System
def test_list_errors(isolated_db):
    with _client() as c:
        resp = c.get("/admin/system/errors")
    assert resp.status_code == 200


def test_error_counts(isolated_db):
    with _client() as c:
        resp = c.get("/admin/system/errors/counts")
    assert resp.status_code == 200


def test_unknown_error_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/system/errors/missing-id")
    assert resp.status_code == 404


def test_logs_endpoint(isolated_db):
    with _client() as c:
        resp = c.get("/admin/system/logs")
    assert resp.status_code == 200
    assert "lines" in resp.json()


# Secrets (vault probably not configured in test → 503).
# The secrets router is admin-gated (C1), and explicit guards aren't weakened by
# bootstrap, so these go through ApiKeyMiddleware with a seeded admin key.
def _admin_secrets_client():
    from app_litestar.middleware import ApiKeyMiddleware

    return create_test_client(
        route_handlers=[secrets_router], middleware=[ApiKeyMiddleware()]
    )


def _seed_admin_key(email: str = "vaultadmin@test") -> str:
    from app.database import get_connection
    from app.db.rbac import create_user_role, generate_api_key

    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, email, password_hash, created_at) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (email, email, "x"),
        )
        conn.commit()
    api_key = generate_api_key()
    assert create_user_role(api_key, label="t", role="admin", user_id=email) is not None
    return api_key


def test_vault_status(isolated_db):
    key = _seed_admin_key()
    with _admin_secrets_client() as c:
        resp = c.get("/admin/secrets/status", headers={"X-API-Key": key})
    assert resp.status_code == 200
    body = resp.json()
    assert "configured" in body


def test_list_secrets_without_vault_503(isolated_db):
    key = _seed_admin_key()
    with _admin_secrets_client() as c:
        resp = c.get("/admin/secrets/", headers={"X-API-Key": key})
    # Either 503 (vault not configured) or 200 (vault wired in conftest)
    assert resp.status_code in (200, 503)


# GitOps
def test_list_gitops_repos(isolated_db):
    with _client() as c:
        resp = c.get("/admin/gitops/repos")
    assert resp.status_code == 200


def test_unknown_gitops_repo_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/gitops/repos/missing-id")
    assert resp.status_code == 404


# Version pins
def test_list_version_pins(isolated_db):
    with _client() as c:
        resp = c.get("/admin/version-pins/")
    assert resp.status_code == 200
    assert "pins" in resp.json()


def test_unknown_pin_unpin_404(isolated_db):
    with _client() as c:
        resp = c.post("/admin/version-pins/missing-id/unpin")
    assert resp.status_code == 404


# Retention
def test_list_retention_policies(isolated_db):
    with _client() as c:
        resp = c.get("/admin/retention-policies/")
    assert resp.status_code == 200
    assert "policies" in resp.json()


def test_toggle_retention_unknown_404(isolated_db):
    with _client() as c:
        resp = c.patch(
            "/admin/retention-policies/missing-id/toggle",
            json={"enabled": True},
        )
    assert resp.status_code == 404


def test_run_cleanup(isolated_db):
    with _client() as c:
        resp = c.post("/admin/retention-policies/cleanup")
    # PR-R (wave 83): cleanup is now synchronous-acknowledge (returns immediately
    # with a "queued — enforcement deferred" message). Litestar's default success
    # status for @post is 201 — accept either 200/201/202 since semantically the
    # contract is "ack received".
    assert resp.status_code in (200, 201, 202)
    assert "message" in resp.json()
