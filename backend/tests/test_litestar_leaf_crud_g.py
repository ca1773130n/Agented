"""Smoke tests for the wave 71 leaf CRUD batch."""

from litestar.testing import create_test_client

from app_litestar.auth import provide_caller
from app_litestar.routes.leaf_crud_g import (
    agent_conversations_router,
    plugin_exports_router,
    sketches_router,
)


def _client():
    return create_test_client(
        route_handlers=[
            sketches_router,
            agent_conversations_router,
            plugin_exports_router,
        ],
        dependencies={"caller": provide_caller},
    )


# Sketches


def test_list_sketches(isolated_db):
    with _client() as c:
        resp = c.get("/admin/sketches/")
    assert resp.status_code == 200


def test_create_sketch_requires_title(isolated_db):
    with _client() as c:
        resp = c.post("/admin/sketches/", json={})
    assert resp.status_code == 400


def test_unknown_sketch_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/sketches/missing")
    assert resp.status_code == 404


def test_update_unknown_sketch_404(isolated_db):
    with _client() as c:
        resp = c.put("/admin/sketches/missing", json={"title": "x"})
    assert resp.status_code == 404


def test_classify_unknown_sketch_404(isolated_db):
    with _client() as c:
        resp = c.post("/admin/sketches/missing/classify", json={})
    assert resp.status_code == 404


def test_route_unknown_sketch_404(isolated_db):
    with _client() as c:
        resp = c.post("/admin/sketches/missing/route", json={})
    assert resp.status_code == 404


def test_delegations_unknown_sketch_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/sketches/missing/delegations")
    assert resp.status_code == 404


# Agent conversations (CRUD only)


def test_send_message_requires_message(isolated_db):
    with _client() as c:
        resp = c.post(
            "/api/agents/conversations/conv-x/message", json={}
        )
    assert resp.status_code == 400


# Plugin exports


def test_export_requires_team(isolated_db):
    with _client() as c:
        resp = c.post("/admin/plugin-exports/export", json={})
    assert resp.status_code == 400


def test_export_invalid_format(isolated_db):
    with _client() as c:
        resp = c.post(
            "/admin/plugin-exports/export",
            json={"team_id": "t-x", "export_format": "tar"},
        )
    assert resp.status_code == 400


def test_import_requires_source(isolated_db):
    with _client() as c:
        resp = c.post("/admin/plugin-exports/import", json={})
    assert resp.status_code == 400


def test_import_marketplace_requires_id(isolated_db):
    with _client() as c:
        resp = c.post(
            "/admin/plugin-exports/import-from-marketplace", json={}
        )
    assert resp.status_code == 400


def test_deploy_requires_plugin(isolated_db):
    with _client() as c:
        resp = c.post("/admin/plugin-exports/deploy", json={})
    assert resp.status_code == 400


def test_test_connection_requires_marketplace(isolated_db):
    with _client() as c:
        resp = c.post("/admin/plugin-exports/test-connection", json={})
    assert resp.status_code == 400


def test_list_plugin_exports_empty(isolated_db):
    with _client() as c:
        resp = c.get("/admin/plugin-exports/p-x/exports")
    assert resp.status_code == 200


def test_sync_requires_fields(isolated_db):
    with _client() as c:
        resp = c.post("/admin/plugin-exports/sync", json={})
    assert resp.status_code == 400


def test_sync_entity_requires_fields(isolated_db):
    with _client() as c:
        resp = c.post("/admin/plugin-exports/sync/entity", json={})
    assert resp.status_code == 400


def test_watch_requires_plugin(isolated_db):
    with _client() as c:
        resp = c.post("/admin/plugin-exports/watch", json={})
    assert resp.status_code == 400
