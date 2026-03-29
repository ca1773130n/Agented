"""Tests for the vector embedding and hybrid recall memory system."""

import struct
from unittest.mock import MagicMock, patch

import pytest

from app.db.agent_memory import (
    create_thread,
    embed_and_store,
    hybrid_recall,
    save_messages,
    vector_recall,
)
from app.services.embedding_service import (
    cosine_similarity,
    cosine_similarity_batch,
    deserialize_embedding,
    serialize_embedding,
)


class TestSerializeDeserialize:
    """Embedding serialization roundtrip tests."""

    def test_roundtrip_simple(self):
        vec = [1.0, 2.0, 3.0, 4.0]
        blob = serialize_embedding(vec)
        result = deserialize_embedding(blob)
        assert len(result) == 4
        for a, b in zip(vec, result):
            assert abs(a - b) < 1e-6

    def test_roundtrip_384_dim(self):
        vec = [float(i) / 384 for i in range(384)]
        blob = serialize_embedding(vec)
        assert len(blob) == 384 * 4  # float32 = 4 bytes
        result = deserialize_embedding(blob)
        assert len(result) == 384
        for a, b in zip(vec, result):
            assert abs(a - b) < 1e-6

    def test_empty_vector(self):
        vec: list[float] = []
        blob = serialize_embedding(vec)
        assert blob == b""
        result = deserialize_embedding(blob)
        assert result == []


class TestCosineSimilarity:
    """Cosine similarity computation tests."""

    def test_identical_vectors(self):
        vec = [0.5, 0.5, 0.5, 0.5]
        score = cosine_similarity(vec, vec)
        assert abs(score - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        score = cosine_similarity(a, b)
        assert abs(score) < 1e-6

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        score = cosine_similarity(a, b)
        assert abs(score - (-1.0)) < 1e-6

    def test_batch_similarity(self):
        query = [1.0, 0.0, 0.0]
        candidates = [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.5, 0.5, 0.0],
        ]
        scores = cosine_similarity_batch(query, candidates)
        assert len(scores) == 3
        assert abs(scores[0] - 1.0) < 1e-6  # identical
        assert abs(scores[1]) < 1e-6  # orthogonal
        assert scores[2] > 0  # partial match


def _mock_embed_text(text):
    """Create a deterministic fake embedding from text."""
    import hashlib

    h = hashlib.md5(text.encode()).digest()
    # Create a 384-dim vector from hash bytes, normalize it
    raw = [float(b) / 255.0 for b in h] * 24  # 16 * 24 = 384
    norm = sum(x * x for x in raw) ** 0.5
    return [x / norm for x in raw]


