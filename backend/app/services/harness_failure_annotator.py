"""Life-Harness failure annotator (T1 stub).

Walks a completed execution's harness output and classifies recurring
interface failures into the four Life-Harness layers:

    H2 — Action Realization       (priority 2, checked first)
    H3 — Environment Contract     (priority 3)
    H4 — Trajectory Regulation    (priority 4)
    general                       (priority 5, residual)

Reference: arXiv 2605.22166 Appendix A.1.

Wiring
------
At process startup (``app_litestar/lifecycle.py``) add::

    from app.services import execution_events
    from app.services.harness_failure_annotator import on_execution_complete
    execution_events.register_completion_handler(on_execution_complete)

That hooks the annotator onto every WorkflowExecutionService completion;
errors are already swallowed by ``emit_execution_complete``.

Design notes
------------
- T1 ships only a Claude-Code JSONL parser. Other harnesses fall through to
  the regex-only fallback, which can still raise ``general`` when an
  execution failed and emit ``h2_tool_in_content`` from textual cues.
- Detectors are intentionally conservative. False positives are worse than
  false negatives at this stage; we want users to trust the colored tiles.
- H3 detection is mostly TODO — real H3 needs per-bot tool contracts, which
  is exactly what T2 ``harness_layers`` will encode.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from app.db import harness_annotations as repo
from app.db.connection import get_connection

logger = logging.getLogger(__name__)

ANNOTATOR_VERSION = "0.1.0"
DETECTOR_VERSION = "0.1.0"

# Outcome strings (from execution_logs.status) considered failures.
FAILED_OUTCOMES = frozenset({"failed", "timeout", "interrupted", "cancelled"})

# H2: textual cues that the model wrote a "tool call" in content instead of
# emitting a real tool_use event. Conservative — only flag when an action-
# shaped token is the dominant message form.
_TOOL_IN_CONTENT_RE = re.compile(
    r"\b(take_action|answer_action|submit_answer|finish_task)\s*\(",
    re.IGNORECASE,
)
_TOOL_FENCE_RE = re.compile(r"```\s*(tool|tool_call|action)\b", re.IGNORECASE)


@dataclass
class TurnEvent:
    """One parsed turn from a harness trajectory.

    Fields are intentionally minimal — what every harness can provide.
    """

    index: int
    role: str                       # "assistant" | "tool_result" | "user" | "system"
    content_text: str = ""
    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None
    tool_error: Optional[str] = None  # tool-result error message, if any
    raw: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_claude_stream(stdout: str) -> list[TurnEvent]:
    """Best-effort parse of Claude Code's ``--output-format stream-json``.

    Lines that are not JSON or do not look like Claude events are skipped
    silently. Never raises.
    """
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
        # other types (system, result) are not turn-shaped; ignore.
    return events


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_stringify(v) for v in value)
    if isinstance(value, dict):
        # Anthropic content blocks carry text under "text"
        if "text" in value:
            return str(value["text"])
        try:
            return json.dumps(value)
        except (TypeError, ValueError):
            return str(value)
    return str(value)


# ---------------------------------------------------------------------------
# Detectors — return iterable of incident dicts
# ---------------------------------------------------------------------------

def detect_h2(events: list[TurnEvent]) -> list[dict]:
    """Action Realization — pre-execution interface errors."""
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
    """Environment Contract — TODO: real H3 needs bot-level tool contracts
    (the T2 ``harness_layers`` IR). For T1 we only flag the most universal
    cue: a tool_result that says the parameter or tool semantic is wrong
    even though the call was syntactically accepted."""
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
    """Trajectory Regulation — repetition, stagnation, budget exhaustion."""
    incidents: list[dict] = []

    # Repeated identical tool calls (same name + same args) ≥3 times.
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

    # Stagnation: ≥5 consecutive assistant turns with no tool_use.
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

    # Budget exhaustion via outcome.
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
    """Run detectors in paper-priority order; once a turn is claimed by a
    higher-priority layer it cannot also raise a lower-priority incident."""
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

    # Residual general bucket: only when the execution failed AND nothing else
    # fired. Mirrors the paper's "remaining general reasoning failures".
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
    execution_id: str,
    stdout: str,
    *,
    backend_type: str,
    outcome: Optional[str],
) -> dict[str, int]:
    """Parse → detect → persist. Returns the counts roll-up."""
    if backend_type == "claude":
        events = parse_claude_stream(stdout)
    else:
        # TODO(t1): parsers for codex / opencode / gemini. Until then we still
        # store a `general` bucket if the run failed, so the lane stays useful.
        events = []
    incidents = _apply_priority_protocol(events, outcome=outcome)
    return repo.replace_incidents(
        execution_id,
        incidents,
        detector_version=DETECTOR_VERSION,
        annotator_version=ANNOTATOR_VERSION,
        outcome=outcome,
    )


def annotate_execution(execution_id: str) -> Optional[dict[str, int]]:
    """Look up an execution by its string ID and annotate it. Returns None
    if the execution row is missing. Best-effort: logs but never raises."""
    try:
        with get_connection() as conn:
            row = conn.execute(
                """SELECT execution_id, status, backend_type, stdout_log
                   FROM execution_logs
                   WHERE execution_id = ?""",
                (execution_id,),
            ).fetchone()
    except Exception as exc:  # noqa: BLE001 — repo failure must not block caller
        logger.warning("annotate_execution lookup failed for %s: %s",
                       execution_id, exc)
        return None
    if not row:
        return None
    try:
        return annotate_from_text(
            row["execution_id"],
            row["stdout_log"] or "",
            backend_type=row["backend_type"] or "",
            outcome=row["status"],
        )
    except Exception as exc:  # noqa: BLE001 — never break execution completion
        logger.warning("annotator failed for %s: %s", execution_id, exc)
        return None


# Completion-handler signature: (entity_type, entity_id, status, output).
# Registered from lifecycle.py via execution_events.register_completion_handler.
def on_execution_complete(
    entity_type: str,
    entity_id: str,
    status: str,
    output: Optional[dict],
) -> None:
    if entity_type != "workflow":
        return  # only workflow executions land in execution_logs today
    annotate_execution(entity_id)
