"""ProjectSessionManager -- persistent PTY sessions with ring-buffer output and SSE broadcasting.

Manages long-lived PTY sessions for project plan execution. Each session runs a CLI command
(e.g., `claude -p ...`) in an isolated pseudo-terminal, captures output in a fixed-size ring
buffer, and broadcasts lines in real-time via SSE to connected clients.

Key features:
- PTY-based sessions via pty.openpty()/os.fork()/os.setsid()
- Ring buffer: collections.deque(maxlen=10000) per session
- SSE broadcasting: Queue-per-subscriber, same pattern as ExecutionLogService
- Pause/resume: suppresses broadcast but process keeps running and output keeps buffering
- Resource limits: 1-hour idle timeout, 4-hour max lifetime
- Crash recovery: PID/PGID persisted to DB, dead sessions cleaned on startup
"""

import json
import logging
import os
import pty
import re
import select
import signal
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from queue import Empty, Queue
from typing import Dict, Generator, List, Optional

from ..db import (
    _get_unique_project_session_id,
    get_active_sessions,
    get_connection,
    update_project_session,
)
from ..db.backends import get_accounts_for_backend_type

logger = logging.getLogger(__name__)

# Compiled regex to strip ANSI escape codes from PTY output.
# Handles CSI sequences (\x1b[...X), OSC sequences (\x1b]...BEL), and other common escapes.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|\x1b\].*?\x07|\x1b\[.*?[@-~]")


_MD_FENCE_RE = re.compile(
    r"```(?:markdown|md)\s*\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)

# Matches a stray opening backtick that immediately precedes a
# markdown ATX header. Anchored to a non-whitespace character on the
# left so we don't accidentally match a legitimate fenced code block
# (``\n`` then text + backtick) or an isolated header. Captures the
# leading non-space so the replacement preserves it.
_STRAY_BACKTICK_BEFORE_HEADING_RE = re.compile(
    r"(\S)[ \t]*`[ \t]*(?=#{1,6}[ \t])"
)


def _heal_stray_backtick_before_heading(text: str) -> str:
    """Recover marked-renderable structure when claude inlines a file
    or block under a single (never-closed) backtick.

    Concrete case the user hit (v0.7.64):

        "Here's the full file (99 lines):`# Coding Behavior Contract..."

    Marked sees the lone ````` as the opening of an inline code
    span, but with no close it treats the backtick as a literal and
    consumes the rest of the text as one paragraph. The ``#`` is no
    longer at line-start, so no heading renders. Convert that to

        "Here's the full file (99 lines):\\n\\n# Coding Behavior..."

    so the heading lands cleanly on its own line.
    """
    return _STRAY_BACKTICK_BEFORE_HEADING_RE.sub(r"\1\n\n", text)


# v0.7.72 — AskUserQuestion JSON-in-text detector. Matches both an
# inline JSON object ``{"questions":[...]}`` and a fenced ``` ```json
# {...} ``` ``` block whose payload has that shape. Both forms appear
# when claude lacks the structured tool (or hallucinates the call as
# text); we lift them into the same ``ask_user_question`` SSE event
# the structured ``tool_use`` path emits.
#
# A regex can't reliably bracket-match nested JSON (the options array
# itself contains brace-rich objects), so we use a brace-counting
# scanner anchored at each ``"questions"`` keyword. Cheap enough at
# the sizes claude emits.
_AUQ_FENCE_RE = re.compile(
    r"```(?:json)?\s*\n(\{[\s\S]*?\"questions\"[\s\S]*?\})\s*\n```",
    re.MULTILINE,
)
_AUQ_KEYWORD_RE = re.compile(r"\"questions\"\s*:\s*\[")


def _scan_balanced_object(text: str, anchor: int) -> Optional[tuple[int, int]]:
    """Find the JSON object whose body contains ``anchor``.

    Walks left from ``anchor`` to the nearest ``{`` (the candidate
    object start), then forward counting braces (honoring strings +
    escapes) until balance returns to 0. Returns ``(start, end)`` of
    the substring on success, ``None`` otherwise.
    """
    start = text.rfind("{", 0, anchor)
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
    return None


def _looks_like_ask_user_question(payload: dict) -> bool:
    """True iff ``payload`` has the AskUserQuestion-input shape.

    Required: ``questions`` is a non-empty list of dicts, each with
    ``question`` (str) and ``options`` (list). Other AskUserQuestion
    fields (``header``, ``multiSelect``, option ``description``) are
    optional so we don't reject minor formatting variants.
    """
    if not isinstance(payload, dict):
        return False
    questions = payload.get("questions")
    if not isinstance(questions, list) or not questions:
        return False
    for q in questions:
        if not isinstance(q, dict):
            return False
        if not isinstance(q.get("question"), str):
            return False
        opts = q.get("options")
        if not isinstance(opts, list) or not opts:
            return False
        if not all(isinstance(o, dict) and "label" in o for o in opts):
            return False
    return True


def _extract_text_ask_question(text: str) -> tuple[str, Optional[dict]]:
    """Scan ``text`` for an AskUserQuestion JSON payload.

    Returns ``(stripped_text, payload_dict)`` where:
      * ``stripped_text`` has the matched JSON (and surrounding
        fence, if any) replaced by an empty string so the operator
        doesn't see both the raw JSON and the button card.
      * ``payload_dict`` is ``{"tool_use_id": "", "questions": [...]}``
        ready to be broadcast as an ``ask_user_question`` SSE event,
        or ``None`` if no AskUserQuestion shape was found.

    Fenced ``` ```json ``` ``` blocks are tried first because their
    boundaries are unambiguous. The unfenced scan anchors on the
    ``"questions"`` keyword and uses a brace-balanced walk to find
    the enclosing JSON object.
    """
    for m in _AUQ_FENCE_RE.finditer(text):
        blob = m.group(1)
        try:
            payload = json.loads(blob)
        except (json.JSONDecodeError, ValueError):
            continue
        if not _looks_like_ask_user_question(payload):
            continue
        stripped = text[: m.start()] + text[m.end() :]
        return (
            stripped,
            {"tool_use_id": "", "questions": payload["questions"]},
        )

    for km in _AUQ_KEYWORD_RE.finditer(text):
        bounds = _scan_balanced_object(text, km.start())
        if bounds is None:
            continue
        start, end = bounds
        blob = text[start:end]
        try:
            payload = json.loads(blob)
        except (json.JSONDecodeError, ValueError):
            continue
        if not _looks_like_ask_user_question(payload):
            continue
        stripped = text[:start] + text[end:]
        return (
            stripped,
            {"tool_use_id": "", "questions": payload["questions"]},
        )

    return text, None


def _unwrap_markdown_fences(text: str) -> str:
    """Replace ``` ```markdown\\n…\\n``` ``` blocks with their inner content.

    Claude wraps file contents in a ``markdown`` (or ``md``) fence
    by default when it reads ``.md`` files. ``marked`` correctly
    preserves fenced code, so those headings/lists end up rendered
    as ``<pre><code>`` and ``#`` characters appear literal. From
    the user's POV, "show me CLAUDE.md" should display the rendered
    document, not the source bytes — so when the fence's language
    tag is explicitly ``markdown``/``md``, lift the inner text out
    and let marked parse it as actual markdown.

    Other fence languages (``bash``, ``python``, ``json``, …) and
    untagged fences are untouched — those are code samples the
    user almost certainly wants to see verbatim.
    """
    return _MD_FENCE_RE.sub(lambda m: m.group(1), text)


def _resolve_admin_api_key() -> Optional[str]:
    """Look up an admin API key from ``user_roles`` for the
    permission hook to authenticate against the backend.

    Returns ``None`` if no admin key exists; the overlay setup will
    log a warning and the hook will fall back to ``ask`` (claude's
    default permission flow).
    """
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT api_key FROM user_roles WHERE role='admin' LIMIT 1"
            ).fetchone()
        if row and row["api_key"]:
            return row["api_key"]
    except Exception:
        logger.warning("permission hook: failed to resolve admin API key", exc_info=True)
    return None


