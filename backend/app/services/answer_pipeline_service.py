"""AnswerPipelineService — agentic RAG pipeline for leader chat answers.

Architecture
------------
gather_context(project_id, turn, ...) implements a planner → multi-source
fanout → sufficiency loop → grounded-context assembly pipeline.

Key design choices:
- llm_call is the test seam (injected callable). When None, _default_llm_call
  is built from backend/account_email using stream_llm_response.
- Fanout uses ThreadPoolExecutor with REAL deadline mechanics:
    wait(futures, timeout=remaining) + executor.shutdown(wait=False, cancel_futures=True)
- Tesserae fires ONLY when remaining_seconds > 25 AND tesserae_root is set
  AND the kg-signal cache pass produced nothing relevant.
  With chat's 20s default this NEVER fires (intentional; see docstring).
- All retrievers are try/except → empty list (fail-open per source).
- Project scoping is mandatory: _project_execution_ids JOIN enforces isolation.

Tesserae latency note
---------------------
With deadline_seconds=20 (chat default), ask_tesserae (60s subprocess) never
runs in a live leader turn. Chat relies on cached harness_kg_signals answers
(which Tesserae populated offline). Live Tesserae fires only when the caller
passes deadline_seconds >= 90 (e.g. the eval pipeline arm).
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Maximum sub-queries the planner may produce.
_MAX_PLAN_QUERIES = 4

# Tesserae minimum remaining budget threshold (seconds).
_TESSERAE_MIN_REMAINING = 25.0

# Regex for extracting the first [...] array blob from prose (greedy, outermost).
_ARRAY_BLOB_RE = re.compile(r"\[[\s\S]*\]")

# Regex for extracting the first {...} object blob from prose (greedy, outermost).
_OBJ_BLOB_RE = re.compile(r"\{[\s\S]*\}")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class RetrievedChunk:
    text: str
    source: str  # 'kg_signal'|'execution_log'|'takeaway'|'finding'|'verification'|'tesserae'
    provenance_key: str  # e.g. 'execution:exec-...' | 'signal:<id>' | 'takeaway:<id>'
    score: float = 0.0


LLMCall = Callable[[list[dict]], str]  # messages -> collected text


# ---------------------------------------------------------------------------
# LLM call wrapper
# ---------------------------------------------------------------------------


def _default_llm_call(
    backend: str = "claude",
    account_email: Optional[str] = None,
) -> LLMCall:
    """Build the default LLM call from stream_llm_response with str-filter."""

    def _call(messages: list[dict]) -> str:
        from app.services.conversation_streaming import stream_llm_response

        chunks = stream_llm_response(
            messages,
            backend=backend,
            account_email=account_email,
        )
        return "".join(chunk for chunk in chunks if isinstance(chunk, str))

    return _call


# ---------------------------------------------------------------------------
# Forgiving parsers (mirror goal_judge_service._parse_judge_json style)
# ---------------------------------------------------------------------------


def _parse_plan(text: str, fallback_turn: str = "") -> list[dict]:
    """Parse a JSON array of sub-queries from the planner output.

    Forgiving: tries the first [...] blob in the text; on failure falls back
    to [{"query": fallback_turn, "sources": ["all"]}]. Truncates to 4 queries.
    """
    if not isinstance(text, str):
        return [{"query": fallback_turn, "sources": ["all"]}]

    for match in _ARRAY_BLOB_RE.finditer(text):
        try:
            blob = json.loads(match.group(0))
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(blob, list):
            continue
        queries = []
        for item in blob:
            if isinstance(item, dict) and "query" in item:
                queries.append(item)
        if queries:
            return queries[:_MAX_PLAN_QUERIES]

    # Garbage fallback
    return [{"query": fallback_turn, "sources": ["all"]}]


def _parse_sufficiency(text: str) -> dict:
    """Parse the sufficiency check JSON from the LLM.

    Forgiving: tries the first {...} blob; on failure fails OPEN
    (sufficient=True so the pipeline proceeds rather than loops forever).
    """
    if not isinstance(text, str):
        return {"sufficient": True, "gap": None, "feedback": ""}

    for match in _OBJ_BLOB_RE.finditer(text):
        try:
            blob = json.loads(match.group(0))
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(blob, dict) or "sufficient" not in blob:
            continue
        return {
            "sufficient": bool(blob.get("sufficient", True)),
            "gap": blob.get("gap") or None,
            "feedback": str(blob.get("feedback") or ""),
        }

    # Fail-open
    return {"sufficient": True, "gap": None, "feedback": ""}


# ---------------------------------------------------------------------------
# Project scoping
# ---------------------------------------------------------------------------


def _project_execution_ids(project_id: str) -> set[str]:
    """Return the set of execution_ids belonging to a project.

    Uses the project_paths JOIN to enforce project isolation — the raw
    execution_logs table is cross-project (no project_id column).
    """
    from app.db.connection import get_connection

    try:
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT e.execution_id
                   FROM execution_logs e
                   JOIN project_paths p ON p.trigger_id = e.trigger_id
                   WHERE p.project_id = ?""",
                (project_id,),
            ).fetchall()
        return {r["execution_id"] for r in rows}
    except Exception:
        logger.debug("_project_execution_ids failed for %s", project_id, exc_info=True)
        return set()


