"""Tests for the CRAG-style memory orchestrator."""

from unittest.mock import patch

import pytest

from app.db.agent_memory import create_thread, save_messages
from app.db.knowledge_graph import upsert_entity, upsert_relation
from app.services.memory_orchestrator import (
    RetrievalEvaluation,
    evaluate_retrieval_by_score,
    orchestrated_recall,
)

# Patch targets — the orchestrator imports from these modules at call time
_HR = "app.db.agent_memory.hybrid_recall"
_FTS = "app.db.agent_memory.recall_messages"
_VEC = "app.db.agent_memory.vector_recall"
_KG_SEARCH = "app.db.knowledge_graph.search_entities"


class TestEvaluateRetrievalByScore:
    """Score-based retrieval evaluation."""

    def test_empty_results_returns_incorrect(self, isolated_db):
        evaluation = evaluate_retrieval_by_score([], [])
        assert evaluation.relevance == "incorrect"
        assert evaluation.confidence == 0.0

    def test_high_scores_return_correct(self, isolated_db):
        results = [{"id": "msg-1"}, {"id": "msg-2"}]
        scores = [0.020, 0.016]  # Both above correct threshold
        evaluation = evaluate_retrieval_by_score(results, scores)
        assert evaluation.relevance == "correct"
        assert evaluation.confidence > 0.5

    def test_medium_scores_return_ambiguous(self, isolated_db):
        results = [{"id": "msg-1"}, {"id": "msg-2"}]
        scores = [0.010, 0.005]  # max > 0.008, but avg < 0.01
        evaluation = evaluate_retrieval_by_score(results, scores)
        assert evaluation.relevance == "ambiguous"

    def test_low_scores_return_incorrect(self, isolated_db):
        results = [{"id": "msg-1"}]
        scores = [0.003]  # Below all thresholds
        evaluation = evaluate_retrieval_by_score(results, scores)
        assert evaluation.relevance == "incorrect"
        assert evaluation.confidence < 0.5

    def test_confidence_capped_at_one(self, isolated_db):
        results = [{"id": "msg-1"}]
        scores = [0.050]  # 0.050 * 60 = 3.0, should be capped at 1.0
        evaluation = evaluate_retrieval_by_score(results, scores)
        assert evaluation.confidence == 1.0


# --- Helpers for setting up memory data ---


def _setup_agent_memory(agent_id: str = "agent-test01"):
    """Create a thread with messages and KG entities for testing."""
    thread = create_thread(agent_id, "agent", "Test Thread")
    messages = save_messages(
        thread["id"],
        [
            {"role": "user", "content": "Tell me about Python decorators"},
            {"role": "assistant", "content": "Decorators wrap functions in Python"},
            {"role": "user", "content": "What about Flask routes?"},
            {"role": "assistant", "content": "Flask uses decorators for route definitions"},
        ],
    )
    # Add KG entities
    upsert_entity(agent_id, "python", "concept", {"domain": "programming"})
    upsert_entity(agent_id, "flask", "concept", {"domain": "web"})
    upsert_relation(agent_id, "flask", "concept", "python", "concept", "built_with", confidence=0.8)
    return thread, messages


class TestOrchestratedRecallCorrectPath:
    """When hybrid retrieval returns high-quality results."""

    def test_returns_results_on_correct_path(self, isolated_db):
        thread, msgs = _setup_agent_memory()

        # Mock hybrid_recall to return high-quality results, and FTS/vector for scoring
        mock_results = [
            {"id": msgs[1]["id"], "thread_id": thread["id"], "content": "Decorators wrap"},
        ]
        mock_fts = mock_results[:]
        mock_vec = [(mock_results[0], 0.9)]

        with (
            patch(_HR, return_value=mock_results),
            patch(_FTS, return_value=mock_fts),
            patch(_VEC, return_value=mock_vec),
        ):
            result = orchestrated_recall(
                query="decorators",
                agent_id="agent-test01",
                thread_id=thread["id"],
                top_k=5,
                message_range=0,
            )

        assert result["search_mode"] == "orchestrated"
        assert result["count"] >= 1
        assert "retrieval_evaluation" in result
        assert "related_entities" in result

    def test_includes_graph_context_when_entities_exist(self, isolated_db):
        thread, msgs = _setup_agent_memory()

        mock_results = [
            {"id": msgs[1]["id"], "thread_id": thread["id"], "content": "Decorators"},
        ]
        mock_fts = mock_results[:]
        mock_vec = [(mock_results[0], 0.9)]

        with (
            patch(_HR, return_value=mock_results),
            patch(_FTS, return_value=mock_fts),
            patch(_VEC, return_value=mock_vec),
        ):
            result = orchestrated_recall(
                query="python",
                agent_id="agent-test01",
                thread_id=thread["id"],
                top_k=5,
                message_range=0,
            )

        # Should find KG entities matching "python"
        assert isinstance(result["related_entities"], list)
        assert isinstance(result["graph_context"], str)


