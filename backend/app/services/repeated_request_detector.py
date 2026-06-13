"""Repeated-request detector (Phase 22, REQ-23).

A NEW session-completion handler — registered as a THIRD
``register_session_handler`` callback at module import, mirroring
``harness_failure_annotator.py:14-16``. It does NOT edit
``on_session_complete``; non-blocking is already guaranteed by
``emit_session_complete``'s per-handler try/except
(``execution_events.py:60``).

For every completed session of all five kinds it:
  1. Fetches the session payload via the annotator's ``_FETCHERS`` map.
  2. Extracts the user-request turn text from the payload jsonl (the
     ``{"type": "user", ...}`` text blocks — NOT tool_result blocks, which
     ``parse_claude_stream`` already special-cases).
  3. Embeds the request and cosine-matches (>= ``_COSINE_MATCH_THRESHOLD``)
     against existing signal embeddings for the project. A match UPSERTs
     onto the matched signal's ``request_hash``; otherwise a brand-new
     signal keyed by ``normalize_request_hash(text)`` is created.
  4. When ``embed_text`` returns None (sentence-transformers absent — the
     EVAL A1 fallback), it UPSERTs keyed by the exact ``normalize_request_hash``
     so verbatim repeats still coalesce while paraphrases stay separate.

This turns raw session completions into a growing, deduplicated signal
stream that 22-05's gate consumes.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from app.db.repeated_request_signals import (
    list_signals,
    normalize_request_hash,
    upsert_signal,
)
from app.services.embedding_service import cosine_similarity_batch, embed_text
from app.services.harness_failure_annotator import _FETCHERS

logger = logging.getLogger(__name__)

# Phase-22 design constant: minimum cosine similarity (normalized MiniLM
# vectors) for a new request to coalesce onto an existing signal instead of
# spawning a new one. This is NOT an existing codebase value — it is
# introduced by Phase 22 and tuned against the paraphrase fixtures (EVAL P1).
_COSINE_MATCH_THRESHOLD = 0.83

# Upper bound on signals pulled into a single cosine match. The store returns
# rows most-salient-first (occurrence_count, then recency), so the cap keeps the
# strongest candidates while bounding the work done on the session-completion
# bus thread as the signal table grows.
_MATCH_CANDIDATE_LIMIT = 500


def _extract_user_request_text(payload_text: str) -> str:
    """Pull genuine user-request turns out of the payload's claude-jsonl.

    The fetchers normalize every session kind into the claude-jsonl shape
    (``{"type": "user", "message": {"content": [...]}}``). We collect only
    the ``text`` blocks under ``type == "user"`` — these are the operator's
    requests. ``tool_result`` blocks (which Claude also nests under user
    events) are skipped so tool plumbing never pollutes the signal text.
    """
    parts: list[str] = []
    for line in (payload_text or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if obj.get("type") != "user":
            continue
        for block in (obj.get("message") or {}).get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text = block.get("text")
                if text:
                    parts.append(str(text))
    return "\n".join(parts).strip()


def _match_existing(
    emb: list[float],
    project_id: Optional[str],
) -> Optional[str]:
    """Return the request_hash of the best signal whose embedding cosine-matches
    ``emb`` at or above the threshold, or None if there is no such signal."""
    signals = list_signals(project_id=project_id, limit=_MATCH_CANDIDATE_LIMIT)
    if project_id is None:
        # list_signals(project_id=None) is unfiltered; a project-less session
        # must not coalesce onto (and mutate) another project's signal.
        signals = [s for s in signals if s.project_id is None]
    candidates = [s for s in signals if s.embedding is not None]
    if not candidates:
        return None
    scores = cosine_similarity_batch(emb, [s.embedding for s in candidates])  # type: ignore[arg-type]
    best_idx = max(range(len(scores)), key=lambda i: scores[i])
    if scores[best_idx] >= _COSINE_MATCH_THRESHOLD:
        return candidates[best_idx].request_hash
    return None


def detect_for_session(
    session_kind: str,
    session_id: str,
    project_id: Optional[str],
) -> None:
    """Extract the user request from a completed session, embed + cosine-match
    it against existing signals, and UPSERT into the 22-01 store.

    Best-effort: callers (the bus) isolate exceptions, but the guards here keep
    the common no-op paths (unknown kind, missing payload, empty request) cheap
    and crash-free.
    """
    fetcher = _FETCHERS.get(session_kind)
    if fetcher is None:
        return
    payload = fetcher(session_id)
    if payload is None:
        return

    text = _extract_user_request_text(payload.text)
    if not text:
        return

    resolved_project_id = project_id or payload.project_id

    emb = embed_text(text)
    if emb is not None:
        matched_hash = _match_existing(emb, resolved_project_id)
        request_hash = matched_hash or normalize_request_hash(text)
    else:
        # EVAL A1 fallback: no embedding backend -> exact-hash match only.
        request_hash = normalize_request_hash(text)

    upsert_signal(
        request_hash=request_hash,
        project_id=resolved_project_id,
        session_kind=session_kind,
        representative_text=text,
        embedding=emb,
        session_id=session_id,
    )


def on_session_complete_detect(
    session_kind: str,
    session_id: str,
    project_id: Optional[str],
    status: str,
    output: Optional[dict],
) -> None:
    """``register_session_handler`` callback. Named distinctly so it does not
    collide with the annotator/extractor ``on_session_complete``."""
    detect_for_session(session_kind, session_id, project_id)


# Self-register on the session-completion bus at import (mirror
# harness_failure_annotator.py:14-16). register_session_handler is idempotent.
from app.services.execution_events import register_session_handler  # noqa: E402

register_session_handler(on_session_complete_detect)