def _render_tool_use(block: dict) -> str:
    """Render a ``tool_use`` block as a collapsible HTML widget.

    The earlier v0.7.48 markdown rendering (``**▸ Bash** `ls /tmp` ``)
    looked indistinguishable from inline emphasis once
    ``MarkdownContent`` wrapped paths in ``<code>``. Users asked for
    proper tag-style chips for tool names + paths and a click-to-
    expand for full tool input. ``ChatBubble`` pipes content through
    ``marked.parse`` then ``DOMPurify`` (which keeps ``<details>``,
    ``<summary>``, ``<span>``, ``<code>``, ``<pre>``), so HTML is the
    cleanest way to ship this without subclassing the bubble.

    Layout per call::

        <details class="tool-call tool-call--bash">
          <summary>
            <span class="tool-name">▸ Bash</span>
            <code class="tool-arg">ls /tmp</code>
          </summary>
          <pre><code>{...full JSON input...}</code></pre>
        </details>

    Styling lives in ``App.vue`` (global so it reaches v-html'd
    bubble content — scoped styles can't cross that boundary).
    """
    import html as _html
    import json as _json

    name = block.get("name", "unknown")
    inp = block.get("input", {}) or {}

    kind = _tool_kind(name)
    esc_name = _html.escape(str(name))
    summary_chips = f'<span class="tool-name">▸ {esc_name}</span>'

    if name == "Bash":
        cmd = (inp.get("command") or "").strip()
        if cmd:
            summary_chips += (
                f' <code class="tool-arg">{_html.escape(_one_line(cmd, 80))}</code>'
            )

    elif name in ("Read", "Edit", "Write", "MultiEdit", "NotebookEdit"):
        path = inp.get("file_path") or inp.get("path") or ""
        if path:
            summary_chips += (
                f' <code class="tool-path">{_html.escape(path)}</code>'
            )

    elif name in ("Grep", "Glob"):
        pattern = inp.get("pattern") or inp.get("query") or ""
        path = inp.get("path") or ""
        if pattern:
            summary_chips += (
                f' <code class="tool-pattern">{_html.escape(pattern)}</code>'
            )
        if path:
            summary_chips += (
                f' <span class="tool-sep">in</span>'
                f' <code class="tool-path">{_html.escape(path)}</code>'
            )

    elif name == "WebFetch":
        url = inp.get("url") or ""
        if url:
            summary_chips += (
                f' <code class="tool-arg">{_html.escape(url)}</code>'
            )

    elif name == "WebSearch":
        query = inp.get("query") or ""
        if query:
            summary_chips += (
                f' <code class="tool-arg">{_html.escape(_one_line(query, 80))}</code>'
            )

    elif name == "Task":
        subagent = inp.get("subagent_type") or "general"
        desc = inp.get("description") or ""
        summary_chips += (
            f' <span class="tool-meta">({_html.escape(subagent)})</span>'
        )
        if desc:
            summary_chips += (
                f' <code class="tool-arg">{_html.escape(_one_line(desc, 80))}</code>'
            )

    else:
        # MCP / ToolSearch / etc. Best-effort: pick the most
        # distinctive arg for the chip.
        detail = (
            inp.get("query")
            or inp.get("command")
            or inp.get("file_path")
            or inp.get("path")
            or inp.get("description")
            or ""
        )
        if detail:
            summary_chips += (
                f' <code class="tool-arg">{_html.escape(_one_line(detail, 80))}</code>'
            )

    # Expanded body: full JSON input. Empty inputs collapse to
    # ``(no arguments)`` so the disclosure arrow isn't a dead end.
    if inp:
        try:
            pretty = _json.dumps(inp, indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            pretty = str(inp)
        body = f'<pre class="tool-detail"><code>{_html.escape(pretty)}</code></pre>'
    else:
        body = '<div class="tool-detail-empty">(no arguments)</div>'

    return (
        f'<details class="tool-call tool-call--{kind}">'
        f'<summary>{summary_chips}</summary>'
        f'{body}'
        f'</details>'
    )


def _tool_kind(name: str) -> str:
    """Short kind tag for CSS hooks. Keeps the modifier class human-
    readable (``tool-call--file``, ``tool-call--shell``, etc.)."""
    if name == "Bash":
        return "shell"
    if name in ("Read", "Edit", "Write", "MultiEdit", "NotebookEdit"):
        return "file"
    if name in ("Grep", "Glob"):
        return "search"
    if name in ("WebFetch", "WebSearch"):
        return "web"
    if name == "Task":
        return "task"
    return "tool"


def _one_line(text: str, limit: int = 80) -> str:
    """Collapse multi-line text into a single readable preview line."""
    flat = " ".join(text.split())
    if len(flat) > limit:
        return flat[: limit - 1] + "…"
    return flat


def _extract_stream_json_text(line: str) -> Optional[str]:
    """Back-compat shim — collapses ``_extract_stream_json_events`` to a
    single string for callers that only care about the textual side.

    Kept so the existing test fixtures keep matching exactly. New code
    should use the events list and broadcast each event type
    independently (see ``_reader_loop``).
    """
    events = _extract_stream_json_events(line)
    if not events:
        return None
    # Treat ``output_delta`` text as inline content (no separator, it's
    # a partial token) and ``output`` lines as full content (joined
    # with newlines). Interactive events (ask_user_question, …) don't
    # have an SSE-style textual form.
    deltas = "".join(
        ev_data.get("text", "")
        for ev_type, ev_data in events
        if ev_type == "output_delta"
    )
    outputs = "\n".join(
        ev_data.get("line", "")
        for ev_type, ev_data in events
        if ev_type == "output" and ev_data.get("line")
    )
    combined = (deltas + ("\n" if deltas and outputs else "") + outputs).strip("\n")
    return combined or None


def _extract_stream_json_events(
    line: str, session_info: Optional["SessionInfo"] = None
) -> list[tuple[str, dict]]:
    """Parse one stream-json line into a list of SSE events to broadcast.

    Most lines produce zero or one ``("output", {"line": "..."})``
    tuple. Some produce side-channel events — e.g. ``AskUserQuestion``
    tool_use becomes ``("ask_user_question", {"tool_use_id", "questions"})``
    so the frontend can render clickable options instead of an inert
    chip.

    The optional ``session_info`` carries cross-line state — currently
    just the ``had_recent_delta`` flag for v0.7.67 token-level
    streaming dedup. When provided and a ``content_block_delta`` text
    event has streamed during the current turn, we skip the
    duplicate text blocks in the trailing ``assistant`` event.
    Callers without state (tests) pass ``None`` and get the
    pre-streaming behavior.

    Returns: ordered list of ``(event_type, payload_dict)`` for the
    reader thread to broadcast in sequence.
    """
    try:
        event = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return [("output", {"line": line})]  # Not JSON — pass through

    event_type = event.get("type")

    if event_type == "assistant":
        msg = event.get("message", {})
        events: list[tuple[str, dict]] = []
        # Each block emits at most one event. Text + non-AskUser tool_use
        # blocks accumulate into one "output" event so the chat bubble
        # stays grouped; AskUserQuestion gets its own event so the
        # frontend can mount an interactive component.
        text_buffer: list[str] = []
        # v0.7.67 — when token-level streaming was active during this
        # turn, the trailing ``assistant`` event's text blocks duplicate
        # everything that already streamed via ``content_block_delta``.
        # Skip them.
        skip_text = session_info is not None and session_info.had_recent_delta
        for block in msg.get("content", []):
            block_type = block.get("type")
            if block_type == "thinking":
                # v0.7.68 — extended-thinking reasoning text.
                # Surface as its own SSE event so the frontend can
                # render a distinct collapsible block rather than
                # treating the reasoning as regular prose.
                thinking_text = block.get("thinking", "")
                if thinking_text:
                    if text_buffer:
                        events.append(
                            ("output", {"line": "\n".join(text_buffer)})
                        )
                        text_buffer = []
                    events.append(
                        ("thinking", {"text": thinking_text}),
                    )
                continue
            if block_type == "text":
                if skip_text:
                    continue
                # Two normalization passes:
                # 1. Lift ``markdown``-tagged fences so .md files render
                #    as the source intends (headings, lists, paragraphs).
                # 2. Heal stray opening backticks that swallow a
                #    following ATX header — see v0.7.64.
                healed = _heal_stray_backtick_before_heading(block["text"])
                normalized = _unwrap_markdown_fences(healed)

                # v0.7.72 — defensive AskUserQuestion detection.
                # When claude doesn't have the structured tool
                # available (or hallucinates the call as a JSON
                # payload inside a text block), the operator sees
                # raw JSON instead of clickable options. Lift any
                # such payload into a real ``ask_user_question``
                # event so InteractiveQuestionCard fires the same
                # way it does for the structured tool_use path.
                stripped_text, synthetic_q = _extract_text_ask_question(
                    normalized
                )
                if stripped_text.strip():
                    text_buffer.append(stripped_text)
                if synthetic_q is not None:
                    if text_buffer:
                        events.append(
                            ("output", {"line": "\n".join(text_buffer)})
                        )
                        text_buffer = []
                    events.append(("ask_user_question", synthetic_q))
            elif block_type == "tool_use":
                name = block.get("name")
                if name == "AskUserQuestion":
                    # Flush accumulated text first so chronological
                    # order is preserved (text before the question).
                    if text_buffer:
                        events.append(
                            ("output", {"line": "\n".join(text_buffer)})
                        )
                        text_buffer = []
                    events.append(
                        (
                            "ask_user_question",
                            {
                                "tool_use_id": block.get("id", ""),
                                "questions": (block.get("input") or {}).get(
                                    "questions", []
                                ),
                            },
                        )
                    )
                elif name == "ExitPlanMode":
                    # v0.7.65 — claude proposes a plan in plan mode.
                    # The user must approve before claude starts
                    # executing. Flush prior text, then side-channel
                    # the plan payload so the frontend can render an
                    # approve / keep-planning card.
                    if text_buffer:
                        events.append(
                            ("output", {"line": "\n".join(text_buffer)})
                        )
                        text_buffer = []
                    events.append(
                        (
                            "exit_plan_mode",
                            {
                                "tool_use_id": block.get("id", ""),
                                "plan": (block.get("input") or {}).get(
                                    "plan", ""
                                ),
                            },
                        )
                    )
                else:
                    text_buffer.append(_render_tool_use(block))
            elif block_type == "tool_result":
                content = block.get("content", "")
                if isinstance(content, str) and content:
                    text_buffer.append(content[:500])
        if text_buffer:
            events.append(("output", {"line": "\n".join(text_buffer)}))
        # v0.7.74 — synthesize a ``turn_done`` event at the end of
        # EVERY assistant event so in-process consumers (e.g.
        # ``GoalLoopRunner``) have a reliable turn-boundary signal.
        # ``text`` aggregates everything the judge needs to assess
        # the turn:
        #   * ``output`` event lines (text + non-AUQ tool chips)
        #   * accumulated ``content_block_delta`` text (the
        #     ``skip_text`` path swallowed the trailing assistant
        #     text blocks, but the deltas are the canonical record)
        #   * the ``ExitPlanMode`` plan body (side-channel event;
        #     missing it would hide a turn's primary content from
        #     the judge)
        # ``AskUserQuestion`` is intentionally NOT included — it's
        # an operator-facing widget the judge can't evaluate.
        # ALWAYS emit, even when text is empty, so tool-use-only
        # turns (or AskUserQuestion-only turns) still tick the
        # runner's iteration counter. The runner's judge handles
        # empty text gracefully.
        text_parts: list[str] = [
            ev_data["line"]
            for ev_type, ev_data in events
            if ev_type == "output" and ev_data.get("line")
        ]
        if session_info is not None and session_info.pending_turn_text:
            text_parts.append(session_info.pending_turn_text)
        for ev_type, ev_data in events:
            if ev_type == "exit_plan_mode" and ev_data.get("plan"):
                text_parts.append(f"[plan proposed]\n{ev_data['plan']}")
        turn_text = "\n".join(p for p in text_parts if p).strip()
        events.append(("turn_done", {"text": turn_text}))
        # Reset streaming state at the end of an assistant event —
        # the next delta would belong to a new turn.
        if session_info is not None:
            session_info.had_recent_delta = False
            session_info.pending_turn_text = ""
        return events

    # Streaming delta events (partial text during long responses).
    # With ``--include-partial-messages`` (v0.7.67) claude emits these
    # token-by-token; we surface them as ``output_delta`` so the
    # frontend can append to the live bubble without separators.
    if event_type == "content_block_delta":
        delta = event.get("delta", {})
        if delta.get("type") == "text_delta":
            text = delta.get("text", "")
            if text and session_info is not None:
                session_info.had_recent_delta = True
                # v0.7.74 — accumulate the streamed text for
                # ``turn_done``. The trailing assistant event will
                # skip its own text blocks (``skip_text``) so this
                # accumulator is the only record of what the user
                # saw during the streaming portion of the turn.
                session_info.pending_turn_text += text
            return [("output_delta", {"text": text})] if text else []
        return []

    if event_type == "result":
        # Suppressed — duplicates the preceding ``assistant`` content.
        # See note on v0.7.43.
        return []

    if event_type == "system":
        # v0.7.66 — surface ``PreToolUse`` / ``PostToolUse`` hook
        # decisions as a side-channel ``hook_decision`` event the
        # chat panel can render as a read-only badge. Other system
        # subtypes (init, hook_started, rate_limit_event, …) stay
        # filtered.
        if event.get("subtype") == "hook_response":
            return _extract_hook_decision_events(event)
        return []

    # Skip noise.
    return []


def _extract_hook_decision_events(hook_event: dict) -> list[tuple[str, dict]]:
    """Translate a ``system/hook_response`` into a ``hook_decision``
    SSE event when its output contains a permission decision.

    Claude's ``PreToolUse`` / ``PostToolUse`` hooks can return JSON in
    the response ``output`` field with shape:

        {"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow"|"deny"|"ask",
            ...}}

    When that's present we lift it into a structured event for the
    frontend; hooks that just return text or have no permission
    decision are filtered (returning ``[]``).
    """
    output_raw = hook_event.get("output", "")
    if not isinstance(output_raw, str) or not output_raw.strip():
        return []
    try:
        output = json.loads(output_raw)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(output, dict):
        return []
    spec = output.get("hookSpecificOutput") or {}
    if not isinstance(spec, dict):
        return []
    decision = spec.get("permissionDecision")
    if decision not in ("allow", "deny", "ask"):
        return []
    return [
        (
            "hook_decision",
            {
                "hook_event": spec.get("hookEventName") or hook_event.get("hook_event"),
                "hook_name": hook_event.get("hook_name"),
                "tool_name": (
                    hook_event.get("tool_name")
                    or spec.get("toolName")
                    or ""
                ),
                "tool_input": (
                    hook_event.get("tool_input")
                    or spec.get("toolInput")
                    or {}
                ),
                "decision": decision,
                "outcome": hook_event.get("outcome"),
            },
        )
    ]


@dataclass
class SessionInfo:
    """In-memory state for an active session.

    Two transports are supported:
    * **PTY** (default, ``popen is None``): ``master_fd`` is the PTY master.
      Used by ralph loops, team-spawn, and any TUI-aware subprocess.
    * **Pipe** (``popen is not None``): stdin/stdout are anonymous pipes.
      Used for ``claude --print --input-format stream-json`` style chat,
      where claude refuses to read from a tty. ``master_fd`` aliases
      ``popen.stdout.fileno()`` so the reader thread is fd-uniform.
    """

    session_id: str
    pid: int
    pgid: int
    master_fd: int
    ring_buffer: deque  # deque(maxlen=10000)
    reader_thread: threading.Thread
    status: str  # active, paused, completed, failed
    created_at: datetime
    last_activity_at: datetime
    worktree_path: Optional[str] = None
    execution_type: str = "direct"
    execution_mode: str = "autonomous"
    idle_timeout_seconds: int = 3600
    max_lifetime_seconds: int = 14400
    paused: bool = False  # When True, output buffers but SSE broadcast is suppressed
    stream_json: bool = False  # When True, parse claude stream-json events for display
    # Set on pipe-mode sessions only. None means PTY-mode (legacy path).
    popen: Optional[subprocess.Popen] = field(default=None, repr=False)
    # v0.7.67 — true after at least one ``content_block_delta`` text
    # event has arrived in the current assistant turn. The extractor
    # uses this to skip the final ``assistant`` event's text blocks
    # (they'd duplicate what already streamed live). Reset to False
    # at the end of each ``assistant`` event.
    had_recent_delta: bool = False
    # v0.7.74 — accumulator for text streamed via
    # ``content_block_delta`` so the trailing ``assistant`` event's
    # ``turn_done`` synthetic event carries the full text the
    # operator saw (and the goal-loop judge needs to assess), even
    # when ``--include-partial-messages`` is on and the assistant's
    # text blocks were dropped to avoid double-rendering. Cleared
    # at the end of each assistant turn.
    pending_turn_text: str = ""


class ProjectSessionManager:
    """Service for managing persistent PTY sessions with SSE output streaming.

    Follows the classmethod singleton pattern from ExecutionLogService.
    All state is class-level, protected by a threading lock.
    """

    # In-memory session tracking: {session_id: SessionInfo}
    _sessions: Dict[str, SessionInfo] = {}
    # SSE subscribers: {session_id: [Queue]} — queues receive
    # SSE-formatted strings ("event: ...\ndata: {...}\n\n"). Used by
    # the HTTP /stream endpoint.
    _subscribers: Dict[str, List[Queue]] = {}
    # v0.7.74 — in-process raw subscribers: {session_id: [Queue]}.
    # Queues receive ``(event_type, data_dict)`` tuples — no SSE
    # framing — for consumers like ``GoalLoopRunner`` that need to
    # react to events programmatically instead of forwarding them to
    # a browser. Separate from ``_subscribers`` because mixing the
    # two payload shapes on one queue would force every consumer to
    # parse SSE strings, defeating the point.
    _raw_subscribers: Dict[str, List[Queue]] = {}
    _lock = threading.Lock()

    @classmethod
    def create_session(
        cls,
        project_id: str,
        cmd: list,
        cwd: str,
        phase_id: str = None,
        plan_id: str = None,
        agent_id: str = None,
        worktree_path: str = None,
        execution_type: str = "direct",
        execution_mode: str = "autonomous",
        env: dict = None,
        stream_json: bool = False,
        use_pty: bool = True,
        yolo_mode: bool = False,
        forge_bundle: Optional[dict] = None,
    ) -> str:
        """Create a persistent session.

        Two transports are supported. Most callers want the default
        PTY transport: ralph loops, team-spawn, and interactive
        ``claude`` TUI all need a tty so the child sees ``isatty()``
        succeed. Chat-style ``claude --print --input-format stream-json``
        callers must pass ``use_pty=False`` because ``--print`` refuses
        to read from a tty.

        Args:
            project_id: Project this session belongs to.
            cmd: Command and arguments to execute, e.g. ["claude", "-p", "..."].
            cwd: Working directory for the command.
            phase_id: Optional phase context.
            plan_id: Optional plan context.
            agent_id: Optional agent context.
            worktree_path: Optional isolated worktree path.
            execution_type: "direct", "ralph_loop", or "team_spawn".
            execution_mode: "autonomous" or "interactive".
            env: Optional dict of environment variables to set in the child process.
                 Applied after fork, before exec. None means no changes.
            stream_json: When True, the reader thread parses claude's
                ``--output-format stream-json`` events into displayable text.
            use_pty: When True (default), spawn the child via ``pty.fork()``.
                When False, spawn via ``subprocess.Popen`` with anonymous
                pipes — required for ``claude --print``.

        Returns:
            session_id (str): The unique session identifier (psess-XXXXXX).
        """
        # Generate session_id from DB to ensure uniqueness
        with get_connection() as conn:
            session_id = _get_unique_project_session_id(conn)

        # Auto-inject CLAUDE_CONFIG_DIR for claude CLI sessions so the spawned
        # process inherits the user's auth and plugins (e.g. GRD skill provider).
        user_config_dir: Optional[str] = None
        if cmd and cmd[0] == "claude" and not (env or {}).get("CLAUDE_CONFIG_DIR"):
            try:
                accounts = get_accounts_for_backend_type("claude")
                if accounts and accounts[0].get("config_path"):
                    if env is None:
                        env = {}
                    expanded = os.path.expanduser(accounts[0]["config_path"])
                    env["CLAUDE_CONFIG_DIR"] = expanded
                    user_config_dir = expanded
                    logger.info("Auto-injecting CLAUDE_CONFIG_DIR=%s for claude session", expanded)
                else:
                    logger.warning(
                        "No claude account with config_path found (accounts=%d)",
                        len(accounts) if accounts else 0,
                    )
            except Exception:
                logger.warning(
                    "Could not resolve CLAUDE_CONFIG_DIR from backend accounts", exc_info=True
                )

        # v0.7.69 — for non-yolo stream-json chat sessions, install a
        # session-scoped overlay that adds our PreToolUse permission
        # hook on top of the user's existing claude config. Symlinks
        # everything else (plugins/, mcp.json, projects/, …) so the
        # subprocess still sees the user's skills + MCP servers. The
        # user's real ~/.claude is never mutated.
        if (
            cmd
            and cmd[0] == "claude"
            and stream_json
            and not yolo_mode
            and user_config_dir
        ):
            try:
                from .claude_config_overlay import prepare_session_overlay

                overlay = prepare_session_overlay(session_id, user_config_dir)
                if overlay:
                    if env is None:
                        env = {}
                    env["CLAUDE_CONFIG_DIR"] = overlay
                    env["AGENTED_PERMISSION_HOOK_ACTIVE"] = "1"
                    env["AGENTED_PROJECT_ID"] = project_id
                    env["AGENTED_SESSION_ID"] = session_id
                    env["AGENTED_BACKEND_URL"] = os.environ.get(
                        "AGENTED_BACKEND_URL", "http://127.0.0.1:20000"
                    )
                    api_key = _resolve_admin_api_key()
                    if api_key:
                        env["AGENTED_API_KEY"] = api_key
            except Exception:
                logger.warning(
                    "Failed to prepare claude config overlay for %s — "
                    "interactive permission prompts will be inactive",
                    session_id,
                    exc_info=True,
                )

        # v0.7.71 — apply the Forge ContextBundle into whichever
        # claude overlay is in effect (the permission-hook overlay
        # we just built above, or one supplied via env). When the
        # overlay dir doesn't exist, the apply silently skips —
        # the system-prompt flag already added to ``cmd`` is the
        # other half of the bundle's effect and it doesn't need the
        # overlay. yolo_mode sessions can still benefit by setting
        # CLAUDE_CONFIG_DIR ahead of time; otherwise the bundle's
        # overlay-only portions (hooks / commands / MCP) silently
        # don't take effect, which matches the yolo philosophy.
        if forge_bundle and cmd and cmd[0] == "claude":
            overlay_path = (env or {}).get("CLAUDE_CONFIG_DIR")
            if overlay_path:
                try:
                    from .claude_config_overlay import apply_forge_bundle

                    apply_forge_bundle(overlay_path, forge_bundle)
                except Exception:
                    logger.warning(
                        "Failed to apply Forge context bundle to %s",
                        session_id,
                        exc_info=True,
                    )

        popen: Optional[subprocess.Popen] = None
        if use_pty:
            # PTY transport — child's stdio is connected to a pseudo-tty.
            master_fd, slave_fd = pty.openpty()
            pid = os.fork()

            if pid == 0:
                # --- Child process ---
                os.close(master_fd)
                os.setsid()  # New session leader (detach from parent's process group)
                os.dup2(slave_fd, 0)  # stdin
                os.dup2(slave_fd, 1)  # stdout
                os.dup2(slave_fd, 2)  # stderr
                if slave_fd > 2:
                    os.close(slave_fd)
                # Apply optional environment variables before exec
                if env:
                    for k, v in env.items():
                        os.environ[k] = v
                try:
                    os.chdir(cwd)
                except OSError:
                    os._exit(1)
                try:
                    os.execvp(cmd[0], cmd)
                except OSError:
                    os._exit(1)
                os._exit(1)

            # --- Parent process ---
            os.close(slave_fd)
        else:
            # Pipe transport — anonymous stdin/stdout pipes. Required for
            # ``claude --print``: that flag refuses to read from a tty.
            # ``preexec_fn=os.setsid`` mirrors the PTY child's setsid()
            # so ``stop_session`` can still kill the whole process group.
            # Env merges with os.environ to match the PTY behavior (a fork
            # child inherits the parent's env; Popen does not unless we
            # explicitly merge).
            popen_env = {**os.environ, **(env or {})}
            try:
                popen = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=cwd,
                    env=popen_env,
                    bufsize=0,
                    preexec_fn=os.setsid,
                )
            except (OSError, FileNotFoundError) as exc:
                logger.error("Failed to spawn pipe session: %s", exc)
                raise
            pid = popen.pid
            # ``master_fd`` is repurposed as the read fd so the reader
            # thread's select() loop stays uniform across both transports.
            master_fd = popen.stdout.fileno()

        try:
            pgid = os.getpgid(pid)
        except ProcessLookupError:
            pgid = pid  # Fallback if process already exited

        now = datetime.now()
        ring_buffer = deque(maxlen=10000)

        # Start reader thread
        reader_thread = threading.Thread(
            target=cls._reader_loop,
            args=(session_id, master_fd),
            daemon=True,
        )

        session_info = SessionInfo(
            session_id=session_id,
            pid=pid,
            pgid=pgid,
            master_fd=master_fd,
            ring_buffer=ring_buffer,
            reader_thread=reader_thread,
            status="active",
            created_at=now,
            last_activity_at=now,
            worktree_path=worktree_path,
            execution_type=execution_type,
            execution_mode=execution_mode,
            stream_json=stream_json,
            popen=popen,
        )

        with cls._lock:
            cls._sessions[session_id] = session_info

        reader_thread.start()

        # Persist to database for crash recovery.
        # We insert directly with our pre-generated session_id rather than calling
        # add_project_session() (which generates its own ID internally).
        with get_connection() as conn:
            columns = ["id", "project_id", "phase_id", "plan_id", "agent_id"]
            values = [session_id, project_id, phase_id, plan_id, agent_id]
            optional_fields = {
                "pid": pid,
                "pgid": pgid,
                "worktree_path": worktree_path,
                "execution_type": execution_type,
                "execution_mode": execution_mode,
                "last_activity_at": now.isoformat(),
            }
            for col, val in optional_fields.items():
                if val is not None:
                    columns.append(col)
                    values.append(val)
            placeholders = ", ".join(["?"] * len(columns))
            col_str = ", ".join(columns)
            try:
                conn.execute(
                    f"INSERT INTO project_sessions ({col_str}) VALUES ({placeholders})",
                    values,
                )
                conn.commit()
            except Exception:
                logger.warning(
                    f"Failed to persist session {session_id} to DB",
                    exc_info=True,
                )

        logger.info(
            "Created %s session %s (pid=%s, pgid=%s, type=%s, mode=%s, stream_json=%s)",
            "PTY" if use_pty else "pipe",
            session_id,
            pid,
            pgid,
            execution_type,
            execution_mode,
            stream_json,
        )
        return session_id

    @classmethod
    def _reader_loop(cls, session_id: str, master_fd: int) -> None:
        """Read PTY output, strip ANSI, append to ring buffer, broadcast via SSE.

        Runs in a dedicated daemon thread. Uses select() with 0.5s timeout for
        non-blocking reads. Splits output on line delimiters (\r\n, \r, \n) and
        also flushes buffered content periodically when no delimiters appear
        (CLI tools like claude use cursor-movement escapes instead of \r/\n).
        """
        buffer = b""
        last_flush_time = time.monotonic()
        FLUSH_INTERVAL = 1.0  # seconds — flush buffer even if no line delimiters

        # Check if this session uses stream-json mode
        with cls._lock:
            si = cls._sessions.get(session_id)
            _stream_json = si.stream_json if si else False

        def _emit_line(line_text: str) -> None:
            """Strip ANSI, optionally parse stream-json, broadcast events.

            In stream-json mode one input line may produce multiple
            output SSE events — e.g. a chat turn that contains text +
            an ``AskUserQuestion`` tool_use emits an ``output`` event
            for the text then an ``ask_user_question`` event for the
            structured payload, in chronological order.
            """
            cleaned = _ANSI_RE.sub("", line_text).strip()
            if not cleaned:
                return

            # Pull the session up front — the extractor consults its
            # ``had_recent_delta`` flag for token-level streaming dedup.
            with cls._lock:
                si = cls._sessions.get(session_id)
                if not si:
                    return
            if _stream_json:
                events = _extract_stream_json_events(cleaned, session_info=si)
            else:
                events = [("output", {"line": cleaned})]
            if not events:
                return

            with cls._lock:
                # Re-fetch under the lock to read paused state freshly.
                si = cls._sessions.get(session_id)
                if not si:
                    return
                is_paused = si.paused
                # Ring buffer keeps only ``output`` events — that's
                # what gets replayed to a late SSE subscriber. Side-
                # channel events (ask_user_question, output_delta, …)
                # can't be meaningfully replayed; if the user
                # reconnects after the question was answered, the
                # answer state lives elsewhere.
                for ev_type, ev_data in events:
                    if ev_type == "output":
                        si.ring_buffer.append(ev_data["line"])
                si.last_activity_at = datetime.now()

            if is_paused:
                return

            for ev_type, ev_data in events:
                payload = {**ev_data, "timestamp": datetime.now().isoformat()}
                cls._broadcast(session_id, ev_type, payload)
                # Persist assistant text into log_json so the chat
                # panel can rehydrate later. Interactive events
                # (ask_user_question) aren't persisted today —
                # answering one mutates the conversation, and that
                # mutation is already captured via the resulting
                # ``user`` (tool_result) line being persisted on the
                # input side.
                if ev_type == "output":
                    try:
                        from app.db.grd import append_session_message

                        append_session_message(
                            session_id, "assistant", ev_data["line"]
                        )
                    except Exception:
                        logger.warning(
                            "reader: failed to persist assistant message for %s",
                            session_id,
                            exc_info=True,
                        )

        try:
            while True:
                with cls._lock:
                    session_info = cls._sessions.get(session_id)
                if not session_info:
                    break

                try:
                    ready, _, _ = select.select([master_fd], [], [], 0.5)
                except (ValueError, OSError):
                    break  # fd closed or invalid

                if ready:
                    try:
                        data = os.read(master_fd, 4096)
                    except OSError:
                        break  # PTY closed
                    if not data:
                        break  # EOF
                    buffer += data

                # Extract lines delimited by \r\n, \r, or \n
                lines_found = False
                while b"\n" in buffer or b"\r" in buffer:
                    parts = re.split(b"\r\n|\r|\n", buffer, maxsplit=1)
                    if len(parts) < 2:
                        break
                    line_bytes = parts[0]
                    buffer = parts[1]
                    lines_found = True
                    _emit_line(line_bytes.decode("utf-8", errors="replace"))

                if lines_found:
                    last_flush_time = time.monotonic()

                # Time-based flush: if the buffer has content but no line delimiters
                # were found for FLUSH_INTERVAL seconds, flush it anyway.
                # This handles CLI tools that use cursor-movement escape sequences
                # (e.g. \x1b[1G) instead of \r or \n for progress updates.
                #
                # IMPORTANT: stream-json sessions opt out. Their contract is
                # strict NDJSON — one JSON event per line, terminated by ``\n``.
                # The system ``init`` event in particular is ~6-10KB once the
                # tools list expands; it spans multiple ``os.read(…, 4096)``
                # calls. Flushing the partial buffer mid-event produces a
                # broken JSON fragment that ``json.loads`` rejects, so
                # ``_extract_stream_json_text`` falls through to its
                # "not JSON — pass through as plain text" branch and a slice
                # of raw system-event bytes lands in the chat bubble. Wait
                # for a real ``\n`` instead.
                if (
                    not _stream_json
                    and buffer
                    and (time.monotonic() - last_flush_time) >= FLUSH_INTERVAL
                ):
                    _emit_line(buffer.decode("utf-8", errors="replace"))
                    buffer = b""
                    last_flush_time = time.monotonic()

        finally:
            # Close the read fd. For pipe-mode sessions the fd is owned
            # by ``popen.stdout`` — close that file object so Python's
            # buffer state stays consistent. For PTY-mode the fd is the
            # bare master we opened, so close it directly.
            with cls._lock:
                si = cls._sessions.get(session_id)
                popen_obj = si.popen if si else None
            if popen_obj is not None and popen_obj.stdout is not None:
                try:
                    popen_obj.stdout.close()
                except (OSError, ValueError):
                    pass  # Best-effort: stdout may already be closed.
            else:
                try:
                    os.close(master_fd)
                except OSError:
                    pass  # Best-effort: PTY master may already be closed.

            # Flush remaining buffer content
            if buffer:
                decoded = buffer.decode("utf-8", errors="replace")
                decoded = _ANSI_RE.sub("", decoded)
                with cls._lock:
                    session_info = cls._sessions.get(session_id)
                    if session_info:
                        session_info.ring_buffer.append(decoded)

            cls._handle_session_exit(session_id)

    @classmethod
    def _handle_session_exit(cls, session_id: str) -> None:
        """Handle session process exit: determine status, update DB, notify subscribers."""
        with cls._lock:
            session_info = cls._sessions.get(session_id)
        if not session_info:
            return

        # Check exit status. Pipe-mode sessions go through subprocess.Popen
        # which reaps the child itself; PTY-mode sessions need an explicit
        # waitpid because we forked manually.
        exit_code = None
        status = "completed"
        if session_info.popen is not None:
            try:
                # ``wait`` rather than ``poll`` here because the reader loop
                # only reaches this handler after observing EOF on stdout,
                # so the child is on its way out — wait briefly to surface
                # the return code without blocking forever.
                exit_code = session_info.popen.wait(timeout=2)
            except subprocess.TimeoutExpired:
                # Process didn't exit promptly; surface whatever poll() has.
                exit_code = session_info.popen.poll()
            except OSError:
                exit_code = None
            if exit_code is None:
                status = "failed"
            else:
                status = "completed" if exit_code == 0 else "failed"
        else:
            try:
                _, wait_status = os.waitpid(session_info.pid, os.WNOHANG)
                if os.WIFEXITED(wait_status):
                    exit_code = os.WEXITSTATUS(wait_status)
                    status = "completed" if exit_code == 0 else "failed"
                elif os.WIFSIGNALED(wait_status):
                    exit_code = -os.WTERMSIG(wait_status)
                    status = "failed"
            except ChildProcessError:
                # Process already reaped
                status = "completed"
            except OSError:
                status = "failed"

        # Update DB
        update_project_session(
            session_id,
            status=status,
            ended_at=datetime.now().isoformat(),
        )

        # Update in-memory state
        with cls._lock:
            session_info = cls._sessions.get(session_id)
            if session_info:
                session_info.status = status

        # Sync GRD .planning/ files to DB on session completion (only for GRD-initialized projects)
        try:
            from .grd_planning_service import GrdPlanningService
            from .grd_sync_service import GrdSyncService

            # Look up project_id from the DB session record
            project_id = None
            try:
                with get_connection() as conn:
                    row = conn.execute(
                        "SELECT project_id FROM project_sessions WHERE id = ?",
                        (session_id,),
                    ).fetchone()
                    if row:
                        project_id = row["project_id"]
            except Exception:
                pass  # Intentionally silenced: failure is non-critical

            if project_id:
                # Unregister from planning session tracker (no-op if not a planning session)
                GrdPlanningService.unregister_session(session_id)
                # Only sync if this project has GRD initialized
                from ..database import get_project

                project = get_project(project_id)
                if project and project.get("grd_init_status") in ("initializing", "ready"):
                    GrdSyncService.sync_on_session_complete(project_id, session_id)
        except Exception as e:
            logger.warning("GRD sync on session complete failed: %s", e)

        # v0.7.88 — flip any matching grd_evolve_runs row to its
        # terminal status. No-op when the session wasn't a
        # ``grd_evolve`` session (the runner row simply doesn't
        # exist). Reads ``exit_code`` from the session info to
        # distinguish ``completed`` vs ``failed``.
        try:
            from .grd_evolve_runner import finalize_on_session_exit

            exit_code: Optional[int] = None
            try:
                with get_connection() as conn:
                    row = conn.execute(
                        "SELECT status FROM project_sessions WHERE id = ?",
                        (session_id,),
                    ).fetchone()
                    if row and row["status"] == "completed":
                        exit_code = 0
                    elif row and row["status"] == "failed":
                        exit_code = 1
            except Exception:
                pass  # Intentionally silenced — finalize() defaults to 'completed' on None.
            finalize_on_session_exit(session_id, exit_code)
        except Exception:
            logger.warning(
                "grd_evolve: finalize_on_session_exit failed for %s",
                session_id,
                exc_info=True,
            )

        # v0.7.69 — drop any in-flight permission requests for this
        # session and remove the session-scoped config overlay dir.
        try:
            from .claude_config_overlay import cleanup_session_overlay
            from .permission_prompt_service import PermissionPromptRegistry

            PermissionPromptRegistry.cancel_session(session_id)
            cleanup_session_overlay(session_id)
        except Exception:
            logger.warning(
                "session_exit: overlay/permission cleanup failed for %s",
                session_id,
                exc_info=True,
            )

        # Broadcast completion
        cls._broadcast(
            session_id,
            "complete",
            {"status": status, "exit_code": exit_code},
        )

        # Signal end to all subscribers
        with cls._lock:
            if session_id in cls._subscribers:
                for q in cls._subscribers[session_id]:
                    q.put(None)  # Signal end of stream
                del cls._subscribers[session_id]
            # v0.7.74 — raw consumers get the ``__end__`` sentinel
            # so they can break their drain loop and unsubscribe.
            if session_id in cls._raw_subscribers:
                for q in cls._raw_subscribers[session_id]:
                    q.put(("__end__", {"status": status, "exit_code": exit_code}))
                del cls._raw_subscribers[session_id]

        logger.info(f"Session {session_id} exited (status={status}, exit_code={exit_code})")

    @classmethod
    def stop_session(cls, session_id: str) -> bool:
        """Stop a running session by terminating its process group.

        Sends SIGTERM first, waits up to 5 seconds, then SIGKILL if still alive.

        Returns:
            True if session was stopped successfully, False if session not found.
        """
        with cls._lock:
            session_info = cls._sessions.get(session_id)
        if not session_info:
            return False

        pid = session_info.pid
        pgid = session_info.pgid
        popen = session_info.popen

        # Closing stdin gives ``claude --print`` a graceful EOF to wind
        # down on. The killpg below is the fallback if it doesn't.
        if popen is not None and popen.stdin is not None:
            try:
                popen.stdin.close()
            except OSError:
                pass

        # Try graceful termination first
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass  # Already dead
        except OSError as e:
            logger.warning(f"SIGTERM to pgid {pgid} failed: {e}")

        # Wait up to 5 seconds for process to exit
        exited = False
        for _ in range(50):  # 50 * 0.1s = 5s
            if popen is not None:
                if popen.poll() is not None:
                    exited = True
                    break
            else:
                try:
                    result = os.waitpid(pid, os.WNOHANG)
                    if result[0] != 0:
                        exited = True
                        break
                except ChildProcessError:
                    exited = True
                    break  # Already reaped
                except OSError:
                    break
            time.sleep(0.1)

        if not exited:
            # Still alive after 5s -- force kill
            try:
                os.killpg(pgid, signal.SIGKILL)
                logger.warning(f"Sent SIGKILL to session {session_id} pgid {pgid}")
            except ProcessLookupError:
                pass  # Intentionally silenced: process already terminated
            except OSError as e:
                logger.error(f"SIGKILL to pgid {pgid} failed: {e}", exc_info=True)

        # Update DB
        status = "completed"
        update_project_session(
            session_id,
            status=status,
            ended_at=datetime.now().isoformat(),
        )

        # Update in-memory
        with cls._lock:
            session_info = cls._sessions.get(session_id)
            if session_info:
                session_info.status = status

        logger.info(f"Stopped session {session_id}")
        return True

    @classmethod
    def pause_session(cls, session_id: str) -> bool:
        """Pause a session's SSE broadcasting.

        The process keeps running and output keeps buffering in the ring buffer,
        but SSE broadcast is suppressed until resume_session() is called.

        Returns:
            True if session was paused, False if session not found.
        """
        with cls._lock:
            session_info = cls._sessions.get(session_id)
            if not session_info:
                return False
            session_info.paused = True
            session_info.status = "paused"

        update_project_session(session_id, status="paused")
        logger.info(f"Paused session {session_id}")
        return True

    @classmethod
    def resume_session(cls, session_id: str) -> bool:
        """Resume a paused session's SSE broadcasting.

        Re-enables the broadcast flag so NEW output lines are broadcast.
        Does NOT replay buffered output to avoid double-delivery.
        Callers should use get_output() to fetch historical lines from the ring buffer.

        Returns:
            True if session was resumed, False if session not found.
        """
        with cls._lock:
            session_info = cls._sessions.get(session_id)
            if not session_info:
                return False
            session_info.paused = False
            session_info.status = "active"

        update_project_session(session_id, status="active")
        logger.info(f"Resumed session {session_id}")
        return True

    @classmethod
    def get_output(cls, session_id: str, last_n: int = 100) -> list:
        """Get the last N lines from the session's ring buffer.

        Args:
            session_id: Session to get output from.
            last_n: Number of recent lines to return (default 100).

        Returns:
            List of output line strings.
        """
        with cls._lock:
            session_info = cls._sessions.get(session_id)
            if not session_info:
                return []
            return list(session_info.ring_buffer)[-last_n:]

    @classmethod
    def send_input(cls, session_id: str, text: str) -> bool:
        """Send input text to a session's stdin.

        For PTY sessions this writes to the master fd (which the child
        sees as stdin). For pipe sessions this writes to the
        ``Popen.stdin`` file object.

        Args:
            session_id: Target session.
            text: Text to send (a newline is appended automatically).

        Returns:
            True if the write succeeded, False if session not found/inactive or write failed.
        """
        with cls._lock:
            session_info = cls._sessions.get(session_id)
            if not session_info or session_info.status != "active":
                return False
            master_fd = session_info.master_fd
            popen = session_info.popen

        # Write outside lock to avoid blocking other threads during I/O.
        payload = (text + "\n").encode("utf-8")
        try:
            if popen is not None and popen.stdin is not None:
                popen.stdin.write(payload)
                popen.stdin.flush()
            else:
                os.write(master_fd, payload)
        except (OSError, BrokenPipeError, ValueError):
            return False

        # Update activity timestamp
        with cls._lock:
            session_info = cls._sessions.get(session_id)
            if session_info:
                session_info.last_activity_at = datetime.now()

        return True

    @classmethod
    def subscribe(cls, session_id: str) -> Generator[str, None, None]:
        """SSE generator for real-time session output streaming.

        Ordering to avoid TOCTOU gap:
        1. Register Queue in _subscribers FIRST (under lock) -- ensures no lines lost
        2. Yield existing ring buffer contents as "output" events (catchup)
        3. Check if session already completed (yield "complete" and return)
        4. Loop: queue.get(timeout=30), yield events, keepalive on timeout

        Yields:
            SSE-formatted event strings.
        """
        queue: Queue = Queue()

        with cls._lock:
            # Step 1: Register subscriber FIRST to avoid missing lines
            if session_id not in cls._subscribers:
                cls._subscribers[session_id] = []
            cls._subscribers[session_id].append(queue)

            # Step 2: Yield existing ring buffer contents (catchup)
            session_info = cls._sessions.get(session_id)
            if session_info:
                for line in session_info.ring_buffer:
                    yield cls._format_sse(
                        "output",
                        {"line": line, "timestamp": datetime.now().isoformat()},
                    )
                current_status = session_info.status
            else:
                current_status = None

        # Step 3: Check if session already completed
        if current_status in ("completed", "failed"):
            yield cls._format_sse(
                "complete",
                {"status": current_status, "exit_code": None},
            )
            # Unsubscribe
            with cls._lock:
                if session_id in cls._subscribers:
                    try:
                        cls._subscribers[session_id].remove(queue)
                    except ValueError:
                        pass  # Intentionally silenced: invalid value handled gracefully
            return

        if current_status is None:
            # Session not found in memory
            yield cls._format_sse(
                "error",
                {"message": "Session not found"},
            )
            with cls._lock:
                if session_id in cls._subscribers:
                    try:
                        cls._subscribers[session_id].remove(queue)
                    except ValueError:
                        pass  # Intentionally silenced: invalid value handled gracefully
            return

        # Step 4: Stream live events
        try:
            while True:
                try:
                    event = queue.get(timeout=30)
                    if event is None:
                        break  # End of stream
                    yield event
                except Empty:
                    # Send keepalive comment
                    yield ": keepalive\n\n"
        finally:
            # Unsubscribe
            with cls._lock:
                if session_id in cls._subscribers:
                    try:
                        cls._subscribers[session_id].remove(queue)
                    except ValueError:
                        pass  # Intentionally silenced: invalid value handled gracefully

    @classmethod
    def _broadcast(cls, session_id: str, event_type: str, data: dict) -> None:
        """Broadcast an SSE event to all subscribers for a session.

        Args:
            session_id: Target session.
            event_type: SSE event type (e.g., "output", "complete").
            data: Event payload dict (will be JSON-serialized).

        Dual-channel: pushes the SSE-formatted string to
        ``_subscribers`` (browser-bound) AND the raw
        ``(event_type, data)`` tuple to ``_raw_subscribers``
        (in-process consumers like ``GoalLoopRunner``).
        """
        message = cls._format_sse(event_type, data)
        with cls._lock:
            for q in cls._subscribers.get(session_id, []):
                q.put(message)
            for q in cls._raw_subscribers.get(session_id, []):
                q.put((event_type, data))

    @classmethod
    def subscribe_raw(cls, session_id: str) -> Queue:
        """Register an in-process raw-event consumer. v0.7.74.

        Returns a ``Queue`` that will receive ``(event_type,
        data_dict)`` tuples for every event broadcast for
        ``session_id``, plus a final ``("__end__", {})`` sentinel
        when the session completes. Caller is expected to call
        ``unsubscribe_raw`` when done.

        Unlike the SSE ``subscribe`` generator, this does NOT
        replay ring-buffer history — raw subscribers only see
        events emitted after they registered. Goal-loop runners
        register before the first turn, so they catch everything.
        """
        queue: Queue = Queue()
        with cls._lock:
            cls._raw_subscribers.setdefault(session_id, []).append(queue)
        return queue

    @classmethod
    def unsubscribe_raw(cls, session_id: str, queue: Queue) -> None:
        with cls._lock:
            subs = cls._raw_subscribers.get(session_id, [])
            try:
                subs.remove(queue)
            except ValueError:
                pass
            if not subs and session_id in cls._raw_subscribers:
                del cls._raw_subscribers[session_id]

    @staticmethod
    def _format_sse(event_type: str, data: dict) -> str:
        """Format data as an SSE message string."""
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    @classmethod
    def is_stream_json(cls, session_id: str) -> bool:
        """Return whether the session was started in stream-json mode.

        Used by the input endpoint to decide between raw-text passthrough
        (PTY interactive REPL) and JSON-envelope wrapping (claude's
        ``--input-format stream-json``).
        """
        with cls._lock:
            si = cls._sessions.get(session_id)
            return bool(si and si.stream_json)

    @classmethod
    def get_session_info(cls, session_id: str) -> Optional[dict]:
        """Get summary info for a session from in-memory state.

        Returns:
            Dict with status, pid, output_lines, created_at, last_activity_at.
            None if session not found.
        """
        with cls._lock:
            session_info = cls._sessions.get(session_id)
            if not session_info:
                return None
            return {
                "session_id": session_info.session_id,
                "status": session_info.status,
                "pid": session_info.pid,
                "pgid": session_info.pgid,
                "output_lines": len(session_info.ring_buffer),
                "created_at": session_info.created_at.isoformat(),
                "last_activity_at": session_info.last_activity_at.isoformat(),
                "worktree_path": session_info.worktree_path,
                "execution_type": session_info.execution_type,
                "execution_mode": session_info.execution_mode,
                "paused": session_info.paused,
            }

    @classmethod
    def cleanup_dead_sessions(cls) -> None:
        """Clean up sessions whose processes are no longer alive.

        Called on startup to handle sessions that were active when the server
        previously crashed or restarted. Queries the DB for active sessions
        and checks if their PIDs are still alive.
        """
        try:
            active_sessions = get_active_sessions()
        except Exception:
            logger.warning("Failed to query active sessions for cleanup", exc_info=True)
            return

        cleaned = 0
        for session_row in active_sessions:
            pid = session_row.get("pid")
            session_id = session_row.get("id")
            if not pid or not session_id:
                continue

            # Check if process is alive
            try:
                os.kill(pid, 0)  # Signal 0 = check existence only
            except ProcessLookupError:
                # Process is dead -- mark as failed
                update_project_session(
                    session_id,
                    status="failed",
                    ended_at=datetime.now().isoformat(),
                )
                cleaned += 1
                logger.info(f"Cleaned dead session {session_id} (pid={pid})")
            except PermissionError:
                # Process exists but we can't signal it -- leave it alone
                pass

        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} dead session(s) on startup")
        else:
            logger.debug("No dead sessions found during startup cleanup")

    @classmethod
    def check_resource_limits(cls) -> None:
        """Check all active sessions for resource limit violations.

        Enforces two limits:
        - Idle timeout: session with no output for idle_timeout_seconds (default 1 hour)
        - Max lifetime: session running longer than max_lifetime_seconds (default 4 hours)

        Sessions exceeding either limit are stopped.
        """
        now = datetime.now()
        sessions_to_stop = []

        with cls._lock:
            for session_id, session_info in cls._sessions.items():
                if session_info.status not in ("active", "paused"):
                    continue

                # Check idle timeout
                idle_seconds = (now - session_info.last_activity_at).total_seconds()
                if idle_seconds > session_info.idle_timeout_seconds:
                    sessions_to_stop.append(
                        (
                            session_id,
                            f"idle timeout ({idle_seconds:.0f}s > {session_info.idle_timeout_seconds}s)",
                        )
                    )
                    continue

                # Check max lifetime
                lifetime_seconds = (now - session_info.created_at).total_seconds()
                if lifetime_seconds > session_info.max_lifetime_seconds:
                    sessions_to_stop.append(
                        (
                            session_id,
                            f"max lifetime ({lifetime_seconds:.0f}s > {session_info.max_lifetime_seconds}s)",
                        )
                    )

        for session_id, reason in sessions_to_stop:
            logger.warning(f"Stopping session {session_id}: {reason}")
            cls.stop_session(session_id)
