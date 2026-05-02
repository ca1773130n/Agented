"""Smoke tests for the wave 61 batch (rules + plugins + hooks + commands)."""

from litestar.testing import create_test_client

from app.db.rbac import create_user_role
from app_litestar.auth import provide_caller
from app_litestar.routes.rules_plugins_hooks_commands import (
    commands_router,
    hooks_router,
    plugins_router,
    rules_router,
)


def _client():
    return create_test_client(
        route_handlers=[rules_router, plugins_router, hooks_router, commands_router],
        dependencies={"caller": provide_caller},
    )


# Rules
def test_list_rules(isolated_db):
    with _client() as c:
        resp = c.get("/admin/rules/")
    assert resp.status_code == 200


def test_rule_types(isolated_db):
    with _client() as c:
        resp = c.get("/admin/rules/types")
    assert resp.status_code == 200
    assert "types" in resp.json()


def test_unknown_rule_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/rules/9999")
    assert resp.status_code == 404


def test_invalid_rule_type_400(isolated_db):
    with _client() as c:
        resp = c.get("/admin/rules/type/not-a-type")
    assert resp.status_code == 400


# Plugins
def test_list_plugins(isolated_db):
    with _client() as c:
        resp = c.get("/admin/plugins/")
    assert resp.status_code == 200


def test_unknown_plugin_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/plugins/missing-id")
    assert resp.status_code == 404


def test_create_plugin_requires_body(isolated_db):
    with _client() as c:
        resp = c.post("/admin/plugins/", json={})
    assert resp.status_code == 400


# Hooks
def test_list_hooks(isolated_db):
    with _client() as c:
        resp = c.get("/admin/hooks/")
    assert resp.status_code == 200


def test_hook_events(isolated_db):
    with _client() as c:
        resp = c.get("/admin/hooks/events")
    assert resp.status_code == 200
    assert "events" in resp.json()


def test_unknown_hook_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/hooks/9999")
    assert resp.status_code == 404


def test_list_hooks_by_event(isolated_db):
    with _client() as c:
        resp = c.get("/admin/hooks/event/PreToolUse")
    assert resp.status_code == 200


# Commands
def test_list_commands(isolated_db):
    with _client() as c:
        resp = c.get("/admin/commands/")
    assert resp.status_code == 200


def test_unknown_command_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/commands/9999")
    assert resp.status_code == 404


def test_list_project_commands(isolated_db):
    with _client() as c:
        resp = c.get("/admin/commands/project/proj-x")
    assert resp.status_code == 200
