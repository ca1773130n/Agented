"""Takeaway extractor — the positive-learning side of Life-Harness.

Where ``harness_failure_annotator`` captures mistakes (H2/H3/H4 incidents),
this service captures what the agent / user / environment *taught* the
session: preferences, discovered procedures, tool patterns, constraints,
domain facts. Each takeaway either auto-applies to its target (memory /
rule / KG) when confidence is high and auto-apply is enabled, or queues
for operator review via the Activity-lane Takeaways card.

Two extraction modes:
    - **Heuristic** (default, no LLM): regex patterns over the parsed
      trajectory. Cheap, runs on every completed session.
    - **LLM** (opt-in via ``AGENTED_TAKEAWAY_LLM=1``): would call Codex
      with the transcript + extraction prompt. Skeleton only — wire your
      preferred LLM here when ready.

Auto-apply is OFF by default. Set ``AGENTED_TAKEAWAY_AUTOAPPLY=1`` to
let high-confidence (>=0.85) takeaways write straight to memory / KG /
rules at extraction time. Lower-confidence and impactful kinds always
queue for operator review.

Hooks into the same ``session_events`` channel as the annotator, so the
extractor sees every completed session across every producer (trigger,
super-agent, project session, workflow).
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Optional

from app.db import harness_takeaways as repo
from app.services.harness_failure_annotator import (
    SessionPayload,
    _FETCHERS,
    parse_claude_stream,
)

logger = logging.getLogger(__name__)

EXTRACTOR_VERSION = "0.1.0"
HIGH_CONFIDENCE = 0.85


# ---------------------------------------------------------------------------
# Heuristic patterns
# ---------------------------------------------------------------------------

@dataclass
class _Pattern:
    """A regex-based takeaway detector.

    The ``regex`` runs against assistant content_text. ``kind`` is the
    takeaway category. ``confidence`` is a hand-tuned prior. ``target``
    suggests where it should ultimately land. ``payload_builder`` (when
    present) projects the regex match into the target's expected payload
    shape.
    """
    regex: re.Pattern
    kind: str
    confidence: float
    target: Optional[str]
    description: str


# User preferences — when the agent claims to remember a preference.
_USER_PREF_REMEMBER = _Pattern(
    regex=re.compile(
        r"(?:I'?ll|I will|got it,?\s+I'll)\s+remember\s+(?:that\s+)?"
        r"(?:you\s+)?(?:prefer|want|always|like)\b[:.,]?\s*(.{10,200}?)(?:[.!\n]|$)",
        re.IGNORECASE,
    ),
    kind="user_preference",
    confidence=0.90,
    target="memory",
    description="agent acknowledged a stored user preference",
)

# User-stated preferences — explicit "use X" / "always Y" by the user.
_USER_PREF_USER_STATED = _Pattern(
    regex=re.compile(
        r"(?:please|always|never|prefer|use)\s+"
        r"((?:use|do|avoid|stick to|stop|don'?t use)\s+[^.!\n]{5,150})",
        re.IGNORECASE,
    ),
    kind="user_preference",
    confidence=0.55,
    target="memory",
    description="user stated a preference",
)

# Discovered procedures — agent narrates a multi-step procedure.
_DISCOVERED_PROCEDURE = _Pattern(
    regex=re.compile(
        r"(?:I learned|I found|I figured out|The (?:right|correct) way to)\s+"
        r"(.{15,250}?)(?:[.!\n]|$)",
        re.IGNORECASE,
    ),
    kind="discovered_procedure",
    confidence=0.65,
    target="skill",
    description="agent narrated a procedural insight",
)

# Constraints — environment told the agent it can't do X.
_CONSTRAINT = _Pattern(
    regex=re.compile(
        r"(?:must|cannot|can'?t|need to|required to|requires)\s+"
        r"([^.!\n]{10,200}?)\b",
        re.IGNORECASE,
    ),
    kind="constraint",
    confidence=0.50,
    target="rule",
    description="constraint discovered during execution",
)

# Domain facts — file path / URL / config reference.
_DOMAIN_FACT_PATH = _Pattern(
    regex=re.compile(
        r"(?:lives at|located at|configured in|defined in|stored in)\s+"
        r"`?([^\s`]+\.[a-zA-Z0-9]{2,8})`?",
    ),
    kind="domain_fact",
    confidence=0.75,
    target="knowledge_graph",
    description="agent referenced a specific file / config path",
)

# Tool pattern — agent reports a tool combination that works.
_TOOL_PATTERN = _Pattern(
    regex=re.compile(
        r"(?:I'll|I will)\s+use\s+(\w+)\s+(?:to|for)\s+([^.!\n]{5,150})",
        re.IGNORECASE,
    ),
    kind="tool_pattern",
    confidence=0.45,
    target=None,
    description="agent declared a tool-for-task pattern",
)


_PATTERNS: tuple[_Pattern, ...] = (
    _USER_PREF_REMEMBER,
    _USER_PREF_USER_STATED,
    _DISCOVERED_PROCEDURE,
    _CONSTRAINT,
    _DOMAIN_FACT_PATH,
    _TOOL_PATTERN,
)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _extract_heuristic(
    session_kind: str,
    session_id: str,
    project_id: Optional[str],
    payload: SessionPayload,
) -> list[dict[str, Any]]:
    """Walk the parsed trajectory and run pattern detectors. Returns
    takeaway dicts ready for ``harness_takeaways.insert_many``."""
    if payload.backend_type == "claude":
        events = parse_claude_stream(payload.text)
    else:
        events = []
    if not events:
        return []

    out: list[dict[str, Any]] = []
    for ev in events:
        if ev.role != "assistant" or not ev.content_text:
            continue
        for pat in _PATTERNS:
            for m in pat.regex.finditer(ev.content_text):
                content = m.group(1).strip() if m.groups() else m.group(0).strip()
                if not content or len(content) < 5:
                    continue
                out.append({
                    "session_kind": session_kind,
                    "session_id": session_id,
                    "project_id": project_id,
                    "kind": pat.kind,
                    "content": content[:500],
                    "confidence": pat.confidence,
                    "evidence": {
                        "event_index": ev.index,
                        "pattern": pat.description,
                        "match_snippet": m.group(0)[:240],
                    },
                    "suggested_target": pat.target,
                    "suggested_payload": _build_payload(
                        pat.target, pat.kind, content, project_id,
                    ),
                    "extractor_version": EXTRACTOR_VERSION,
                })
    return _dedupe(out)


def _build_payload(
    target: Optional[str], kind: str, content: str, project_id: Optional[str],
) -> dict[str, Any]:
    """Project the takeaway into a target-shaped payload so the applier
    doesn't have to re-derive it."""
    if target == "memory":
        return {"key": _slugify(content), "value": content}
    if target == "rule":
        return {
            "name": _slugify(content)[:50],
            "description": content,
            "rule_type": "convention" if kind == "user_preference" else "validation",
        }
    if target == "knowledge_graph":
        return {"name": content[:100], "entity_type": kind}
    if target == "skill":
        return {
            "title": _slugify(content)[:60],
            "when": "extracted from session takeaway",
            "recipe": content,
        }
    return {}


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return s or "takeaway"


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop duplicates within a single session (same kind + normalised content)."""
    seen: set[tuple] = set()
    out: list[dict[str, Any]] = []
    for it in items:
        key = (it["kind"], it["content"].lower().strip())
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


# ---------------------------------------------------------------------------
# Apply-target writers (auto-apply path)
# ---------------------------------------------------------------------------

def _apply_to_memory(takeaway: dict[str, Any]) -> Optional[str]:
    """Write to ``agent_memory`` working-memory keyed on project_id. Returns
    the storage key on success or ``None`` on failure."""
    project_id = takeaway.get("project_id")
    if not project_id:
        return None
    payload = takeaway.get("suggested_payload") or {}
    key = payload.get("key") or _slugify(takeaway["content"])
    value = payload.get("value") or takeaway["content"]
    try:
        from app.db.agent_memory import (
            get_working_memory,
            upsert_working_memory,
        )
        existing = get_working_memory(project_id, entity_type="project")
        existing_content = (existing or {}).get("content") or "{}"
        try:
            bucket = json.loads(existing_content)
            if not isinstance(bucket, dict):
                bucket = {}
        except (TypeError, ValueError):
            bucket = {}
        bucket[key] = {
            "value": value,
            "source_takeaway_id": takeaway["id"],
            "kind": takeaway.get("kind"),
        }
        upsert_working_memory(
            entity_id=project_id,
            entity_type="project",
            content=json.dumps(bucket, default=str),
        )
        return key
    except Exception:
        logger.warning(
            "takeaway: memory write failed for %s", takeaway["id"], exc_info=True,
        )
        return None


def _apply_to_knowledge_graph(takeaway: dict[str, Any]) -> Optional[str]:
    project_id = takeaway.get("project_id")
    if not project_id:
        return None
    payload = takeaway.get("suggested_payload") or {}
    name = payload.get("name") or takeaway["content"][:100]
    entity_type = payload.get("entity_type") or takeaway["kind"]
    try:
        from app.db.knowledge_graph import upsert_entity
        eid = upsert_entity(
            agent_id=project_id,
            name=name,
            entity_type=entity_type,
        )
        return str(eid) if eid else None
    except Exception:
        logger.warning(
            "takeaway: KG write failed for %s", takeaway["id"], exc_info=True,
        )
        return None


def _apply_to_rule(takeaway: dict[str, Any]) -> Optional[str]:
    project_id = takeaway.get("project_id")
    if not project_id:
        return None
    payload = takeaway.get("suggested_payload") or {}
    try:
        from app.db.rules import create_rule
        rid = create_rule(
            name=payload.get("name") or _slugify(takeaway["content"]),
            description=payload.get("description") or takeaway["content"],
            rule_type=payload.get("rule_type", "validation"),
            project_id=project_id,
        )
        return str(rid) if rid else None
    except Exception:
        logger.warning(
            "takeaway: rule write failed for %s", takeaway["id"], exc_info=True,
        )
        return None


_APPLIERS = {
    "memory": _apply_to_memory,
    "knowledge_graph": _apply_to_knowledge_graph,
    "rule": _apply_to_rule,
    # skill + claude_md remain proposal-only (filesystem materialization
    # for skills; CLAUDE.md project sections need a dedicated writer).
}


def apply_takeaway(takeaway_id: str) -> dict[str, Any]:
    """Operator-triggered apply path. Returns ``{applied: bool, ...}``."""
    tk = repo.get(takeaway_id)
    if tk is None:
        return {"applied": False, "reason": f"not found: {takeaway_id}"}
    if tk.get("applied"):
        return {"applied": False, "reason": "already applied"}
    if tk.get("dismissed"):
        return {"applied": False, "reason": "dismissed"}
    target = tk.get("suggested_target")
    applier = _APPLIERS.get(target) if target else None
    if applier is None:
        return {
            "applied": False,
            "reason": f"target {target!r} not auto-applicable; "
                      "operator must materialize manually",
        }
    asset_id = applier(tk)
    if asset_id is None:
        return {"applied": False, "reason": "applier returned no id"}
    repo.mark_applied(takeaway_id, target=target, asset_id=asset_id)
    return {
        "applied": True, "target": target, "asset_id": asset_id,
        "takeaway_id": takeaway_id,
    }


def dismiss_takeaway(takeaway_id: str, *, reason: Optional[str] = None) -> dict:
    tk = repo.get(takeaway_id)
    if tk is None:
        return {"dismissed": False, "reason": "not found"}
    repo.mark_dismissed(takeaway_id, reason=reason)
    return {"dismissed": True, "takeaway_id": takeaway_id}


# ---------------------------------------------------------------------------
# Session-completion handler
# ---------------------------------------------------------------------------

def _autoapply_enabled() -> bool:
    return os.environ.get("AGENTED_TAKEAWAY_AUTOAPPLY", "0") == "1"


def extract_for_session(
    session_kind: str,
    session_id: str,
    *,
    project_id: Optional[str] = None,
) -> list[str]:
    """Pull the session's text via the annotator's fetcher map, run the
    extractor, persist takeaways. Returns the new takeaway ids."""
    fetcher = _FETCHERS.get(session_kind)
    if fetcher is None:
        return []
    try:
        payload = fetcher(session_id)
    except Exception:
        logger.debug(
            "takeaway: fetcher %s/%s raised",
            session_kind, session_id, exc_info=True,
        )
        return []
    if payload is None:
        return []
    items = _extract_heuristic(
        session_kind, session_id,
        project_id or payload.project_id,
        payload,
    )
    if not items:
        return []
    try:
        ids = repo.insert_many(items)
    except Exception:
        logger.warning("takeaway: insert_many failed", exc_info=True)
        return []

    if _autoapply_enabled():
        for tk_id, tk in zip(ids, items):
            if tk["confidence"] < HIGH_CONFIDENCE:
                continue
            if tk.get("suggested_target") not in _APPLIERS:
                continue
            try:
                tk_row = repo.get(tk_id)
                if tk_row:
                    apply_takeaway(tk_id)
            except Exception:
                continue
    return ids


def on_session_complete(
    session_kind: str,
    session_id: str,
    project_id: Optional[str],
    status: str,
    output: Optional[dict],
) -> None:
    """Handler for ``execution_events.register_session_handler``. Fires
    alongside the annotator on every session completion. Best-effort —
    extractor failures must never block other handlers."""
    try:
        extract_for_session(session_kind, session_id, project_id=project_id)
    except Exception:
        logger.warning(
            "takeaway: extract failed for %s/%s",
            session_kind, session_id, exc_info=True,
        )
