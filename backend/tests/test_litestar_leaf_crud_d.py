"""Smoke tests for the wave 68 leaf CRUD batch."""

from litestar.testing import create_test_client

from app_litestar.auth import provide_caller
from app_litestar.routes.leaf_crud_d import (
    campaigns_router,
    collaborative_router,
    execution_tagging_router,
    knowledge_graph_router,
    pr_assignment_router,
)


def _client():
    return create_test_client(
        route_handlers=[
            knowledge_graph_router,
            collaborative_router,
            campaigns_router,
            execution_tagging_router,
            pr_assignment_router,
        ],
        dependencies={"caller": provide_caller},
    )


# Knowledge graph


def test_kg_unknown_agent_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/agents/missing/knowledge/entities")
    assert resp.status_code == 404


def test_kg_search_empty_q(isolated_db):
    with _client() as c:
        resp = c.get("/admin/agents/missing/knowledge/search?q=")
    assert resp.status_code == 200
    assert resp.json() == {"entities": [], "total": 0}


def test_kg_consolidate_unknown_agent_404(isolated_db):
    with _client() as c:
        resp = c.post("/admin/agents/missing/knowledge/consolidate", json={})
    assert resp.status_code == 404


# Collaborative viewers


def test_viewer_join_requires_id(isolated_db):
    with _client() as c:
        resp = c.post("/admin/executions/exec-x/viewers/join", json={})
    assert resp.status_code == 400


def test_viewer_leave_requires_id(isolated_db):
    with _client() as c:
        resp = c.post("/admin/executions/exec-x/viewers/leave", json={})
    assert resp.status_code == 400


def test_viewer_heartbeat_requires_id(isolated_db):
    with _client() as c:
        resp = c.post("/admin/executions/exec-x/viewers/heartbeat", json={})
    assert resp.status_code == 400


def test_list_viewers(isolated_db):
    with _client() as c:
        resp = c.get("/admin/executions/exec-x/viewers")
    assert resp.status_code == 200


def test_post_comment_requires_body(isolated_db):
    with _client() as c:
        resp = c.post("/admin/executions/exec-x/comments", json={})
    assert resp.status_code == 400


def test_list_comments(isolated_db):
    with _client() as c:
        resp = c.get("/admin/executions/exec-x/comments")
    assert resp.status_code == 200


def test_delete_unknown_comment_404(isolated_db):
    with _client() as c:
        resp = c.delete("/admin/comments/missing")
    assert resp.status_code == 404


# Campaigns


def test_list_campaigns(isolated_db):
    with _client() as c:
        resp = c.get("/admin/campaigns")
    assert resp.status_code == 200


def test_create_campaign_requires_body(isolated_db):
    with _client() as c:
        resp = c.post("/admin/campaigns", json={})
    assert resp.status_code == 400


def test_unknown_campaign_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/campaigns/missing")
    assert resp.status_code == 404


def test_unknown_campaign_results_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/campaigns/missing/results")
    assert resp.status_code == 404


def test_delete_unknown_campaign_404(isolated_db):
    with _client() as c:
        resp = c.delete("/admin/campaigns/missing")
    assert resp.status_code == 404


def test_list_trigger_campaigns(isolated_db):
    with _client() as c:
        resp = c.get("/admin/triggers/missing/campaigns")
    assert resp.status_code == 200


# Execution tagging


def test_list_execution_tags(isolated_db):
    with _client() as c:
        resp = c.get("/admin/execution-tags")
    assert resp.status_code == 200


def test_create_tag_requires_name(isolated_db):
    with _client() as c:
        resp = c.post("/admin/execution-tags", json={})
    assert resp.status_code == 400


def test_create_tag_invalid_color(isolated_db):
    with _client() as c:
        resp = c.post("/admin/execution-tags", json={"name": "x", "color": "neon"})
    assert resp.status_code == 400


def test_delete_unknown_tag_404(isolated_db):
    with _client() as c:
        resp = c.delete("/admin/execution-tags/missing")
    assert resp.status_code == 404


def test_list_tagged_executions(isolated_db):
    with _client() as c:
        resp = c.get("/admin/execution-tagging")
    assert resp.status_code == 200


def test_add_tag_to_execution_requires_body(isolated_db):
    with _client() as c:
        resp = c.post("/admin/execution-tagging/exec-x/tags", json={})
    assert resp.status_code == 400


def test_remove_tag_from_unknown_assignment_404(isolated_db):
    with _client() as c:
        resp = c.delete("/admin/execution-tagging/exec-x/tags/tag-x")
    assert resp.status_code == 404


# PR assignment


def test_list_pr_rules(isolated_db):
    with _client() as c:
        resp = c.get("/api/pr-assignment/rules")
    assert resp.status_code == 200


def test_create_pr_rule_requires_pattern(isolated_db):
    with _client() as c:
        resp = c.post("/api/pr-assignment/rules", json={})
    assert resp.status_code == 400


def test_delete_unknown_rule_404(isolated_db):
    with _client() as c:
        resp = c.delete("/api/pr-assignment/rules/missing")
    assert resp.status_code == 404


def test_get_pr_settings_defaults(isolated_db):
    with _client() as c:
        resp = c.get("/api/pr-assignment/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["pr_assignment_enabled"] == "true"
    assert body["pr_assignment_min_confidence"] == "70"


def test_update_pr_settings(isolated_db):
    with _client() as c:
        resp = c.put(
            "/api/pr-assignment/settings",
            json={"pr_assignment_enabled": "false"},
        )
    assert resp.status_code == 200
    assert resp.json()["updated"]["pr_assignment_enabled"] == "false"


def test_list_recent_assignments(isolated_db):
    with _client() as c:
        resp = c.get("/api/pr-assignment/recent")
    assert resp.status_code == 200