# ---------------------------------------------------------------------------
# Retriever functions (fail-open per source)
# ---------------------------------------------------------------------------


def _search_kg_signals(project_id: str, query: str, *, limit: int = 5) -> list[RetrievedChunk]:
    """Search kg_signals — already project-keyed."""
    try:
        from app.db.harness_kg_signals import list_signals

        signals = list_signals(project_id, limit=50)
        query_lower = query.lower()
        scored = []
        for sig in signals:
            text = f"{sig.get('question', '')} {sig.get('content', '')}"
            score = sum(1 for word in query_lower.split() if word in text.lower())
            scored.append((score, sig))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            RetrievedChunk(
                text=f"{s.get('question', '')} — {s.get('content', '')}",
                source="kg_signal",
                provenance_key=f"signal:{s['signal_id']}",
                score=float(score),
            )
            for score, s in scored[:limit]
            if score > 0 or len(scored) <= limit
        ][:limit]
    except Exception:
        logger.debug("_search_kg_signals failed", exc_info=True)
        return []


def _search_execution_logs(project_id: str, query: str, *, limit: int = 5) -> list[RetrievedChunk]:
    """Search execution logs FTS, post-filtered by project_execution_ids."""
    try:
        from app.services.execution_search_service import ExecutionSearchService

        allowed_ids = _project_execution_ids(project_id)
        if not allowed_ids:
            return []

        hits = ExecutionSearchService.search(query, limit=limit * 3)
        chunks = []
        for hit in hits:
            eid = hit.get("execution_id", "")
            if eid not in allowed_ids:
                continue
            text = hit.get("stdout_match") or hit.get("prompt") or ""
            chunks.append(
                RetrievedChunk(
                    text=text,
                    source="execution_log",
                    provenance_key=f"execution:{eid}",
                    score=0.5,
                )
            )
            if len(chunks) >= limit:
                break
        return chunks
    except Exception:
        logger.debug("_search_execution_logs failed", exc_info=True)
        return []


def _search_takeaways(project_id: str, query: str, *, limit: int = 5) -> list[RetrievedChunk]:
    """Search session_takeaways — already project-keyed."""
    try:
        from app.db.harness_takeaways import list_for_project

        takeaways = list_for_project(project_id, limit=50)
        query_lower = query.lower()
        scored = []
        for tk in takeaways:
            text = tk.get("content", "")
            score = sum(1 for word in query_lower.split() if word in text.lower())
            scored.append((score, tk))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            RetrievedChunk(
                text=s.get("content", ""),
                source="takeaway",
                provenance_key=f"takeaway:{s['id']}",
                score=float(score),
            )
            for score, s in scored[:limit]
            if score > 0 or len(scored) <= limit
        ][:limit]
    except Exception:
        logger.debug("_search_takeaways failed", exc_info=True)
        return []


