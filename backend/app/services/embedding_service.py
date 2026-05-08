"""Vector embedding service using sentence-transformers for semantic search.

Also owns the orchestration of embedding-based memory storage and recall.
The DB layer (`backend.app.db.agent_memory`) keeps only raw row I/O —
anything that needs to invoke the embedding model lives here so the DB
layer never imports a service (a layering rule the v0.7.0 knowledge-graph
analysis flagged as a violation).
"""

import json
import logging
import struct

logger = logging.getLogger(__name__)

# Module-level singleton — avoids 500ms cold start per request
_model = None
_MODEL_NAME = "all-MiniLM-L6-v2"
_DIMENSION = 384


def get_model():
    """Lazy-load the sentence-transformers model."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer(_MODEL_NAME)
            logger.info("Loaded embedding model: %s", _MODEL_NAME)
        except ImportError:
            logger.warning("sentence-transformers not installed — vector search disabled")
            return None
        except Exception as e:
            logger.error("Failed to load embedding model: %s", e)
            return None
    return _model


def is_available() -> bool:
    """Check if the embedding model can be loaded."""
    return get_model() is not None


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch embed texts. Returns list of float vectors."""
    model = get_model()
    if model is None:
        return []
    embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
    return [emb.tolist() for emb in embeddings]


def embed_text(text: str) -> list[float] | None:
    """Embed a single text. Returns float vector or None."""
    results = embed_texts([text])
    return results[0] if results else None


def serialize_embedding(embedding: list[float]) -> bytes:
    """Serialize embedding to bytes for SQLite BLOB storage."""
    return struct.pack(f"{len(embedding)}f", *embedding)


def deserialize_embedding(blob: bytes) -> list[float]:
    """Deserialize embedding from SQLite BLOB."""
    count = len(blob) // 4  # float32 = 4 bytes
    return list(struct.unpack(f"{count}f", blob))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors. Assumes normalized vectors."""
    # For normalized vectors, cosine similarity = dot product
    return sum(x * y for x, y in zip(a, b))


def cosine_similarity_batch(query: list[float], candidates: list[list[float]]) -> list[float]:
    """Compute cosine similarity between query and multiple candidates."""
    try:
        import numpy as np

        q = np.array(query, dtype=np.float32)
        c = np.array(candidates, dtype=np.float32)
        return (c @ q).tolist()
    except ImportError:
        # Fallback to pure Python
        return [cosine_similarity(query, cand) for cand in candidates]


# --- Embedding-backed memory orchestration ---
# Moved from db/agent_memory.py so the DB layer no longer imports a
# service. Both functions need the embedding model AND the DB; the
# service layer is the right home for that pairing.


def embed_and_store(message_id: str, content: str) -> str | None:
    """Generate embedding for a message and store it."""
    if not is_available():
        return None
    embedding = embed_text(content)
    if embedding is None:
        return None
    from ..db.connection import get_connection
    from ..db.ids import generate_embedding_id

    emb_id = generate_embedding_id()
    blob = serialize_embedding(embedding)
    with get_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO memory_embeddings
               (id, message_id, embedding, model, dimension)
               VALUES (?, ?, ?, 'all-MiniLM-L6-v2', 384)""",
            (emb_id, message_id, blob),
        )
        conn.commit()
    return emb_id


def vector_recall(
    query: str,
    resource_id: str | None = None,
    thread_id: str | None = None,
    resource_type: str = "agent",
    top_k: int = 5,
) -> list[tuple[dict, float]]:
    """Search memory using vector similarity. Returns (message, score) pairs."""
    if not is_available():
        return []
    query_embedding = embed_text(query)
    if query_embedding is None:
        return []

    from ..db.connection import get_connection

    col_names = [
        "id",
        "thread_id",
        "role",
        "content",
        "type",
        "metadata",
        "created_at",
    ]

    with get_connection() as conn:
        if thread_id:
            cursor = conn.execute(
                """SELECT m.id, m.thread_id, m.role, m.content, m.type,
                          m.metadata, m.created_at, e.embedding
                   FROM memory_embeddings e
                   JOIN memory_messages m ON m.id = e.message_id
                   WHERE m.thread_id = ?""",
                (thread_id,),
            )
        elif resource_id:
            cursor = conn.execute(
                """SELECT m.id, m.thread_id, m.role, m.content, m.type,
                          m.metadata, m.created_at, e.embedding
                   FROM memory_embeddings e
                   JOIN memory_messages m ON m.id = e.message_id
                   JOIN memory_threads t ON t.id = m.thread_id
                   WHERE t.resource_id = ? AND t.resource_type = ?""",
                (resource_id, resource_type),
            )
        else:
            return []

        rows = cursor.fetchall()
        if not rows:
            return []

        messages = []
        embeddings = []
        for row in rows:
            msg = dict(zip(col_names, row[:7]))
            if msg.get("metadata"):
                try:
                    msg["metadata"] = json.loads(msg["metadata"])
                except (json.JSONDecodeError, TypeError):
                    logger.warning(
                        "vector_recall: corrupt metadata JSON on message %s; "
                        "returning metadata=None. raw=%r",
                        msg.get("id"),
                        str(msg["metadata"])[:200],
                    )
                    msg["metadata"] = None
            messages.append(msg)
            embeddings.append(deserialize_embedding(row[7]))

        scores = cosine_similarity_batch(query_embedding, embeddings)
        scored = list(zip(messages, scores))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]


def hybrid_recall(
    query: str,
    resource_id: str | None = None,
    thread_id: str | None = None,
    resource_type: str = "agent",
    top_k: int = 5,
    message_range: int = 1,
    alpha: float = 0.4,
) -> list[dict]:
    """Hybrid recall using Reciprocal Rank Fusion of FTS5 + Vector search.

    RRF formula: score = alpha/(k + rank_fts) + (1-alpha)/(k + rank_vec)
    """
    from ..db.agent_memory import _expand_with_context, recall_messages

    K = 60  # RRF constant

    fts_results = recall_messages(
        thread_id=thread_id,
        query=query,
        resource_id=resource_id,
        resource_type=resource_type,
        top_k=top_k * 2,
        message_range=0,
    )

    vec_results = vector_recall(
        query=query,
        resource_id=resource_id,
        thread_id=thread_id,
        resource_type=resource_type,
        top_k=top_k * 2,
    )

    fts_ranks = {msg["id"]: rank for rank, msg in enumerate(fts_results)}
    vec_ranks = {msg["id"]: rank for rank, (msg, _score) in enumerate(vec_results)}

    all_msg_ids = set(fts_ranks.keys()) | set(vec_ranks.keys())
    msg_map: dict[str, dict] = {}
    for msg in fts_results:
        msg_map[msg["id"]] = msg
    for msg, _score in vec_results:
        if msg["id"] not in msg_map:
            msg_map[msg["id"]] = msg

    scored = []
    max_rank = top_k * 2 + 1
    for msg_id in all_msg_ids:
        fts_rank = fts_ranks.get(msg_id, max_rank)
        vec_rank = vec_ranks.get(msg_id, max_rank)
        rrf_score = alpha / (K + fts_rank) + (1 - alpha) / (K + vec_rank)
        scored.append((msg_map[msg_id], rrf_score))

    scored.sort(key=lambda x: x[1], reverse=True)
    results = [msg for msg, _score in scored[:top_k]]

    if message_range > 0 and results:
        return _expand_with_context(results, message_range)
    return results
