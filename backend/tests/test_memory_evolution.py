"""Tests for the memory evolution engine — extraction, decay, consolidation."""

from datetime import datetime, timedelta

import pytest

from app.db.agent_memory import create_thread, save_messages
from app.db.agents import create_agent
from app.db.knowledge_graph import count_entities, list_entities, upsert_entity
from app.services.memory_evolution import (
    apply_decay,
    consolidate_thread,
    extract_entities_from_text,
    find_related_threads,
    process_message_entities,
    should_consolidate,
)


@pytest.fixture()
def agent_id(isolated_db):
    """Create a test agent and return its ID."""
    return create_agent("Evolution Test Agent", description="For evolution tests")


@pytest.fixture()
def thread_with_messages(agent_id):
    """Create a thread with several messages mentioning tech entities."""
    thread = create_thread(resource_id=agent_id, resource_type="agent", title="Tech chat")
    save_messages(
        thread["id"],
        [
            {"role": "user", "content": "We should use Python and Flask for the backend."},
            {"role": "assistant", "content": "Flask is great. We can add SQLite for storage."},
            {"role": "user", "content": "Let's also add pytest for testing."},
        ],
    )
    return thread


class TestExtractEntities:
    """Entity extraction from text."""

    def test_extracts_technology_entities(self):
        entities = extract_entities_from_text("We use Python and Flask together.")
        names = {e["name"] for e in entities}
        assert "python" in names
        assert "flask" in names

    def test_extracts_tool_entities(self):
        entities = extract_entities_from_text("Run pytest and ruff for quality.")
        names = {e["name"] for e in entities}
        assert "pytest" in names
        assert "ruff" in names

    def test_extracts_concept_entities(self):
        entities = extract_entities_from_text("The webhook triggers the scheduler.")
        names = {e["name"] for e in entities}
        assert "webhook" in names
        assert "scheduler" in names

    def test_no_duplicates(self):
        entities = extract_entities_from_text("Python Python Python")
        python_entities = [e for e in entities if e["name"] == "python"]
        assert len(python_entities) == 1

    def test_co_occurrence_relations(self):
        entities = extract_entities_from_text("Python and Flask")
        python = next(e for e in entities if e["name"] == "python")
        assert any(r["target"] == "flask" for r in python["relations"])

    def test_empty_text_returns_empty(self):
        assert extract_entities_from_text("") == []

    def test_no_match_returns_empty(self):
        assert extract_entities_from_text("just some random words") == []


class TestProcessMessageEntities:
    """Upsert entities from message text into KG."""

    def test_upserts_entities_to_kg(self, agent_id):
        count = process_message_entities(agent_id, "Using Python with Flask and SQLite.")
        assert count >= 3
        entities = list_entities(agent_id)
        names = {e["name"] for e in entities}
        assert "python" in names
        assert "flask" in names
        assert "sqlite" in names

    def test_returns_zero_for_no_entities(self, agent_id):
        count = process_message_entities(agent_id, "nothing special here")
        assert count == 0


class TestApplyDecay:
    """Exponential importance decay."""

    def test_decay_reduces_importance(self, agent_id):
        from app.db.connection import get_connection

        # Insert an entity with old last_seen
        upsert_entity(agent_id, "OldTech", "technology")
        old_date = (datetime.utcnow() - timedelta(days=60)).strftime("%Y-%m-%d %H:%M:%S")
        with get_connection() as conn:
            conn.execute(
                "UPDATE kg_entities SET last_seen = ?, importance_score = 1.0 "
                "WHERE agent_id = ? AND name = 'oldtech'",
                (old_date, agent_id),
            )
            conn.commit()

        decayed = apply_decay(agent_id)
        assert decayed >= 1

        entities = list_entities(agent_id)
        oldtech = next(e for e in entities if e["name"] == "oldtech")
        assert oldtech["importance_score"] < 1.0

    def test_recent_entities_not_decayed(self, agent_id):
        upsert_entity(agent_id, "NewTech", "technology")
        decayed = apply_decay(agent_id)
        # Entity was just created (today), so days_since < 1 => skipped
        assert decayed == 0

    def test_archives_below_threshold(self, agent_id):
        from app.db.connection import get_connection

        upsert_entity(agent_id, "Forgotten", "technology")
        # Set very old date and low importance
        old_date = (datetime.utcnow() - timedelta(days=365)).strftime("%Y-%m-%d %H:%M:%S")
        with get_connection() as conn:
            conn.execute(
                "UPDATE kg_entities SET last_seen = ?, importance_score = 0.15 "
                "WHERE agent_id = ? AND name = 'forgotten'",
                (old_date, agent_id),
            )
            conn.commit()

        apply_decay(agent_id)
        entities = list_entities(agent_id)
        forgotten = next((e for e in entities if e["name"] == "forgotten"), None)
        # Should be archived (importance_score = 0)
        if forgotten:
            assert forgotten["importance_score"] == 0