def _search_findings(project_id: str, query: str, *, limit: int = 5) -> list[RetrievedChunk]:
    """Search findings, filtered to project's execution_ids."""
    try:
        from app.db.findings import list_findings

        allowed_ids = _project_execution_ids(project_id)
        # list_findings has no project filter — post-filter by execution_id
        all_findings = list_findings()
        query_lower = query.lower()
        chunks = []
        for f in all_findings:
            eid = f.get("execution_id")
            if eid is not None and eid not in allowed_ids:
                continue
            text = f"{f.get('title', '')} {f.get('description', '')}"
            score = sum(1 for word in query_lower.split() if word in text.lower())
            if score > 0 or not allowed_ids:
                chunks.append(
                    RetrievedChunk(
                        text=text.strip(),
                        source="finding",
                        provenance_key=f"finding:{f['id']}",
                        score=float(score),
                    )
                )
        chunks.sort(key=lambda c: c.score, reverse=True)
        return chunks[:limit]
    except Exception:
        logger.debug("_search_findings failed", exc_info=True)
        return []


def _search_verifications(project_id: str, query: str, *, limit: int = 5) -> list[RetrievedChunk]:
    """Search verification_records for the project's recent executions."""
    try:
        from app.db.verification_records import list_verifications

        allowed_ids = _project_execution_ids(project_id)
        if not allowed_ids:
            return []

        # Cap to most recent ~10 execution_ids
        recent_ids = sorted(allowed_ids)[-10:]
        query_lower = query.lower()
        chunks = []
        for eid in recent_ids:
            try:
                verifs = list_verifications(eid)
            except Exception:
                continue
            for v in verifs:
                text = f"{v.get('claim', '')} {v.get('evidence_ref', '') or ''}"
                score = sum(1 for word in query_lower.split() if word in text.lower())
                chunks.append(
                    RetrievedChunk(
                        text=text.strip(),
                        source="verification",
                        provenance_key=f"verification:{v['id']}",
                        score=float(score),
                    )
                )
        chunks.sort(key=lambda c: c.score, reverse=True)
        return chunks[:limit]
    except Exception:
        logger.debug("_search_verifications failed", exc_info=True)
        return []


def _ask_tesserae_raw(project_id: str, question: str, *, top_k: int = 5) -> Optional[str]:
    """Thin wrapper around tesserae_integration.ask_tesserae — injectable for tests."""
    from app.services.tesserae_integration import ask_tesserae

    return ask_tesserae(project_id, question, top_k=top_k)


