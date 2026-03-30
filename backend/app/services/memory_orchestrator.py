"""Memory orchestrator — CRAG-style self-correcting retrieval with KG augmentation."""

import logging
from typing import Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class RetrievalEvaluation(BaseModel):
    relevance: Literal["correct", "ambiguous", "incorrect"]
    confidence: float
    reasoning: str


def evaluate_retrieval_by_score(
    results: list[dict],
    scores: list[float],
) -> RetrievalEvaluation:
    """Evaluate retrieval quality using score-based thresholds (no LLM call).

    Uses percentile-based evaluation relative to the score distribution.
    """
    if not results or not scores:
        return RetrievalEvaluation(
            relevance="incorrect", confidence=0.0, reasoning="No results found"
        )

    max_score = max(scores)
    avg_score = sum(scores) / len(scores)

    # Percentile-based thresholds — RRF scores are small numbers
    if max_score > 0.015 and avg_score > 0.01:
        return RetrievalEvaluation(
            relevance="correct",
            confidence=min(1.0, max_score * 60),  # Normalize RRF to ~0-1
            reasoning=f"Top score {max_score:.4f}, avg {avg_score:.4f} — confident match",
        )
    elif max_score > 0.008:
        return RetrievalEvaluation(
            relevance="ambiguous",
            confidence=min(1.0, max_score * 60),
            reasoning=f"Top score {max_score:.4f} — moderate confidence, augmenting with KG",
        )
    else:
        return RetrievalEvaluation(
            relevance="incorrect",
            confidence=min(1.0, max_score * 60),
            reasoning=f"Top score {max_score:.4f} — low confidence, falling back",
        )


def orchestrated_recall(
    query: str,
    agent_id: str,
    thread_id: str | None = None,
    top_k: int = 5,
    message_range: int = 1,
    alpha: float = 0.4,
    use_crag: bool = False,
    graph_hops: int = 1,
    include_cross_thread: bool = False,
) -> dict:
    """Main orchestrated recall entry point with CRAG-style routing.

    Flow:
    1. Run hybrid retrieval (FTS5 + Vector via RRF)
    2. Evaluate retrieval quality (score-based)
    3. Route: correct -> return, ambiguous -> augment with KG, incorrect -> fallback
    4. Return enriched results
    """
    from ..db.agent_memory import (
        _expand_with_context,
        get_messages,
        hybrid_recall,
        recall_messages,
        vector_recall,
    )
    from ..db.knowledge_graph import (
        get_entity_context,
        promote_entity,
        search_entities,
        traverse_graph,
    )

    effective_thread_id = None if include_cross_thread else thread_id

    # Step 1: Hybrid retrieval
    try:
        results = hybrid_recall(
            query=query,
            resource_id=agent_id,
            thread_id=effective_thread_id,
            resource_type="agent",
            top_k=top_k,
            message_range=0,  # Expand later
            alpha=alpha,
        )
    except Exception:
        logger.warning("Hybrid recall failed, falling back to FTS", exc_info=True)
        results = []

    # Compute RRF scores for evaluation
    try:
        fts_results = recall_messages(
            thread_id=effective_thread_id,
            query=query,
            resource_id=agent_id,
            resource_type="agent",
            top_k=top_k * 2,
            message_range=0,
        )
        vec_results = vector_recall(
            query=query,
            resource_id=agent_id,
            thread_id=effective_thread_id,
            resource_type="agent",
            top_k=top_k * 2,
        )
    except Exception:
        logger.warning("Score computation retrieval failed", exc_info=True)
        fts_results = []
        vec_results = []

    K = 60
    fts_ranks = {msg["id"]: rank for rank, msg in enumerate(fts_results)}
    vec_ranks = {msg["id"]: rank for rank, (msg, _) in enumerate(vec_results)}
    max_rank = top_k * 2 + 1
    scores = []
    for msg in results:
        fts_r = fts_ranks.get(msg["id"], max_rank)
        vec_r = vec_ranks.get(msg["id"], max_rank)
        score = alpha / (K + fts_r) + (1 - alpha) / (K + vec_r)
        scores.append(score)

    # Step 2: Evaluate retrieval
    evaluation = evaluate_retrieval_by_score(results, scores)

    # Step 3: KG entity search for context
    related_entities: list[dict] = []
    graph_context = ""
    try:
        kg_entities = search_entities(agent_id, query, limit=5)
    except Exception:
        logger.warning("KG entity search failed", exc_info=True)
        kg_entities = []
    entity_names = [e["name"] for e in kg_entities]

    if evaluation.relevance == "correct":
        # Good results — just add light KG context
        related_entities = kg_entities[:3]
        if entity_names:
            try:
                graph_context = get_entity_context(agent_id, entity_names[:3])
            except Exception:
                pass
    elif evaluation.relevance == "ambiguous":
        # Moderate results — augment with KG traversal
        related_entities = kg_entities[:5]
        for entity_name in entity_names[:2]:
            try:
                subgraph = traverse_graph(agent_id, entity_name, hops=graph_hops)
                sub_names = [e["name"] for e in subgraph.get("entities", [])]
                graph_context = get_entity_context(agent_id, sub_names[:10])
            except Exception:
                pass

        # Also broaden search: try cross-thread if not already
        if not include_cross_thread and thread_id:
            try:
                cross_results = hybrid_recall(
                    query=query,
                    resource_id=agent_id,
                    thread_id=None,
                    resource_type="agent",
                    top_k=3,
                    message_range=0,
                    alpha=alpha,
                )
                existing_ids = {m["id"] for m in results}
                for msg in cross_results:
                    if msg["id"] not in existing_ids:
                        results.append(msg)
                        existing_ids.add(msg["id"])
            except Exception:
                pass
    else:
        # Poor results — fallback to recent messages + working memory
        related_entities = kg_entities
        if entity_names:
            try:
                graph_context = get_entity_context(agent_id, entity_names)
            except Exception:
                pass

        # Fallback: get recent messages from thread
        if thread_id:
            try:
                recent = get_messages(thread_id, limit=top_k)
                if recent and not results:
                    results = recent
            except Exception:
                pass

    # Step 4: Promote entities that appeared in results
    for entity in related_entities[:3]:
        try:
            promote_entity(entity["id"], boost=0.02)
        except Exception:
            pass

    # Expand with context
    if message_range > 0 and results:
        try:
            results = _expand_with_context(results, message_range)
        except Exception:
            pass

    return {
        "results": results[:top_k],
        "count": min(len(results), top_k),
        "query": query,
        "search_mode": "orchestrated",
        "relevance_score": round(evaluation.confidence, 4),
        "retrieval_evaluation": evaluation.relevance,
        "related_entities": related_entities,
        "graph_context": graph_context,
    }
