"""Vector embedding service using sentence-transformers for semantic search."""

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