class TestOrchestratedRecallAmbiguousPath:
    """When retrieval quality is moderate — augments with KG."""

    def test_augments_with_kg_on_ambiguous(self, isolated_db):
        thread, msgs = _setup_agent_memory()

        mock_results = [
            {"id": msgs[0]["id"], "thread_id": thread["id"], "content": "Tell me"},
        ]
        # Scores that produce ambiguous evaluation (max > 0.008, avg < 0.01)
        mock_fts = []  # No FTS results -> high default rank -> low RRF
        mock_vec = [(mock_results[0], 0.3)]  # Only vec rank 0

        with (
            patch(_HR, return_value=mock_results),
            patch(_FTS, return_value=mock_fts),
            patch(_VEC, return_value=mock_vec),
        ):
            result = orchestrated_recall(
                query="flask",
                agent_id="agent-test01",
                thread_id=thread["id"],
                top_k=5,
                message_range=0,
            )

        assert result["search_mode"] == "orchestrated"
        # Should have KG entities from the search
        entity_names = [e.get("name") for e in result["related_entities"]]
        assert isinstance(entity_names, list)

    def test_cross_thread_broadening_on_ambiguous(self, isolated_db):
        thread, msgs = _setup_agent_memory()
        # Create second thread
        thread2 = create_thread("agent-test01", "agent", "Thread 2")
        save_messages(
            thread2["id"],
            [{"role": "user", "content": "Cross-thread content about flask"}],
        )

        mock_results = [
            {"id": msgs[0]["id"], "thread_id": thread["id"], "content": "Tell me"},
        ]
        mock_fts = []
        mock_vec = [(mock_results[0], 0.3)]

        call_count = {"n": 0}

        def mock_hybrid_side_effect(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return mock_results
            # Second call is for cross-thread broadening — return empty
            return []

        with (
            patch(_HR, side_effect=mock_hybrid_side_effect),
            patch(_FTS, return_value=mock_fts),
            patch(_VEC, return_value=mock_vec),
        ):
            result = orchestrated_recall(
                query="flask",
                agent_id="agent-test01",
                thread_id=thread["id"],
                top_k=5,
                message_range=0,
                include_cross_thread=False,
            )

        assert result["count"] >= 1


class TestOrchestratedRecallIncorrectPath:
    """When retrieval quality is poor — falls back to recent messages."""

    def test_falls_back_to_recent_messages(self, isolated_db):
        thread, msgs = _setup_agent_memory()

        with (
            patch(_HR, return_value=[]),
            patch(_FTS, return_value=[]),
            patch(_VEC, return_value=[]),
        ):
            result = orchestrated_recall(
                query="nonexistent topic xyz",
                agent_id="agent-test01",
                thread_id=thread["id"],
                top_k=5,
                message_range=0,
            )

        assert result["retrieval_evaluation"] == "incorrect"
        assert result["relevance_score"] == 0.0
        # Should fall back to recent messages from the thread
        assert result["count"] > 0
        assert result["results"][0]["thread_id"] == thread["id"]

    def test_returns_empty_when_no_thread_and_no_results(self, isolated_db):
        _setup_agent_memory()

        with (
            patch(_HR, return_value=[]),
            patch(_FTS, return_value=[]),
            patch(_VEC, return_value=[]),
        ):
            result = orchestrated_recall(
                query="nonexistent topic xyz",
                agent_id="agent-test01",
                thread_id=None,
                top_k=5,
                message_range=0,
            )

        assert result["retrieval_evaluation"] == "incorrect"
        assert result["count"] == 0


class TestOrchestratedRecallEntityPromotion:
    """Entity promotion side effect when entities appear in results."""

    def test_promotes_entities_on_recall(self, isolated_db):
        thread, msgs = _setup_agent_memory()

        from app.db.knowledge_graph import get_entity

        # Get initial importance
        entity_before = get_entity("agent-test01", "python")
        initial_importance = entity_before["importance_score"]

        mock_results = [
            {"id": msgs[1]["id"], "thread_id": thread["id"], "content": "Decorators"},
        ]
        mock_fts = mock_results[:]
        mock_vec = [(mock_results[0], 0.9)]

        with (
            patch(_HR, return_value=mock_results),
            patch(_FTS, return_value=mock_fts),
            patch(_VEC, return_value=mock_vec),
        ):
            orchestrated_recall(
                query="python",
                agent_id="agent-test01",
                thread_id=thread["id"],
                top_k=5,
                message_range=0,
            )

        # Entity importance should have increased
        entity_after = get_entity("agent-test01", "python")
        assert entity_after["importance_score"] >= initial_importance


class TestOrchestratedRecallResilience:
    """Orchestrator should be resilient to partial failures."""

    def test_handles_kg_search_failure(self, isolated_db):
        thread, msgs = _setup_agent_memory()

        mock_results = [
            {"id": msgs[0]["id"], "thread_id": thread["id"], "content": "Test"},
        ]
        mock_fts = mock_results[:]
        mock_vec = [(mock_results[0], 0.9)]

        with (
            patch(_HR, return_value=mock_results),
            patch(_FTS, return_value=mock_fts),
            patch(_VEC, return_value=mock_vec),
            patch(_KG_SEARCH, side_effect=Exception("KG down")),
        ):
            result = orchestrated_recall(
                query="test",
                agent_id="agent-test01",
                thread_id=thread["id"],
                top_k=5,
                message_range=0,
            )

        # Should still return results even if KG fails
        assert result["count"] >= 1
        assert result["related_entities"] == []

    def test_handles_hybrid_recall_failure(self, isolated_db):
        thread, msgs = _setup_agent_memory()

        with (
            patch(_HR, side_effect=Exception("Search down")),
            patch(_FTS, return_value=[]),
            patch(_VEC, return_value=[]),
        ):
            result = orchestrated_recall(
                query="test",
                agent_id="agent-test01",
                thread_id=thread["id"],
                top_k=5,
                message_range=0,
            )

        # Should fall back gracefully (recent messages)
        assert result["search_mode"] == "orchestrated"
        assert result["retrieval_evaluation"] == "incorrect"


class TestRecallEndpointWithCRAG:
    """Test the recall endpoint integration with use_crag=True."""

    def test_recall_endpoint_routes_to_orchestrator(self, client, isolated_db):
        # Create an agent first
        resp = client.post(
            "/admin/agents",
            json={"name": "Test Agent", "description": "test"},
        )
        assert resp.status_code in (200, 201)
        agent_id = resp.get_json()["agent_id"]

        # Create a thread + messages
        thread = create_thread(agent_id, "agent", "Test")
        save_messages(
            thread["id"],
            [
                {"role": "user", "content": "Hello world"},
                {"role": "assistant", "content": "Hi there"},
            ],
        )

        # Call recall with use_crag=True
        resp = client.get(
            f"/admin/agents/{agent_id}/memory/recall",
            query_string={
                "q": "hello",
                "thread_id": thread["id"],
                "use_crag": "true",
                "top_k": 5,
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["search_mode"] == "orchestrated"
        assert "retrieval_evaluation" in data
        assert "related_entities" in data
        assert "graph_context" in data

    def test_recall_endpoint_without_crag_unchanged(self, client, isolated_db):
        resp = client.post(
            "/admin/agents",
            json={"name": "Test Agent 2", "description": "test"},
        )
        assert resp.status_code in (200, 201)
        agent_id = resp.get_json()["agent_id"]

        thread = create_thread(agent_id, "agent", "Test")
        save_messages(
            thread["id"],
            [{"role": "user", "content": "Hello world"}],
        )

        # Without use_crag, should use normal search_mode routing
        resp = client.get(
            f"/admin/agents/{agent_id}/memory/recall",
            query_string={
                "q": "hello",
                "thread_id": thread["id"],
                "search_mode": "fts",
                "top_k": 5,
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["search_mode"] == "fts"
        assert "retrieval_evaluation" not in data
