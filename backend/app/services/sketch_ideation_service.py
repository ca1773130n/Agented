"""Sketch ideation chat — a general-LLM "thinking partner" for the Sketch page.

The Sketch page is a brainstorming conversation: the operator fleshes out a rough
idea over several turns BEFORE deciding to turn it into work (the explicit "Route
this conversation" action). Each ideation turn is grounded with FEDERATED Tesserae
knowledge — relevant nodes retrieved across ALL of the operator's projects — so
the partner connects the new idea to prior work, prior art, and existing systems.

This deliberately does NOT route or execute anything: it is a stateless streaming
chat (the frontend holds the conversation and sends the history each turn). When
the idea is concrete the operator clicks Route, which hands it to the existing
sketch routing/execution path.

Default backend is ``gemini`` = Google **Antigravity**, the operator's general
chat model (Claude Code / Codex are coding agents that refuse open-ended ideation).
The model id is resolved from the live CLIProxy catalog default (a current
Gemini-3 id), never a hardcoded obsolete gemini-2.x.
"""

from __future__ import annotations

import logging
from typing import Generator, Optional

logger = logging.getLogger(__name__)

# Ideation needs a GENERAL-chat backend resolved from the operator's CONFIGURED
# accounts (shared with competitor-intel) — never hard-requiring one they haven't
# added. model=None lets the streamer resolve each kind's current catalog default.
from .general_backend import resolve_general_chat_backend as _resolve_ideation_backend

_IDEATION_SYSTEM = (
    "You are a product-ideation partner for an operator who builds software with "
    "autonomous AI agents. Help them turn a rough idea (a 'sketch') into something "
    "concrete: ask sharp clarifying questions, surface risks and relevant prior "
    "work, and propose concrete directions. Be concise and conversational.\n\n"
    "You are given knowledge retrieved across ALL of the operator's projects — "
    "ground your suggestions in it and reference projects/sources by name when "
    "relevant. Do NOT execute or build anything; this is a thinking conversation. "
    "When the idea feels concrete enough to act on, suggest they click "
    "'Route this conversation' to turn it into actual work."
)


def stream_ideation(
    messages: list[dict],
    *,
    backend: Optional[str] = None,
    model: Optional[str] = None,
) -> Generator[tuple[str, dict], None, None]:
    """Stream one grounded ideation turn.

    ``messages`` is the full conversation so far (roles ``user``/``assistant``),
    ending with the latest user message. Yields ``(event, payload)`` tuples:
      * ``("retrieval", {projects, citations})`` — the federated grounding used
        (emitted once, up front; empty when retrieval yielded nothing).
      * ``("content", {content})`` — response text chunks.
      * ``("done", {})`` — end of turn.
      * ``("error", {message})`` — a fatal streaming error (rare; fail-soft).
    """
    from .conversation_streaming import stream_llm_response
    from .tesserae_integration import federated_context_message, federation_status

    backend = backend or _resolve_ideation_backend()
    llm_messages: list[dict] = [{"role": "system", "content": _IDEATION_SYSTEM}, *messages]

    last_user = next((m.get("content") for m in reversed(messages) if m.get("role") == "user"), "")
    # Rich retrieval provenance for the UI: scope (federated graph vs nothing),
    # the semantic backend actually used (so a hash-bucket fallback is visible vs
    # real embeddings), graph size searched, and the cited sources.
    retrieval: dict = {
        "scope": None,
        "projects": [],
        "citations": 0,
        "stats": {},
        "sources": [],
        "federation": {},
    }
    if last_user:
        try:
            ctx = federated_context_message(last_user)
            if ctx:
                # Insert BEFORE the latest user message (the last entry).
                llm_messages.insert(-1, {"role": "system", "content": ctx["content"]})
                cits = ctx.get("_citations", []) or []
                stats = ctx.get("_stats", {}) or {}
                # 0.12.0 federation composition (cached): per-project node counts +
                # cross-project identity merges — shows HOW the federation is built.
                fed = federation_status() or {}
                retrieval = {
                    "scope": "federated",
                    "projects": ctx.get("_projects", []),
                    "citations": len(cits),
                    "stats": {
                        "nodes": stats.get("nodes"),
                        "edges": stats.get("edges"),
                        "semantic_backend": stats.get("semantic_backend"),
                        "semantic_skipped": stats.get("semantic_skipped"),
                        "semantic_added": stats.get("semantic_added"),
                    },
                    "sources": [
                        {
                            "name": c.get("node_name"),
                            "path": c.get("source_path"),
                            "wiki_kind": c.get("wiki_kind"),
                            "project": (c.get("node_id") or "").split("::", 1)[0] or None,
                        }
                        for c in cits[:12]  # cap for the UI; `citations` carries the true total
                        if isinstance(c, dict)
                    ],
                    "federation": {
                        "per_project_nodes": fed.get("per_project_nodes") or {},
                        "identity_merges": fed.get("identity_merges"),
                    },
                }
        except Exception:
            logger.warning("sketch ideation: federated grounding failed", exc_info=True)

    yield ("retrieval", retrieval)

    try:
        for chunk in stream_llm_response(llm_messages, backend=backend, model=model):
            if chunk:
                yield ("content", {"content": chunk})
    except Exception as exc:  # noqa: BLE001 — a streaming error must end the turn cleanly
        logger.warning("sketch ideation: stream failed: %s", exc, exc_info=True)
        yield ("error", {"message": str(exc)[:200]})
        return

    yield ("done", {})


def sse_lines(messages: list[dict], *, backend: Optional[str] = None) -> Generator[str, None, None]:
    """Adapt :func:`stream_ideation` to SSE wire frames (``event:``/``data:``)."""
    import json as _json

    for event, payload in stream_ideation(messages, backend=backend):
        yield f"event: {event}\ndata: {_json.dumps(payload)}\n\n"
