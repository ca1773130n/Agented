"""Tests for the knowledge graph — entities, relations, traversal, API endpoints."""

import json

import pytest

from app.db.agents import create_agent
from app.db.knowledge_graph import (
    count_entities,
    count_relations,
    delete_entity,
    get_entity,
    get_entity_context,
    get_entity_relations,
    list_entities,
    promote_entity,
    search_entities,
    traverse_graph,
    upsert_entity,
    upsert_relation,
)

AGENT_ID = "agent-kgtest"


@pytest.fixture()
def agent_id(isolated_db):
    """Create a test agent and return its ID."""
    return create_agent("KG Test Agent", description="For KG tests")


class TestUpsertEntity:
    """Entity insert and update operations."""

    def test_insert_new_entity(self, agent_id):
        entity = upsert_entity(agent_id, "Python", "technology")
        assert entity["id"].startswith("kge-")
        assert entity["name"] == "python"
        assert entity["entity_type"] == "technology"
        assert entity["mention_count"] == 1

    def test_upsert_increments_mention_count(self, agent_id):
        upsert_entity(agent_id, "Python", "technology")
        entity = upsert_entity(agent_id, "Python", "technology")
        assert entity["mention_count"] == 2

    def test_name_is_lowercased_and_stripped(self, agent_id):
        entity = upsert_entity(agent_id, "  Flask  ", "technology")
        assert entity["name"] == "flask"

    def test_upsert_with_properties(self, agent_id):
        props = {"version": "3.12", "category": "language"}
        entity = upsert_entity(agent_id, "Python", "technology", properties=props)
        assert entity["properties"]["version"] == "3.12"

    def test_different_types_are_separate_entities(self, agent_id):
        e1 = upsert_entity(agent_id, "flask", "technology")
        e2 = upsert_entity(agent_id, "flask", "project")
        assert e1["id"] != e2["id"]


class TestUpsertRelation:
    """Relation creation and updates."""

    def test_create_relation(self, agent_id):
        rel = upsert_relation(
            agent_id,
            "python",
            "technology",
            "flask",
            "technology",
            "used_by",
            confidence=0.8,
        )
        assert rel is not None
        assert rel["id"].startswith("kgr-")
        assert rel["relation_type"] == "used_by"
        assert rel["confidence"] == 0.8

    def test_upsert_relation_increments_mention_count(self, agent_id):
        upsert_relation(
            agent_id,
            "python",
            "technology",
            "flask",
            "technology",
            "used_by",
        )
        rel = upsert_relation(
            agent_id,
            "python",
            "technology",
            "flask",
            "technology",
            "used_by",
        )
        assert rel["mention_count"] == 2

    def test_relation_creates_entities(self, agent_id):
        upsert_relation(
            agent_id,
            "alice",
            "person",
            "acme",
            "organization",
            "works_at",
        )
        alice = get_entity(agent_id, "alice", "person")
        acme = get_entity(agent_id, "acme", "organization")
        assert alice is not None
        assert acme is not None


class TestGetAndListEntities:
    """Entity retrieval operations."""

    def test_get_entity_by_name(self, agent_id):
        upsert_entity(agent_id, "Vue", "technology")
        entity = get_entity(agent_id, "vue")
        assert entity is not None
        assert entity["name"] == "vue"

    def test_get_entity_by_name_and_type(self, agent_id):
        upsert_entity(agent_id, "vue", "technology")
        entity = get_entity(agent_id, "vue", "technology")
        assert entity is not None

    def test_get_nonexistent_entity(self, agent_id):
        assert get_entity(agent_id, "nonexistent") is None

    def test_list_entities(self, agent_id):
        upsert_entity(agent_id, "python", "technology")
        upsert_entity(agent_id, "flask", "technology")
        upsert_entity(agent_id, "alice", "person")
        entities = list_entities(agent_id)
        assert len(entities) == 3

    def test_list_entities_with_type_filter(self, agent_id):
        upsert_entity(agent_id, "python", "technology")
        upsert_entity(agent_id, "flask", "technology")
        upsert_entity(agent_id, "alice", "person")
        entities = list_entities(agent_id, entity_type="technology")
        assert len(entities) == 2

    def test_list_entities_with_importance_filter(self, agent_id):
        upsert_entity(agent_id, "python", "technology")
        entities = list_entities(agent_id, min_importance=0.9)
        assert len(entities) == 0  # Default importance is 0.5

    def test_count_entities(self, agent_id):
        upsert_entity(agent_id, "a", "concept")
        upsert_entity(agent_id, "b", "concept")
        assert count_entities(agent_id) == 2

    def test_count_relations(self, agent_id):
        upsert_relation(agent_id, "a", "concept", "b", "concept", "related_to")
        assert count_relations(agent_id) == 1