class TestShouldConsolidate:
    """Consolidation trigger logic."""

    def test_below_threshold_returns_false(self, agent_id):
        thread = create_thread(resource_id=agent_id, resource_type="agent")
        # No messages, so count < threshold
        assert should_consolidate(agent_id, thread["id"], threshold=50) is False

    def test_above_threshold_returns_true(self, agent_id):
        thread = create_thread(resource_id=agent_id, resource_type="agent")
        # Add enough messages
        messages = [
            {"role": "user", "content": f"Message {i} about Python and Flask"}
            for i in range(50)
        ]
        save_messages(thread["id"], messages)
        # First time: no previous consolidation, so should return True
        assert should_consolidate(agent_id, thread["id"], threshold=50) is True


class TestConsolidateThread:
    """Thread consolidation."""

    def test_creates_consolidation_log(self, thread_with_messages, agent_id):
        result = consolidate_thread(agent_id, thread_with_messages["id"])
        assert result is not None
        assert result["agent_id"] == agent_id
        assert result["thread_id"] == thread_with_messages["id"]
        assert result["entity_count"] >= 0
        assert result["id"].startswith("cons-")

    def test_empty_thread_returns_none(self, agent_id):
        thread = create_thread(resource_id=agent_id, resource_type="agent")
        result = consolidate_thread(agent_id, thread["id"])
        assert result is None

    def test_consolidation_extracts_entities(self, thread_with_messages, agent_id):
        consolidate_thread(agent_id, thread_with_messages["id"])
        entities = list_entities(agent_id)
        names = {e["name"] for e in entities}
        # Messages mention Python, Flask, SQLite, pytest
        assert "python" in names
        assert "flask" in names


class TestFindRelatedThreads:
    """Cross-thread entity linking."""

    def test_finds_threads_sharing_entities(self, agent_id):
        # Create two threads mentioning the same tech
        t1 = create_thread(resource_id=agent_id, resource_type="agent", title="Thread 1")
        save_messages(t1["id"], [{"role": "user", "content": "Python and Flask are great."}])

        t2 = create_thread(resource_id=agent_id, resource_type="agent", title="Thread 2")
        save_messages(t2["id"], [{"role": "user", "content": "Python is my favorite language."}])

        # Ensure entities exist in KG
        upsert_entity(agent_id, "Python", "technology")
        upsert_entity(agent_id, "Flask", "technology")

        related = find_related_threads(agent_id, t1["id"])
        # t2 should show up as related (shares "python")
        related_ids = [r["id"] for r in related]
        assert t2["id"] in related_ids

    def test_no_related_threads_returns_empty(self, agent_id):
        t1 = create_thread(resource_id=agent_id, resource_type="agent", title="Isolated")
        save_messages(t1["id"], [{"role": "user", "content": "nothing matchable"}])
        related = find_related_threads(agent_id, t1["id"])
        assert related == []


class TestRelatedThreadsEndpoint:
    """HTTP endpoint for related threads."""

    def test_get_related_threads(self, client, agent_id, thread_with_messages):
        resp = client.get(
            f"/admin/agents/{agent_id}/memory/threads/"
            f"{thread_with_messages['id']}/related"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "related_threads" in data
        assert "count" in data

    def test_not_found_for_missing_thread(self, client, agent_id):
        resp = client.get(f"/admin/agents/{agent_id}/memory/threads/fake-id/related")
        assert resp.status_code == 404


class TestConsolidationEndpoint:
    """HTTP endpoint for triggering consolidation."""

    def test_trigger_consolidation(self, client, agent_id, thread_with_messages):
        resp = client.post(f"/admin/agents/{agent_id}/knowledge/consolidate")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "consolidated" in data
        assert "details" in data

    def test_consolidation_not_found_for_missing_agent(self, client):
        resp = client.post("/admin/agents/agent-nonexist/knowledge/consolidate")
        assert resp.status_code == 404
