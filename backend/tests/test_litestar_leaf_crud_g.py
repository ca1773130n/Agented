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


def test_route_forwards_use_cli_agent_override(isolated_db, monkeypatch):
    """`use_cli_agent` in the request body must reach `execute_sketch`.

    Pins the AiChatPanel toggle's plumbing: when the panel flips its
    CLI-runner toggle, the next ``POST /admin/sketches/{id}/route``
    carries that value, which then drives whether ``run_streaming_response``
    uses the CLI agent runner or the legacy CLIProxy path. We stub
    classification + routing + execution so the test pins the wiring,
    not provider/model behavior.
    """
    import json as _json

    from app.db.sketches import create_sketch, update_sketch
    from app_litestar.routes import leaf_crud_g

    sketch_id = create_sketch(title="t", content="c")
    update_sketch(
        sketch_id,
        classification_json=_json.dumps({"phase": "build"}),
        status="classified",
    )

    monkeypatch.setattr(
        "app.services.sketch_routing_service.SketchRoutingService.route",
        lambda _classification, project_id=None: {
            "target_type": "super_agent",
            "target_id": "sa-x",
            "reason": "test",
        },
    )

    captured: dict = {}

    def _fake_execute(sketch_id, super_agent_id, content, team_id=None, use_cli_agent=None):
        captured["use_cli_agent"] = use_cli_agent
        captured["sketch_id"] = sketch_id
        return "sess-x"

    monkeypatch.setattr(leaf_crud_g, "execute_sketch", _fake_execute)

    with _client() as c:
        resp = c.post(
            f"/admin/sketches/{sketch_id}/route",
            json={"use_cli_agent": False},
        )
    assert resp.status_code == 201, resp.text
    assert captured["use_cli_agent"] is False
    assert captured["sketch_id"] == sketch_id

    captured.clear()
    with _client() as c:
        resp = c.post(
            f"/admin/sketches/{sketch_id}/route",
            json={"use_cli_agent": True},
        )
    assert captured["use_cli_agent"] is True

    # Empty body → no override (falls back to global YOLO setting).
    captured.clear()
    with _client() as c:
        resp = c.post(f"/admin/sketches/{sketch_id}/route", json={})
    assert captured["use_cli_agent"] is None

    # Non-bool values are rejected — the override must be unambiguous.
    captured.clear()
    with _client() as c:
        resp = c.post(
            f"/admin/sketches/{sketch_id}/route",
            json={"use_cli_agent": "yes"},
        )
    assert captured["use_cli_agent"] is None


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