class TestTraverseGraph:
    """BFS graph traversal."""

    def test_traverse_1_hop(self, agent_id):
        upsert_relation(agent_id, "python", "technology", "flask", "technology", "powers")
        upsert_relation(agent_id, "python", "technology", "django", "technology", "powers")
        upsert_relation(agent_id, "flask", "technology", "jinja", "technology", "uses")

        subgraph = traverse_graph(agent_id, "python", hops=1)
        names = {e["name"] for e in subgraph["entities"]}
        assert "python" in names
        assert "flask" in names
        assert "django" in names
        # jinja is 2 hops away
        assert "jinja" not in names

    def test_traverse_2_hops(self, agent_id):
        upsert_relation(agent_id, "python", "technology", "flask", "technology", "powers")
        upsert_relation(agent_id, "flask", "technology", "jinja", "technology", "uses")

        subgraph = traverse_graph(agent_id, "python", hops=2)
        names = {e["name"] for e in subgraph["entities"]}
        assert "python" in names
        assert "flask" in names
        assert "jinja" in names

    def test_traverse_nonexistent_seed(self, agent_id):
        subgraph = traverse_graph(agent_id, "nonexistent", hops=1)
        assert subgraph["entities"] == []
        assert subgraph["relations"] == []


class TestSearchEntities:
    """LIKE-based entity search."""

    def test_search_by_prefix(self, agent_id):
        upsert_entity(agent_id, "python", "technology")
        upsert_entity(agent_id, "pytorch", "technology")
        upsert_entity(agent_id, "flask", "technology")

        results = search_entities(agent_id, "pyth")
        assert len(results) == 1
        assert results[0]["name"] == "python"

    def test_search_by_substring(self, agent_id):
        upsert_entity(agent_id, "python", "technology")
        upsert_entity(agent_id, "pytorch", "technology")

        results = search_entities(agent_id, "py")
        assert len(results) == 2

    def test_search_no_results(self, agent_id):
        results = search_entities(agent_id, "zzz_nonexistent")
        assert results == []


class TestGetEntityContext:
    """Natural language context generation."""

    def test_context_with_relations(self, agent_id):
        upsert_relation(agent_id, "python", "technology", "flask", "technology", "powers")
        ctx = get_entity_context(agent_id, ["python"])
        assert "python" in ctx
        assert "flask" in ctx
        assert "powers" in ctx

    def test_context_entity_without_relations(self, agent_id):
        upsert_entity(agent_id, "orphan", "concept")
        ctx = get_entity_context(agent_id, ["orphan"])
        assert "orphan" in ctx

    def test_context_empty_list(self, agent_id):
        assert get_entity_context(agent_id, []) == ""

    def test_context_nonexistent_entity(self, agent_id):
        assert get_entity_context(agent_id, ["nonexistent"]) == ""


class TestPromoteEntity:
    """Importance score boosting."""

    def test_promote_increases_importance(self, agent_id):
        entity = upsert_entity(agent_id, "python", "technology")
        original_score = entity["importance_score"]
        promote_entity(entity["id"], boost=0.1)
        updated = get_entity(agent_id, "python", "technology")
        assert updated["importance_score"] == pytest.approx(original_score + 0.1)

    def test_promote_caps_at_1(self, agent_id):
        entity = upsert_entity(agent_id, "python", "technology")
        promote_entity(entity["id"], boost=0.6)  # 0.5 + 0.6 > 1.0
        updated = get_entity(agent_id, "python", "technology")
        assert updated["importance_score"] == 1.0


