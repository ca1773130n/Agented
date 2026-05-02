"""Smoke tests for the wave 64 batch."""

from litestar.testing import create_test_client

from app_litestar.routes.admin_tooling import (
    gitops_router,
    retention_router,
    secrets_router,
    settings_router,
    system_router,
    version_pins_router,
)


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


# Secrets (vault probably not configured in test → 503)
def test_vault_status(isolated_db):
    with _client() as c:
        resp = c.get("/admin/secrets/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "configured" in body


def test_list_secrets_without_vault_503(isolated_db):
    with _client() as c:
        resp = c.get("/admin/secrets/")
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
    assert resp.status_code == 202
