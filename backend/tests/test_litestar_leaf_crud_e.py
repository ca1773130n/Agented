"""Smoke tests for the wave 69 leaf CRUD batch."""

from litestar.testing import create_test_client

from app_litestar.auth import provide_caller
from app_litestar.routes.leaf_crud_e import (
    bot_pipes_router,
    health_monitor_router,
    monitoring_router,
    onboarding_router,
    orchestration_router,
    project_instances_router,
    repo_bot_defaults_router,
)


def _client():
    return create_test_client(
        route_handlers=[
            monitoring_router,
            health_monitor_router,
            orchestration_router,
            onboarding_router,
            project_instances_router,
            repo_bot_defaults_router,
            bot_pipes_router,
        ],
        dependencies={"caller": provide_caller},
    )


# Monitoring


def test_monitoring_config(isolated_db):
    with _client() as c:
        resp = c.get("/admin/monitoring/config")
    assert resp.status_code == 200


def test_monitoring_save_config_invalid_polling(isolated_db):
    with _client() as c:
        resp = c.post(
            "/admin/monitoring/config",
            json={"polling_minutes": 7, "accounts": {}},
        )
    assert resp.status_code == 400


def test_monitoring_status(isolated_db):
    with _client() as c:
        resp = c.get("/admin/monitoring/status")
    assert resp.status_code == 200


def test_monitoring_history_requires_account(isolated_db):
    with _client() as c:
        resp = c.get("/admin/monitoring/history")
    assert resp.status_code == 400


# Health monitor


def test_health_alerts(isolated_db):
    with _client() as c:
        resp = c.get("/admin/health-monitor/alerts")
    assert resp.status_code == 200


def test_health_status(isolated_db):
    with _client() as c:
        resp = c.get("/admin/health-monitor/status")
    assert resp.status_code == 200


def test_acknowledge_unknown_alert(isolated_db):
    with _client() as c:
        resp = c.post("/admin/health-monitor/alerts/999999/acknowledge", json={})
    assert resp.status_code == 404


def test_health_report(isolated_db):
    with _client() as c:
        resp = c.get("/admin/health-monitor/report")
    assert resp.status_code == 200


# Orchestration


def test_get_chain_empty(isolated_db):
    with _client() as c:
        resp = c.get("/admin/orchestration/triggers/missing/fallback-chain")
    assert resp.status_code == 200
    assert resp.json() == {"chain": []}


def test_orchestration_health(isolated_db):
    with _client() as c:
        resp = c.get("/admin/orchestration/health")
    assert resp.status_code == 200


def test_clear_unknown_account_404(isolated_db):
    with _client() as c:
        resp = c.post(
            "/admin/orchestration/accounts/999/clear-rate-limit", json={}
        )
    assert resp.status_code == 404


def test_delete_chain_204(isolated_db):
    with _client() as c:
        resp = c.delete("/admin/orchestration/triggers/missing/fallback-chain")
    assert resp.status_code == 204


# Onboarding


def test_onboarding_config_default(isolated_db):
    with _client() as c:
        resp = c.get("/admin/onboarding/config")
    assert resp.status_code == 200


def test_save_onboarding_requires_trigger_id(isolated_db):
    with _client() as c:
        resp = c.put("/admin/onboarding/config", json={})
    assert resp.status_code == 400


def test_save_onboarding_unknown_trigger_404(isolated_db):
    with _client() as c:
        resp = c.put(
            "/admin/onboarding/config",
            json={"trigger_id": "missing", "steps": []},
        )
    assert resp.status_code == 404


def test_onboarding_runs_default(isolated_db):
    with _client() as c:
        resp = c.get("/admin/onboarding/runs")
    assert resp.status_code == 200


# Project instances


def test_create_instance_unknown_project_404(isolated_db):
    with _client() as c:
        resp = c.post("/admin/projects/missing/instances", json={"team_id": "t-x"})
    assert resp.status_code == 404


def test_list_instances_empty(isolated_db):
    with _client() as c:
        resp = c.get("/admin/projects/missing/instances")
    assert resp.status_code == 200


def test_get_unknown_instance_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/projects/missing/instances/missing")
    assert resp.status_code == 404


def test_delete_unknown_instance_404(isolated_db):
    with _client() as c:
        resp = c.delete("/admin/projects/missing/instances/missing")
    assert resp.status_code == 404


# Repo bot defaults


def test_list_repo_defaults(isolated_db):
    with _client() as c:
        resp = c.get("/admin/repo-bot-defaults/")
    assert resp.status_code == 200


def test_create_repo_default_requires_repo(isolated_db):
    with _client() as c:
        resp = c.post("/admin/repo-bot-defaults/", json={})
    assert resp.status_code == 400


def test_toggle_repo_default_requires_enabled(isolated_db):
    with _client() as c:
        resp = c.put("/admin/repo-bot-defaults/owner__repo", json={})
    assert resp.status_code == 400


def test_delete_repo_default_no_match_404(isolated_db):
    with _client() as c:
        resp = c.delete("/admin/repo-bot-defaults/missing__repo")
    assert resp.status_code == 404


# Bot pipes


def test_list_bot_pipes(isolated_db):
    with _client() as c:
        resp = c.get("/admin/bot-pipes/")
    assert resp.status_code == 200


def test_create_pipe_requires_fields(isolated_db):
    with _client() as c:
        resp = c.post("/admin/bot-pipes/", json={"name": "x"})
    assert resp.status_code == 400


def test_patch_unknown_pipe_404(isolated_db):
    with _client() as c:
        resp = c.patch("/admin/bot-pipes/missing", json={"enabled": False})
    assert resp.status_code == 404


def test_list_pipe_executions(isolated_db):
    with _client() as c:
        resp = c.get("/admin/bot-pipes/executions")
    assert resp.status_code == 200
