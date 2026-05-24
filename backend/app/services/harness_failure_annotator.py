"""Life-Harness session failure annotator (session-scoped).

Walks any completed session's harness output and classifies recurring
interface failures into the four Life-Harness layers (H2 → H3 → H4 →
general) per Appendix A.1.

Works across every session kind via a small per-kind fetcher map: given
a ``session_id``, the fetcher returns the raw text stream + the harness
backend type + the project_id. New session producers register by adding
a fetcher.

Wiring (lifecycle.py):

    from app.services.execution_events import register_session_handler
    from app.services.harness_failure_annotator import on_session_complete
    register_session_handler(on_session_complete)
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from app.db import harness_annotations as repo
from app.db.connection import get_connection

logger = logging.getLogger(__name__)

ANNOTATOR_VERSION = "0.2.0"  # bumped for the session-scope pivot
DETECTOR_VERSION = "0.2.0"

FAILED_OUTCOMES = frozenset({"failed", "timeout", "interrupted", "cancelled"})

_TOOL_IN_CONTENT_RE = re.compile(
    r"\b(take_action|answer_action|submit_answer|finish_task)\s*\(",
    re.IGNORECASE,
)
_TOOL_FENCE_RE = re.compile(r"```\s*(tool|tool_call|action)\b", re.IGNORECASE)


@dataclass
class TurnEvent:
    """One parsed turn from a session trajectory."""
    index: int
    role: str
    content_text: str = ""
    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None
    tool_error: Optional[str] = None
    raw: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Per-kind fetchers: pull (text, backend_type, project_id, outcome)
# ---------------------------------------------------------------------------

@dataclass
class SessionPayload:
    text: str
    backend_type: str
    project_id: Optional[str]
    outcome: Optional[str]


def _fetch_trigger_execution(session_id: str) -> Optional[SessionPayload]:
    with get_connection() as conn:
        row = conn.execute(
            """SELECT e.stdout_log, e.status, e.backend_type, pp.project_id
               FROM execution_logs e
               LEFT JOIN project_paths pp ON pp.trigger_id = e.trigger_id
                   AND pp.project_id IS NOT NULL
               WHERE e.execution_id = ?
               ORDER BY pp.id ASC LIMIT 1""",
            (session_id,),
        ).fetchone()
    if not row:
        return None
    return SessionPayload(
        text=row["stdout_log"] or "",
        backend_type=row["backend_type"] or "",
        project_id=row["project_id"],
        outcome=row["status"],
    )


def _fetch_super_agent_session(session_id: str) -> Optional[SessionPayload]:
    with get_connection() as conn:
        row = conn.execute(
            """SELECT conversation_log, status, project_id
               FROM super_agent_sessions WHERE id = ?""",
            (session_id,),
        ).fetchone()
    if not row:
        return None
    return SessionPayload(
        text=row["conversation_log"] or "",
        # super-agent sessions go through CLI proxies; treat as claude-flavoured
        # by default since most super-agents drive Claude Code.
        backend_type="claude",
        project_id=row["project_id"],
        outcome=row["status"],
    )


def _fetch_project_session(session_id: str) -> Optional[SessionPayload]:
    with get_connection() as conn:
        row = conn.execute(
            """SELECT log_json, status, project_id
               FROM project_sessions WHERE id = ?""",
            (session_id,),
        ).fetchone()
    if not row:
        return None
    return SessionPayload(
        text=row["log_json"] or "",
        backend_type="claude",
        project_id=row["project_id"],
        outcome=row["status"],
    )


def _fetch_workflow(session_id: str) -> Optional[SessionPayload]:
    """Workflow completion event passes the workflow id. Aggregate node
    outputs as the trajectory text."""
    with get_connection() as conn:
        wf_row = conn.execute(
            "SELECT status FROM workflow_executions WHERE id = ?",
            (session_id,),
        ).fetchone()
        nodes = conn.execute(
            """SELECT output_json, error FROM workflow_node_executions
               WHERE execution_id = ? ORDER BY id ASC""",
            (session_id,),
        ).fetchall()
    if not wf_row and not nodes:
        return None
    text_parts = []
    for n in nodes:
        if n["output_json"]:
            text_parts.append(n["output_json"])
        if n["error"]:
            text_parts.append(n["error"])
    return SessionPayload(
        text="\n".join(text_parts),
        backend_type="claude",
        project_id=None,  # workflows don't carry project_id directly
        outcome=(wf_row["status"] if wf_row else None),
    )


SessionFetcher = Callable[[str], Optional[SessionPayload]]

_FETCHERS: dict[str, SessionFetcher] = {
    "trigger_execution": _fetch_trigger_execution,
    "super_agent": _fetch_super_agent_session,
    "project_session": _fetch_project_session,
    "workflow": _fetch_workflow,
}


def register_session_fetcher(session_kind: str, fetcher: SessionFetcher) -> None:
    """Plugin point for new session producers added in the future."""
    _FETCHERS[session_kind] = fetcher


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_claude_stream(stdout: str) -> list[TurnEvent]:
    events: list[TurnEvent] = []
    idx = 0
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue

        ev_type = obj.get("type")
        msg = obj.get("message") or {}

        if ev_type == "assistant":
            for block in msg.get("content") or []:
                btype = block.get("type")
                if btype == "text":
                    events.append(
                        TurnEvent(idx, "assistant",
                                  content_text=block.get("text", ""), raw=block)
                    )
                elif btype == "tool_use":
                    events.append(
                        TurnEvent(idx, "assistant",
                                  tool_name=block.get("name"),
                                  tool_args=block.get("input") or {},
                                  raw=block)
                    )
                idx += 1
        elif ev_type == "user":
            for block in msg.get("content") or []:
                if block.get("type") == "tool_result":
                    err = None
                    if block.get("is_error"):
                        err = _stringify(block.get("content"))
                    events.append(
                        TurnEvent(idx, "tool_result",
                                  content_text=_stringify(block.get("content")),
                                  tool_error=err, raw=block)
                    )
                    idx += 1
    return events


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_stringify(v) for v in value)
    if isinstance(value, dict):
        if "text" in value:
            return str(value["text"])
        try:
            return json.dumps(value)
        except (TypeError, ValueError):
            return str(value)
    return str(value)


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

def detect_h2(events: list[TurnEvent]) -> list[dict]:
    incidents: list[dict] = []
    for ev in events:
        if ev.role == "assistant" and ev.tool_name is None and ev.content_text:
            if _TOOL_IN_CONTENT_RE.search(ev.content_text) or \
               _TOOL_FENCE_RE.search(ev.content_text):
                incidents.append({
                    "layer": "h2",
                    "kind": "h2_tool_in_content",
                    "event_index": ev.index,
                    "evidence": {"snippet": ev.content_text[:240]},
                })
        if ev.role == "tool_result" and ev.tool_error:
            err = ev.tool_error.lower()
            if any(k in err for k in (
                "json", "missing required", "unknown argument", "invalid",
                "no such tool", "not found",
            )):
                incidents.append({
                    "layer": "h2",
                    "kind": "h2_invalid_tool_call",
                    "event_index": ev.index,
                    "evidence": {"error": ev.tool_error[:240]},
                })
    return incidents


def detect_h3(events: list[TurnEvent]) -> list[dict]:
    incidents: list[dict] = []
    for ev in events:
        if ev.role == "tool_result" and ev.tool_error:
            err = ev.tool_error.lower()
            if "unknown parameter" in err or "unsupported" in err or \
               "must be called after" in err or "out of order" in err:
                incidents.append({
                    "layer": "h3",
                    "kind": "h3_contract_violation",
                    "event_index": ev.index,
                    "evidence": {"error": ev.tool_error[:240]},
                })
    return incidents


def detect_h4(events: list[TurnEvent], *, outcome: Optional[str]) -> list[dict]:
    incidents: list[dict] = []

    sig_counts: Counter = Counter()
    sig_first: dict[tuple, int] = {}
    for ev in events:
        if ev.role == "assistant" and ev.tool_name:
            sig = (ev.tool_name, json.dumps(ev.tool_args or {}, sort_keys=True))
            sig_counts[sig] += 1
            sig_first.setdefault(sig, ev.index)
    for sig, count in sig_counts.items():
        if count >= 3:
            incidents.append({
                "layer": "h4",
                "kind": "h4_repeat_action",
                "event_index": sig_first[sig],
                "evidence": {"tool": sig[0], "count": count},
            })

    streak = 0
    streak_start: Optional[int] = None
    for ev in events:
        if ev.role == "assistant":
            if ev.tool_name is None:
                streak += 1
                if streak_start is None:
                    streak_start = ev.index
                if streak == 5:
                    incidents.append({
                        "layer": "h4",
                        "kind": "h4_stagnation",
                        "event_index": streak_start,
                        "evidence": {"consecutive_text_turns": streak},
                    })
            else:
                streak = 0
                streak_start = None

    if outcome == "timeout":
        incidents.append({
            "layer": "h4",
            "kind": "h4_budget_exhausted",
            "event_index": None,
            "evidence": {"outcome": outcome},
        })

    return incidents


def _apply_priority_protocol(
    events: list[TurnEvent],
    *,
    outcome: Optional[str],
) -> list[dict]:
    claimed: set[int] = set()
    out: list[dict] = []

    for incident in detect_h2(events):
        idx = incident.get("event_index")
        if idx is not None:
            claimed.add(idx)
        out.append(incident)

    for incident in detect_h3(events):
        idx = incident.get("event_index")
        if idx is not None and idx in claimed:
            continue
        if idx is not None:
            claimed.add(idx)
        out.append(incident)

    for incident in detect_h4(events, outcome=outcome):
        idx = incident.get("event_index")
        if idx is not None and idx in claimed:
            continue
        out.append(incident)

    if not out and outcome in FAILED_OUTCOMES:
        out.append({
            "layer": "general",
            "kind": "general_unclassified",
            "event_index": None,
            "evidence": {"outcome": outcome},
        })

    return out


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def annotate_from_text(
    session_kind: str,
    session_id: str,
    text: str,
    *,
    project_id: Optional[str],
    backend_type: str,
    outcome: Optional[str],
) -> dict[str, int]:
    """Parse → detect → persist. Pure on text input."""
    if backend_type == "claude":
        events = parse_claude_stream(text)
    else:
        events = []
    incidents = _apply_priority_protocol(events, outcome=outcome)
    return repo.replace_incidents(
        session_kind, session_id, incidents,
        project_id=project_id,
        detector_version=DETECTOR_VERSION,
        annotator_version=ANNOTATOR_VERSION,
        outcome=outcome,
    )


def annotate_session(
    session_kind: str,
    session_id: str,
    *,
    project_id: Optional[str] = None,
) -> Optional[dict[str, int]]:
    """Look up + annotate one session via its registered fetcher. Returns
    ``None`` if the session is unknown or the kind has no fetcher. Never
    raises — best-effort observability."""
    fetcher = _FETCHERS.get(session_kind)
    if fetcher is None:
        logger.debug("annotate_session: no fetcher for %s", session_kind)
        return None
    try:
        payload = fetcher(session_id)
    except Exception:
        logger.warning(
            "annotate_session: fetcher for %s/%s raised",
            session_kind, session_id, exc_info=True,
        )
        return None
    if payload is None:
        return None
    return annotate_from_text(
        session_kind, session_id, payload.text,
        project_id=project_id or payload.project_id,
        backend_type=payload.backend_type,
        outcome=payload.outcome,
    )


def on_session_complete(
    session_kind: str,
    session_id: str,
    project_id: Optional[str],
    status: str,
    output: Optional[dict],
) -> None:
    """Handler for ``execution_events.register_session_handler``.

    Fires after any session producer completes; routes to the right fetcher
    and persists annotations. Per-kind fetchers may resolve project_id
    themselves when the emitter didn't know it (e.g., a trigger-execution
    emitter that doesn't join project_paths)."""
    annotate_session(session_kind, session_id, project_id=project_id)


# ---------------------------------------------------------------------------
# Legacy entry point retained for any code path still calling the old API
# ---------------------------------------------------------------------------

def annotate_execution(execution_id: str) -> Optional[dict[str, int]]:
    """Compat: triggered against an execution_logs row by execution_id."""
    return annotate_session("trigger_execution", execution_id)


def on_execution_complete(
    entity_type: str, entity_id: str, status: str, output: Optional[dict],
) -> None:
    """Compat for the 4-arg legacy handler signature. Maps entity_type to
    a session_kind (workflow → workflow; trigger → trigger_execution)."""
    session_kind = "workflow" if entity_type == "workflow" else entity_type
    annotate_session(session_kind, entity_id)