def _ask_tesserae_budgeted(
    *,
    project_id: str,
    query: str,
    tesserae_root: Optional[str],
    budget_state: dict,
    tesserae_budget: int,
    remaining_seconds: float,
) -> list[RetrievedChunk]:
    """Conditionally call Tesserae respecting budget and time constraints.

    Fires ONLY when:
    - remaining_seconds > _TESSERAE_MIN_REMAINING (25s)
    - budget_state["used"] < tesserae_budget
    - tesserae_root is set (project has Tesserae compiled)
    """
    if remaining_seconds <= _TESSERAE_MIN_REMAINING:
        return []
    if budget_state.get("used", 0) >= tesserae_budget:
        return []
    if not tesserae_root:
        return []

    try:
        result = _ask_tesserae_raw(project_id, query)
        budget_state["used"] = budget_state.get("used", 0) + 1
        if result is None:
            return []
        return [
            RetrievedChunk(
                text=result,
                source="tesserae",
                provenance_key=f"tesserae:({project_id},{query[:50]})",
                score=0.8,
            )
        ]
    except Exception:
        logger.debug("_ask_tesserae_budgeted failed", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Tesserae root helper
# ---------------------------------------------------------------------------


def _get_project_tesserae_root(project_id: str) -> Optional[str]:
    """Return the tesserae_project_root for the project, or None."""
    try:
        from app.services.tesserae_integration import get_tesserae_root

        root = get_tesserae_root(project_id)
        return str(root) if root else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# gather_context — main pipeline
# ---------------------------------------------------------------------------


def gather_context(
    project_id: str,
    turn: str,
    *,
    backend: str = "claude",
    account_email: Optional[str] = None,
    llm_call: Optional[LLMCall] = None,
    max_iterations: int = 2,
    tesserae_budget: int = 1,
    deadline_seconds: float = 20,
) -> dict:
    """Agentic RAG pipeline: planner → fanout → sufficiency loop.

    Parameters
    ----------
    project_id:         Project scope for all retrievers.
    turn:               The user's question/turn text.
    backend:            LLM backend (default 'claude').
    account_email:      Account email for CLIProxy routing.
    llm_call:           Test seam — callable(messages) -> str. When None,
                        built from backend/account_email via _default_llm_call.
    max_iterations:     Maximum plan→fanout→sufficiency rounds (default 2).
    tesserae_budget:    Max Tesserae calls per gather_context invocation.
    deadline_seconds:   Wall-clock budget for the entire pipeline (default 20s).

    Returns
    -------
    {
        chunks: list[RetrievedChunk],
        context_message: dict | None,  # system message to insert before last user turn
        iterations: int,
        sufficient: bool,
        gap: str | None,
    }
    """
    start = time.monotonic()

    if llm_call is None:
        llm_call = _default_llm_call(backend=backend, account_email=account_email)

    all_chunks: list[RetrievedChunk] = []
    gap: Optional[str] = None
    sufficient = False
    feedback: str = ""
    tesserae_root = _get_project_tesserae_root(project_id)
    budget_state: dict = {"used": 0}

    for iteration in range(1, max_iterations + 1):
        elapsed = time.monotonic() - start
        remaining = deadline_seconds - elapsed
        if remaining <= 0:
            break

        # Step 1: Plan
        plan_prompt = _build_plan_prompt(turn, feedback=feedback if iteration > 1 else "")
        try:
            plan_text = llm_call([{"role": "user", "content": plan_prompt}])
        except Exception:
            logger.debug("planner llm_call failed on iteration %d", iteration, exc_info=True)
            plan_text = ""

        queries = _parse_plan(plan_text, fallback_turn=turn)

        # Step 2: Fanout — submit all retrievers concurrently
        elapsed = time.monotonic() - start
        remaining = deadline_seconds - elapsed
        if remaining <= 0:
            break

        iter_chunks = _fanout(
            project_id=project_id,
            queries=queries,
            remaining_seconds=remaining,
            tesserae_root=tesserae_root,
            budget_state=budget_state,
            tesserae_budget=tesserae_budget,
            kg_has_results=bool(all_chunks),
        )

        # Merge + dedupe by provenance_key
        seen_keys: set[str] = {c.provenance_key for c in all_chunks}
        for chunk in iter_chunks:
            if chunk.provenance_key not in seen_keys:
                all_chunks.append(chunk)
                seen_keys.add(chunk.provenance_key)

        # Step 3: Sufficiency check
        elapsed = time.monotonic() - start
        remaining = deadline_seconds - elapsed
        if remaining <= 0:
            break

        suf_prompt = _build_sufficiency_prompt(turn, all_chunks)
        try:
            suf_text = llm_call([{"role": "user", "content": suf_prompt}])
        except Exception:
            logger.debug("sufficiency llm_call failed on iteration %d", iteration, exc_info=True)
            suf_text = ""

        suf = _parse_sufficiency(suf_text)
        sufficient = suf["sufficient"]
        gap = suf.get("gap")
        feedback = suf.get("feedback", "")

        if sufficient:
            break

    # Build context message
    context_message = _build_context_message(all_chunks, sufficient=sufficient, gap=gap)

    return {
        "chunks": all_chunks,
        "context_message": context_message,
        "iterations": iteration,  # noqa: F821 — always assigned by loop
        "sufficient": sufficient,
        "gap": gap,
    }


# ---------------------------------------------------------------------------
# Fanout execution
# ---------------------------------------------------------------------------


def _fanout(
    *,
    project_id: str,
    queries: list[dict],
    remaining_seconds: float,
    tesserae_root: Optional[str],
    budget_state: dict,
    tesserae_budget: int,
    kg_has_results: bool,
) -> list[RetrievedChunk]:
    """Submit all retriever futures and wait up to remaining_seconds."""
    futures_map: dict[concurrent.futures.Future, str] = {}
    results: list[RetrievedChunk] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        for q in queries:
            query_text = q.get("query", "")
            sources = q.get("sources", ["all"])
            if not isinstance(sources, list):
                sources = ["all"]
            use_all = "all" in sources

            if use_all or "kg_signal" in sources:
                f = executor.submit(_search_kg_signals, project_id, query_text)
                futures_map[f] = "kg_signal"

            if use_all or "execution_log" in sources:
                f = executor.submit(_search_execution_logs, project_id, query_text)
                futures_map[f] = "execution_log"

            if use_all or "takeaway" in sources:
                f = executor.submit(_search_takeaways, project_id, query_text)
                futures_map[f] = "takeaway"

            if use_all or "finding" in sources:
                f = executor.submit(_search_findings, project_id, query_text)
                futures_map[f] = "finding"

            if use_all or "verification" in sources:
                f = executor.submit(_search_verifications, project_id, query_text)
                futures_map[f] = "verification"

            # Tesserae: only when budget allows, time allows, and kg cache empty
            if (use_all or "tesserae" in sources) and not kg_has_results:
                f = executor.submit(
                    _ask_tesserae_budgeted,
                    project_id=project_id,
                    query=query_text,
                    tesserae_root=tesserae_root,
                    budget_state=budget_state,
                    tesserae_budget=tesserae_budget,
                    remaining_seconds=remaining_seconds,
                )
                futures_map[f] = "tesserae"

        # Wait with deadline
        done, not_done = concurrent.futures.wait(
            list(futures_map.keys()), timeout=max(remaining_seconds - 0.5, 0.1)
        )
        # Cancel unfinished futures
        executor.shutdown(wait=False, cancel_futures=True)

        for future in done:
            try:
                chunks = future.result()
                if chunks:
                    results.extend(chunks)
            except Exception:
                logger.debug("fanout future failed", exc_info=True)

    return results


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def _build_plan_prompt(turn: str, *, feedback: str = "") -> str:
    base = (
        "You are a search planner. Given a user question, produce ≤4 targeted sub-queries "
        "to retrieve relevant context. Each sub-query must be a JSON object with keys "
        '"query" (string) and "sources" (array, subset of: kg_signal, execution_log, '
        "takeaway, finding, verification, tesserae, all). "
        "Return ONLY a JSON array of sub-query objects, no prose.\n\n"
        f"User question: {turn}"
    )
    if feedback:
        base += f"\n\nPrevious retrieval was insufficient. Additional guidance: {feedback}"
    return base


def _build_sufficiency_prompt(turn: str, chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        chunk_text = "(no context retrieved)"
    else:
        lines = []
        for i, c in enumerate(chunks, 1):
            lines.append(f"[F{i}] ({c.source}, {c.provenance_key}) {c.text[:300]}")
        chunk_text = "\n".join(lines)

    return (
        "You are evaluating whether retrieved context is sufficient to answer a question.\n\n"
        f"Question: {turn}\n\n"
        f"Retrieved context:\n{chunk_text}\n\n"
        "Return a JSON object with keys:\n"
        '  "sufficient": true/false — whether the context is enough to answer the question\n'
        '  "gap": string or null — what key information is still missing\n'
        '  "feedback": string — guidance for a follow-up retrieval pass\n\n'
        "Return ONLY the JSON object, no prose."
    )


# ---------------------------------------------------------------------------
# Context message builder
# ---------------------------------------------------------------------------


def _build_context_message(
    chunks: list[RetrievedChunk],
    *,
    sufficient: bool,
    gap: Optional[str],
) -> Optional[dict]:
    """Build the system context message to insert before the final user turn.

    Returns None when there are no chunks (nothing to provide).
    """
    if not chunks:
        return None

    lines = [
        "The following context was retrieved from project sources to help answer the question.",
        "Cite sources using [F<n>] markers in your response where applicable.\n",
    ]
    for i, c in enumerate(chunks, 1):
        lines.append(f"[F{i}] ({c.source}, {c.provenance_key}) {c.text[:500]}")

    if not sufficient and gap:
        lines.append(f"\nNote: context may be partial — {gap}")

    lines.append(
        "\nWhen referencing information from the above, use inline [F<n>] citation markers."
    )

    return {
        "role": "system",
        "content": "\n".join(lines),
    }


# ---------------------------------------------------------------------------
# extract_facts_from_answer
# ---------------------------------------------------------------------------


def extract_facts_from_answer(
    answer_text: str,
    chunks: list[RetrievedChunk],
    *,
    llm_call: LLMCall,
) -> list[dict]:
    """Extract factual claims from an answer with provenance mapping.

    The LLM returns a JSON list of {claim, fact_ids: [F1, F2, ...], confidence}.
    fact_ids are mapped back to chunk provenance into evidence lists.

    Returns [] on any failure (forgiving parse).
    """
    if not chunks or not answer_text:
        return []

    # Build numbered chunk index
    chunk_index: dict[str, RetrievedChunk] = {f"F{i}": c for i, c in enumerate(chunks, 1)}
    chunk_summary = "\n".join(
        f"[F{i}] ({c.source}, {c.provenance_key}) {c.text[:200]}" for i, c in enumerate(chunks, 1)
    )

    prompt = (
        "You are extracting factual claims from an AI assistant answer.\n\n"
        f"Answer:\n{answer_text}\n\n"
        f"Source chunks:\n{chunk_summary}\n\n"
        "Return a JSON array of objects, each with:\n"
        '  "claim": string — a single factual claim from the answer\n'
        '  "fact_ids": array of strings — [F1, F2, ...] chunk IDs that support this claim\n'
        '  "confidence": number 0.0-1.0 — how confident you are in this claim\n\n'
        "Return ONLY the JSON array, no prose."
    )

    try:
        response = llm_call([{"role": "user", "content": prompt}])
    except Exception:
        logger.debug("extract_facts_from_answer llm_call failed", exc_info=True)
        return []

    # Forgiving parse — find first [...] blob
    for match in _ARRAY_BLOB_RE.finditer(response or ""):
        try:
            blob = json.loads(match.group(0))
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(blob, list):
            continue

        facts = []
        for item in blob:
            if not isinstance(item, dict) or "claim" not in item:
                continue
            fact_ids = item.get("fact_ids") or []
            if isinstance(fact_ids, str):
                fact_ids = [fact_ids]
            evidence = []
            for fid in fact_ids:
                chunk = chunk_index.get(str(fid))
                if chunk:
                    evidence.append(
                        {
                            "source": chunk.source,
                            "provenance_key": chunk.provenance_key,
                            "text_snippet": chunk.text[:150],
                        }
                    )
            facts.append(
                {
                    "claim": str(item["claim"]),
                    "evidence": evidence,
                    "confidence": float(item.get("confidence", 0.5)),
                }
            )
        return facts

    return []
