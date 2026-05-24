"""Tests for admin /harness/layers and /run-history routes."""

from __future__ import annotations

from litestar.testing import create_test_client

from app.db import harness_layers as layers_repo
from app.db import harness_snapshots as snapshots_repo
from app_litestar.auth import provide_caller
from app_litestar.routes.harness_layers import harness_layers_router


def _client():
    return create_test_client(
        route_handlers=[harness_layers_router],
        dependencies={"caller": provide_caller},
    )


def test_list_bot_layers_groups_by_kind(isolated_db):
    layers_repo.create_layer(
        bot_id="bot-list", layer="h2", name="block-x",
        payload={"title": "x"},
    )
    layers_repo.create_layer(
        bot_id="bot-list", layer="h3", name="quote-cols",
        payload={"title": "q"},
    )
    layers_repo.create_layer(
        bot_id="bot-list", layer="h5", name="skill-a",
        payload={"title": "s"},
    )

    with _client() as c:
        resp = c.get("/admin/bots/bot-list/harness/layers")
    body = resp.json()
    assert resp.status_code == 200
    assert body["bot_id"] == "bot-list"
    assert len(body["layers"]["h2"]) == 1
    assert len(body["layers"]["h3"]) == 1
    assert len(body["layers"]["h4"]) == 0
    assert len(body["layers"]["h5"]) == 1


def test_list_bot_layers_filter(isolated_db):
    layers_repo.create_layer(
        bot_id="bot-filter", layer="h2", name="x",
        payload={"title": "x"},
    )
    layers_repo.create_layer(
        bot_id="bot-filter", layer="h3", name="y",
        payload={"title": "y"},
    )
    with _client() as c:
        resp = c.get("/admin/bots/bot-filter/harness/layers?layer=h2")
    body = resp.json()
    assert len(body["layers"]["h2"]) == 1
    assert len(body["layers"]["h3"]) == 0


def test_get_single_layer_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/harness/layers/hl-nope")
    assert resp.status_code == 404


def test_get_single_layer_returns_payload(isolated_db):
    lid = layers_repo.create_layer(
        bot_id="bot-get", layer="h3", name="r",
        payload={"title": "r", "rule_text": "ok"},
    )
    with _client() as c:
        resp = c.get(f"/admin/harness/layers/{lid}")
    body = resp.json()
    assert resp.status_code == 200
    assert body["id"] == lid
    assert body["payload"]["title"] == "r"


def test_toggle_layer_disables_then_reenables(isolated_db):
    lid = layers_repo.create_layer(
        bot_id="bot-toggle", layer="h3", name="r",
        payload={"title": "r"},
    )
    with _client() as c:
        resp = c.patch(
            f"/admin/harness/layers/{lid}", json={"enabled": False},
        )
        assert resp.json()["enabled"] is False
        resp = c.patch(
            f"/admin/harness/layers/{lid}", json={"enabled": True},
        )
        assert resp.json()["enabled"] is True


def test_run_history_returns_recent_snapshots(isolated_db):
    bot = "bot-history"
    for i in range(3):
        snapshots_repo.upsert_snapshot(
            execution_id=f"exec-{i}", bot_id=bot,
            harness_kind="claude",
            layer_versions={"h3": 1, "h2": 1},
            artifact={"hook_specs": []},
            applied=True,
        )
    with _client() as c:
        resp = c.get(f"/admin/bots/{bot}/harness/run-history?limit=10")
    body = resp.json()
    assert resp.status_code == 200
    assert len(body["snapshots"]) == 3
    first = body["snapshots"][0]
    assert first["layer_versions"] == {"h3": 1, "h2": 1}
    assert first["applied"] is True
