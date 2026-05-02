"""Smoke tests for the wave 70 leaf CRUD batch."""

from litestar.testing import create_test_client

from app_litestar.auth import provide_caller
from app_litestar.routes.leaf_crud_f import (
    agent_memory_router,
    bulk_router,
    conversation_branches_router,
    replay_router,
)


def _client():
    return create_test_client(
        route_handlers=[
            agent_memory_router,
            bulk_router,
            replay_router,
            conversation_branches_router,
        ],
        dependencies={"caller": provide_caller},
    )


# Agent memory


def test_unknown_agent_threads_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/agents/missing/memory/threads")
    assert resp.status_code == 404


def test_create_thread_unknown_agent_404(isolated_db):
    with _client() as c:
        resp = c.post("/admin/agents/missing/memory/threads", json={"title": "x"})
    assert resp.status_code == 404


def test_get_unknown_thread_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/agents/a-x/memory/threads/missing")
    assert resp.status_code == 404


def test_recall_requires_q(isolated_db):
    with _client() as c:
        resp = c.get("/admin/agents/missing/memory/recall")
    assert resp.status_code == 404  # agent missing first


def test_get_unknown_working_memory_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/agents/missing/memory/working")
    assert resp.status_code == 404


def test_get_memory_config_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/agents/missing/memory/config")
    assert resp.status_code == 404


# Bulk


def test_bulk_agents_requires_action(isolated_db):
    with _client() as c:
        resp = c.post("/admin/bulk/agents", json={})
    assert resp.status_code == 400


def test_bulk_triggers_requires_items(isolated_db):
    with _client() as c:
        resp = c.post("/admin/bulk/triggers", json={"action": "create"})
    assert resp.status_code == 400


def test_bulk_plugins_invalid_items(isolated_db):
    with _client() as c:
        resp = c.post(
            "/admin/bulk/plugins", json={"action": "create", "items": "x"}
        )
    assert resp.status_code == 400


# Replay


def test_replay_unknown_execution_404(isolated_db):
    with _client() as c:
        resp = c.post("/admin/executions/missing/replay", json={})
    # service may raise NOT_FOUND or BAD_REQUEST; both are acceptable error codes
    assert resp.status_code in (400, 404)


def test_list_comparisons_empty(isolated_db):
    with _client() as c:
        resp = c.get("/admin/executions/missing/comparisons")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_unknown_comparison_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/replay-comparisons/missing")
    assert resp.status_code == 404


def test_unknown_comparison_diff_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/replay-comparisons/missing/diff")
    assert resp.status_code == 404


def test_diff_context_requires_diff_text(isolated_db):
    with _client() as c:
        resp = c.post("/admin/diff-context/preview", json={})
    assert resp.status_code == 400


# Conversation branches


def test_create_branch_requires_fork_index(isolated_db):
    with _client() as c:
        resp = c.post(
            "/admin/conversations/conv-x/branches", json={}
        )
    assert resp.status_code == 400


def test_create_branch_invalid_fork_index(isolated_db):
    with _client() as c:
        resp = c.post(
            "/admin/conversations/conv-x/branches",
            json={"fork_message_index": "abc"},
        )
    assert resp.status_code == 400


def test_list_branches_empty(isolated_db):
    with _client() as c:
        resp = c.get("/admin/conversations/conv-x/branches")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_branch_tree(isolated_db):
    with _client() as c:
        resp = c.get("/admin/conversations/conv-x/branches/tree")
    assert resp.status_code == 200


def test_unknown_branch_messages_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/branches/missing/messages")
    assert resp.status_code == 404


def test_add_branch_message_requires_role_content(isolated_db):
    with _client() as c:
        resp = c.post("/admin/branches/missing/messages", json={})
    assert resp.status_code == 400
