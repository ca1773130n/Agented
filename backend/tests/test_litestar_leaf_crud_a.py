"""Smoke tests for the wave 65 leaf CRUD batch."""

from litestar.testing import create_test_client

from app_litestar.auth import provide_caller
from app_litestar.routes.leaf_crud_a import (
    bookmarks_router,
    bot_memory_router,
    prompt_snippets_router,
    scope_filters_router,
    trigger_conditions_router,
)


def _client():
    return create_test_client(
        route_handlers=[
            bookmarks_router,
            prompt_snippets_router,
            scope_filters_router,
            trigger_conditions_router,
            bot_memory_router,
        ],
        dependencies={"caller": provide_caller},
    )


# Bookmarks


def test_list_bookmarks_empty(isolated_db):
    with _client() as c:
        resp = c.get("/admin/bookmarks")
    assert resp.status_code == 200
    assert resp.json()["bookmarks"] == []


def test_unknown_bookmark_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/bookmarks/missing")
    assert resp.status_code == 404


def test_update_unknown_bookmark_404(isolated_db):
    with _client() as c:
        resp = c.put("/admin/bookmarks/missing", json={"title": "x"})
    assert resp.status_code == 404


def test_delete_unknown_bookmark_404(isolated_db):
    with _client() as c:
        resp = c.delete("/admin/bookmarks/missing")
    assert resp.status_code == 404


def test_trigger_bookmarks_empty(isolated_db):
    with _client() as c:
        resp = c.get("/admin/triggers/missing/bookmarks")
    assert resp.status_code == 200


# Prompt snippets


def test_list_snippets(isolated_db):
    with _client() as c:
        resp = c.get("/admin/prompt-snippets/")
    assert resp.status_code == 200
    assert "snippets" in resp.json()


def test_create_snippet_requires_name(isolated_db):
    with _client() as c:
        resp = c.post("/admin/prompt-snippets/", json={})
    assert resp.status_code == 400


def test_create_snippet_invalid_name(isolated_db):
    with _client() as c:
        resp = c.post("/admin/prompt-snippets/", json={"name": "bad name!", "content": "x"})
    assert resp.status_code == 400


def test_unknown_snippet_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/prompt-snippets/missing")
    assert resp.status_code == 404


def test_resolve_requires_text(isolated_db):
    with _client() as c:
        resp = c.post("/admin/prompt-snippets/resolve", json={})
    assert resp.status_code == 400


# Scope filters


def test_list_scope_filters(isolated_db):
    with _client() as c:
        resp = c.get("/admin/scope-filters")
    assert resp.status_code == 200


def test_unknown_scope_filter_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/scope-filters/missing")
    assert resp.status_code == 404


def test_create_scope_filter_requires_trigger_id(isolated_db):
    with _client() as c:
        resp = c.post("/admin/scope-filters", json={})
    assert resp.status_code == 400


def test_add_pattern_to_unknown_filter_404(isolated_db):
    with _client() as c:
        resp = c.post(
            "/admin/scope-filters/missing/patterns",
            json={"type": "include", "pattern": "*"},
        )
    assert resp.status_code == 404


# Trigger conditions


def test_list_trigger_conditions_empty(isolated_db):
    with _client() as c:
        resp = c.get("/admin/triggers/missing/conditions")
    assert resp.status_code == 200


def test_create_condition_requires_name(isolated_db):
    with _client() as c:
        resp = c.post("/admin/triggers/missing/conditions", json={})
    assert resp.status_code == 400


def test_unknown_condition_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/trigger-conditions/missing")
    assert resp.status_code == 404


def test_delete_unknown_condition_404(isolated_db):
    with _client() as c:
        resp = c.delete("/admin/trigger-conditions/missing")
    assert resp.status_code == 404


# Bot memory


def test_list_bots_with_memory(isolated_db):
    with _client() as c:
        resp = c.get("/admin/bots/memory")
    assert resp.status_code == 200
    assert "bots" in resp.json()


def test_get_unknown_bot_memory_returns_empty(isolated_db):
    with _client() as c:
        resp = c.get("/admin/bots/missing/memory")
    assert resp.status_code == 200


def test_upsert_bot_memory_requires_value(isolated_db):
    with _client() as c:
        resp = c.put("/admin/bots/bot-x/memory/key", json={})
    assert resp.status_code == 400


def test_delete_unknown_memory_entry_404(isolated_db):
    with _client() as c:
        resp = c.delete("/admin/bots/bot-x/memory/missing-key")
    assert resp.status_code == 404
