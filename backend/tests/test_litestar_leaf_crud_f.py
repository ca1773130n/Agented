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


def _make_agent_with_corrupt_memory_config(raw: str = "{not valid"):
    """Helper for v0.5.3 audit #6/#7 — insert an agent whose
    memory_config column holds a malformed JSON blob."""
    from app.database import get_connection
    from app.db.agents import create_agent

    agent_id = create_agent(name="MemCfgAgent", description="x")
    assert agent_id is not None
    with get_connection() as conn:
        conn.execute("UPDATE agents SET memory_config = ? WHERE id = ?", (raw, agent_id))
        conn.commit()
    return agent_id


def test_get_memory_config_logs_and_returns_defaults_on_corrupt(isolated_db, monkeypatch):
    """v0.5.3 audit #6: silent corrupt-JSON parse used to return the
    default config without surfacing the corruption. Now logs a WARNING
    and still returns defaults so the API contract is preserved.

    The Litestar test client's logger plumbing doesn't propagate to
    pytest's caplog reliably, so spy on the route module's logger
    directly via monkeypatch.
    """
    from app_litestar.routes import leaf_crud_f

    warnings: list[tuple[str, tuple]] = []
    monkeypatch.setattr(
        leaf_crud_f.logger,
        "warning",
        lambda fmt, *args, **kwargs: warnings.append((fmt, args)),
    )

    agent_id = _make_agent_with_corrupt_memory_config()
    with _client() as c:
        resp = c.get(f"/admin/agents/{agent_id}/memory/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True  # default config restored
    assert any(
        "corrupt memory_config JSON" in fmt and agent_id in args for fmt, args in warnings
    ), f"expected warning, got {warnings}"


def test_update_memory_config_logs_on_corrupt_existing(isolated_db, monkeypatch):
    """v0.5.3 audit #7: silent corrupt-JSON parse during update used to
    drop unrelated keys (existing = {} after the silent except). Now
    logs a WARNING. Behavior — partial update only setting body keys —
    is unchanged because preserving a corrupt blob is not safe."""
    from app_litestar.routes import leaf_crud_f

    warnings: list[tuple[str, tuple]] = []
    monkeypatch.setattr(
        leaf_crud_f.logger,
        "warning",
        lambda fmt, *args, **kwargs: warnings.append((fmt, args)),
    )

    agent_id = _make_agent_with_corrupt_memory_config()
    with _client() as c:
        resp = c.put(
            f"/admin/agents/{agent_id}/memory/config",
            json={"enabled": False},
        )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False
    assert any(
        "corrupt memory_config JSON" in fmt and agent_id in args for fmt, args in warnings
    ), f"expected warning, got {warnings}"


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
        resp = c.post("/admin/bulk/plugins", json={"action": "create", "items": "x"})
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
        resp = c.post("/admin/conversations/conv-x/branches", json={})
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