class TestDeleteEntity:
    """Entity deletion with cascade."""

    def test_delete_entity(self, agent_id):
        entity = upsert_entity(agent_id, "python", "technology")
        assert delete_entity(entity["id"]) is True
        assert get_entity(agent_id, "python", "technology") is None

    def test_delete_cascades_relations(self, agent_id):
        upsert_relation(agent_id, "python", "technology", "flask", "technology", "powers")
        python = get_entity(agent_id, "python", "technology")
        delete_entity(python["id"])
        # Relations should be gone
        assert count_relations(agent_id) == 0

    def test_delete_nonexistent(self, agent_id):
        assert delete_entity("kge-nonexist") is False


class TestEntityRelations:
    """Get relations for an entity."""

    def test_get_entity_relations(self, agent_id):
        upsert_relation(agent_id, "python", "technology", "flask", "technology", "powers")
        upsert_relation(agent_id, "python", "technology", "django", "technology", "powers")
        python = get_entity(agent_id, "python", "technology")
        rels = get_entity_relations(python["id"])
        assert len(rels) == 2
        assert all(r.get("source_name") or r.get("target_name") for r in rels)


class TestKGAPIEndpoints:
    """API endpoint integration tests."""

    def test_list_entities_endpoint(self, client, isolated_db):
        agent_id = create_agent("API Test Agent")
        upsert_entity(agent_id, "python", "technology")
        upsert_entity(agent_id, "flask", "technology")

        resp = client.get(f"/admin/agents/{agent_id}/knowledge/entities")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 2
        assert len(data["entities"]) == 2

    def test_get_entity_endpoint(self, client, isolated_db):
        agent_id = create_agent("API Test Agent")
        entity = upsert_entity(agent_id, "python", "technology")

        resp = client.get(f"/admin/agents/{agent_id}/knowledge/entities/{entity['id']}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["name"] == "python"

    def test_get_entity_not_found(self, client, isolated_db):
        agent_id = create_agent("API Test Agent")
        resp = client.get(f"/admin/agents/{agent_id}/knowledge/entities/kge-nonexist")
        assert resp.status_code == 404

    def test_stats_endpoint(self, client, isolated_db):
        agent_id = create_agent("API Test Agent")
        upsert_entity(agent_id, "python", "technology")
        upsert_relation(agent_id, "python", "technology", "flask", "technology", "powers")

        resp = client.get(f"/admin/agents/{agent_id}/knowledge/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["entity_count"] == 2
        assert data["relation_count"] == 1

    def test_search_endpoint(self, client, isolated_db):
        agent_id = create_agent("API Test Agent")
        upsert_entity(agent_id, "python", "technology")
        upsert_entity(agent_id, "pytorch", "technology")

        resp = client.get(f"/admin/agents/{agent_id}/knowledge/search?q=py")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 2

    def test_search_empty_query(self, client, isolated_db):
        agent_id = create_agent("API Test Agent")
        resp = client.get(f"/admin/agents/{agent_id}/knowledge/search?q=")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 0

    def test_graph_endpoint(self, client, isolated_db):
        agent_id = create_agent("API Test Agent")
        upsert_relation(agent_id, "python", "technology", "flask", "technology", "powers")

        resp = client.get(f"/admin/agents/{agent_id}/knowledge/graph?seed=python&hops=1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["entities"]) == 2
        assert len(data["relations"]) == 1

    def test_delete_entity_endpoint(self, client, isolated_db):
        agent_id = create_agent("API Test Agent")
        entity = upsert_entity(agent_id, "python", "technology")

        resp = client.delete(f"/admin/agents/{agent_id}/knowledge/entities/{entity['id']}")
        assert resp.status_code == 200
        assert get_entity(agent_id, "python", "technology") is None

    def test_agent_not_found(self, client, isolated_db):
        resp = client.get("/admin/agents/agent-nonexist/knowledge/entities")
        assert resp.status_code == 404