def _store_embeddings_for_messages(messages):
    """Helper to manually store embeddings for messages."""
    from app.db.connection import get_connection
    from app.db.ids import generate_embedding_id

    for msg in messages:
        emb = _mock_embed_text(msg["content"])
        blob = serialize_embedding(emb)
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO memory_embeddings
                   (id, message_id, embedding, model, dimension)
                   VALUES (?, ?, ?, 'all-MiniLM-L6-v2', 384)""",
                (generate_embedding_id(), msg["id"], blob),
            )
            conn.commit()


class TestEmbedAndStore:
    """Tests for embed_and_store with mocked embedding model."""

    @patch("app.services.embedding_service.is_available", return_value=True)
    @patch("app.services.embedding_service.embed_text", side_effect=_mock_embed_text)
    def test_embed_and_store_creates_record(
        self, mock_embed, mock_avail, isolated_db
    ):
        thread = create_thread("agent-test01", "agent", "Embed Test")
        msgs = save_messages(
            thread["id"],
            [{"role": "user", "content": "Hello world"}],
        )
        msg_id = msgs[0]["id"]
        emb_id = embed_and_store(msg_id, "Hello world")
        assert emb_id is not None
        assert emb_id.startswith("emb-")

    @patch("app.services.embedding_service.is_available", return_value=False)
    def test_embed_and_store_unavailable(self, mock_avail, isolated_db):
        result = embed_and_store("mmsg-fake", "test content")
        assert result is None


class TestVectorRecall:
    """Tests for vector_recall with mocked embedding model."""

    def _setup_data(self):
        """Helper to create test data with embeddings."""
        thread = create_thread("agent-vec01", "agent", "Vector Test")
        messages = save_messages(
            thread["id"],
            [
                {"role": "user", "content": "How do I deploy to production?"},
                {"role": "assistant", "content": "Use the deploy command."},
                {"role": "user", "content": "What about testing strategies?"},
                {"role": "assistant", "content": "Write unit and integration tests."},
            ],
        )
        _store_embeddings_for_messages(messages)
        return thread, messages

    @patch("app.services.embedding_service.is_available", return_value=True)
    @patch("app.services.embedding_service.embed_text", side_effect=_mock_embed_text)
    def test_vector_recall_by_thread(self, mock_embed, mock_avail, isolated_db):
        thread, messages = self._setup_data()
        results = vector_recall(
            query="deploy production",
            thread_id=thread["id"],
            top_k=2,
        )
        assert len(results) > 0
        assert len(results) <= 2
        # Each result is (message_dict, score)
        for msg, score in results:
            assert "id" in msg
            assert "content" in msg
            assert isinstance(score, float)

    @patch("app.services.embedding_service.is_available", return_value=True)
    @patch("app.services.embedding_service.embed_text", side_effect=_mock_embed_text)
    def test_vector_recall_by_resource(self, mock_embed, mock_avail, isolated_db):
        thread, messages = self._setup_data()
        results = vector_recall(
            query="testing",
            resource_id="agent-vec01",
            resource_type="agent",
            top_k=3,
        )
        assert len(results) > 0

    @patch("app.services.embedding_service.is_available", return_value=False)
    def test_vector_recall_unavailable(self, mock_avail, isolated_db):
        results = vector_recall(query="test", resource_id="agent-test01")
        assert results == []

    @patch("app.services.embedding_service.is_available", return_value=True)
    @patch("app.services.embedding_service.embed_text", side_effect=_mock_embed_text)
    def test_vector_recall_no_params(self, mock_embed, mock_avail, isolated_db):
        results = vector_recall(query="test")
        assert results == []


class TestHybridRecall:
    """Tests for hybrid_recall RRF scoring."""

    @patch("app.services.embedding_service.is_available", return_value=True)
    @patch("app.services.embedding_service.embed_text", side_effect=_mock_embed_text)
    def test_hybrid_recall_combines_results(self, mock_embed, mock_avail, isolated_db):
        thread = create_thread("agent-hyb01", "agent", "Hybrid Test")
        messages = save_messages(
            thread["id"],
            [
                {"role": "user", "content": "How do I deploy to production?"},
                {"role": "assistant", "content": "Use the deploy command."},
                {"role": "user", "content": "What about testing strategies?"},
            ],
        )
        _store_embeddings_for_messages(messages)

        results = hybrid_recall(
            query="deploy",
            resource_id="agent-hyb01",
            resource_type="agent",
            top_k=3,
            message_range=0,
            alpha=0.4,
        )
        assert isinstance(results, list)
        for msg in results:
            assert isinstance(msg, dict)
            assert "id" in msg

    @patch("app.services.embedding_service.is_available", return_value=True)
    @patch("app.services.embedding_service.embed_text", side_effect=_mock_embed_text)
    def test_hybrid_recall_with_context_expansion(
        self, mock_embed, mock_avail, isolated_db
    ):
        thread = create_thread("agent-hyb02", "agent", "Context Test")
        messages = save_messages(
            thread["id"],
            [
                {"role": "user", "content": "First message about deployment"},
                {"role": "assistant", "content": "Deploying is straightforward"},
                {"role": "user", "content": "Second message about testing"},
            ],
        )
        _store_embeddings_for_messages(messages)

        results = hybrid_recall(
            query="deployment",
            resource_id="agent-hyb02",
            resource_type="agent",
            top_k=2,
            message_range=1,
        )
        assert isinstance(results, list)


class TestRecallEndpoint:
    """Tests for the updated /recall endpoint with search_mode parameter."""

    def _create_agent(self, client, name="Test Agent"):
        resp = client.post(
            "/admin/agents/",
            json={"name": name, "description": "Test"},
        )
        return resp.get_json()["agent_id"]

    def test_recall_fts_mode(self, client, isolated_db):
        agent_id = self._create_agent(client, "Recall FTS Agent")

        resp = client.post(
            f"/admin/agents/{agent_id}/memory/threads", json={}
        )
        thread_id = resp.get_json()["id"]
        client.post(
            f"/admin/agents/{agent_id}/memory/threads/{thread_id}/messages",
            json={
                "messages": [
                    {"role": "user", "content": "Tell me about deployment pipelines"},
                ]
            },
        )

        resp = client.get(
            f"/admin/agents/{agent_id}/memory/recall"
            f"?q=deployment&search_mode=fts"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["search_mode"] == "fts"
        assert "relevance_score" in data

    def test_recall_vector_mode(self, client, isolated_db):
        agent_id = self._create_agent(client, "Vec Recall Agent")

        with patch(
            "app.db.agent_memory.vector_recall", return_value=[]
        ):
            resp = client.get(
                f"/admin/agents/{agent_id}/memory/recall"
                f"?q=test&search_mode=vector"
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["search_mode"] == "vector"
        assert data["count"] == 0

    def test_recall_hybrid_mode(self, client, isolated_db):
        agent_id = self._create_agent(client, "Hybrid Recall Agent")

        with patch(
            "app.db.agent_memory.hybrid_recall", return_value=[]
        ):
            resp = client.get(
                f"/admin/agents/{agent_id}/memory/recall"
                f"?q=test&search_mode=hybrid&alpha=0.5"
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["search_mode"] == "hybrid"

    def test_recall_default_is_hybrid(self, client, isolated_db):
        agent_id = self._create_agent(client, "Default Mode Agent")

        with patch(
            "app.db.agent_memory.hybrid_recall", return_value=[]
        ):
            resp = client.get(
                f"/admin/agents/{agent_id}/memory/recall?q=test"
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["search_mode"] == "hybrid"
