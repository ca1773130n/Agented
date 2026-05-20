"""Tests for ProjectSessionManager: PTY session lifecycle, pause/resume, output, cleanup."""

import json
import threading
from collections import deque
from datetime import datetime, timedelta
from queue import Queue
from unittest.mock import MagicMock, patch

import pytest

from app.services.project_session_manager import (
    ProjectSessionManager,
    SessionInfo,
    _extract_hook_decision_events,
    _extract_stream_json_events,
    _extract_stream_json_text,
    _heal_stray_backtick_before_heading,
    _render_tool_use,
    _unwrap_markdown_fences,
)


@pytest.fixture(autouse=True)
def reset_session_manager():
    """Reset ProjectSessionManager class-level state before and after each test."""
    ProjectSessionManager._sessions.clear()
    ProjectSessionManager._subscribers.clear()
    yield
    ProjectSessionManager._sessions.clear()
    ProjectSessionManager._subscribers.clear()


def _make_session_info(
    session_id="psess-test01",
    pid=1234,
    pgid=1234,
    status="active",
    paused=False,
    buffer_lines=None,
    idle_timeout_seconds=3600,
    max_lifetime_seconds=14400,
    created_at=None,
    last_activity_at=None,
    stream_json=False,
):
    """Helper to create a SessionInfo with sensible defaults."""
    now = datetime.now()
    ring_buffer = deque(maxlen=10000)
    if buffer_lines:
        ring_buffer.extend(buffer_lines)
    return SessionInfo(
        session_id=session_id,
        pid=pid,
        pgid=pgid,
        master_fd=99,
        ring_buffer=ring_buffer,
        reader_thread=MagicMock(spec=threading.Thread),
        status=status,
        created_at=created_at or now,
        last_activity_at=last_activity_at or now,
        paused=paused,
        idle_timeout_seconds=idle_timeout_seconds,
        max_lifetime_seconds=max_lifetime_seconds,
        stream_json=stream_json,
    )


# ---------------------------------------------------------------------------
# _extract_stream_json_text
# ---------------------------------------------------------------------------


class TestExtractStreamJsonText:
    def test_non_json_passthrough(self):
        assert _extract_stream_json_text("plain text line") == "plain text line"

    def test_assistant_event_with_text(self):
        event = {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Hello world"}]},
        }
        result = _extract_stream_json_text(json.dumps(event))
        assert result == "Hello world"

    def test_system_event_is_filtered(self):
        """v0.7.48 — ``system/init`` events (with their multi-KB tool
        registry) must not surface in chat. Critical regression: when
        the reader's time-based flush kicked in on a split event, the
        partial bytes leaked through as plain text."""
        event = {
            "type": "system",
            "subtype": "init",
            "tools": ["Bash", "Read"] * 50,  # bulk it up like a real init
        }
        assert _extract_stream_json_text(json.dumps(event)) is None

    def test_assistant_event_with_tool_use(self):
        event = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "/tmp/x.py"}}
                ]
            },
        }
        result = _extract_stream_json_text(json.dumps(event))
        assert "Read" in result
        assert "/tmp/x.py" in result

    def test_result_event_is_suppressed(self):
        """v0.7.43 — ``result`` events are intentionally dropped because
        in ``--input-format stream-json`` interactive chat they duplicate
        the text the ``assistant`` event already emitted, producing a
        second copy of every answer in the chat panel."""
        for payload in (
            {"type": "result", "result": "Done!"},
            {"type": "result", "result": {"text": "Finished"}},
            {"type": "result", "result": {"content": "Wrapped"}},
            {"type": "result"},  # no result key at all
        ):
            assert _extract_stream_json_text(json.dumps(payload)) is None

    def test_content_block_delta_text(self):
        event = {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "hi"}}
        assert _extract_stream_json_text(json.dumps(event)) == "hi"


def _strip_turn_done(events: list) -> list:
    """v0.7.74 — filter out the synthetic ``turn_done`` event the
    parser now appends to assistant turns. The event is a
    boundary marker for in-process consumers (goal-loop runner);
    it doesn't change what the chat UI sees. Tests that predate
    v0.7.74 assert on the user-visible events only, so they wrap
    the call with this helper."""
    return [e for e in events if e[0] != "turn_done"]


class TestExtractStreamJsonEvents:
    """v0.7.63 — ``_extract_stream_json_events`` returns an ordered list
    of ``(event_type, data)`` tuples so the reader thread can broadcast
    side-channel events (like ``AskUserQuestion``) alongside the
    text/tool-use bubble content."""

    def test_streaming_turn_emits_turn_done_with_accumulated_deltas(self):
        """v0.7.74 Codex blocker #2: when ``--include-partial-messages``
        streams text through ``content_block_delta`` and the
        trailing ``assistant`` event drops the text blocks
        (``skip_text``), the ``turn_done`` text must still carry
        what the user actually saw — pulled from the per-session
        delta accumulator.
        """
        si = _make_session_info(stream_json=True)
        # Stream two delta chunks.
        _extract_stream_json_events(
            json.dumps(
                {
                    "type": "content_block_delta",
                    "delta": {"type": "text_delta", "text": "Hello "},
                }
            ),
            session_info=si,
        )
        _extract_stream_json_events(
            json.dumps(
                {
                    "type": "content_block_delta",
                    "delta": {"type": "text_delta", "text": "world."},
                }
            ),
            session_info=si,
        )
        # Trailing assistant event with the same text — should be
        # skipped on the output side, but turn_done picks up the
        # accumulated delta text.
        events = _extract_stream_json_events(
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [{"type": "text", "text": "Hello world."}]
                    },
                }
            ),
            session_info=si,
        )
        turn_done = [e for e in events if e[0] == "turn_done"]
        assert turn_done, "turn_done must always fire at end of assistant event"
        assert turn_done[0][1]["text"] == "Hello world."
        # Accumulator was reset.
        assert si.pending_turn_text == ""

    def test_tool_use_only_turn_still_emits_turn_done(self):
        """v0.7.74 Codex blocker #3: a turn containing only a side-
        channel tool_use (AskUserQuestion / ExitPlanMode) must
        still tick the goal-loop runner's iteration counter, so
        ``turn_done`` fires even with empty text.
        """
        event = {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_q",
                        "name": "AskUserQuestion",
                        "input": {
                            "questions": [
                                {
                                    "question": "ok?",
                                    "options": [{"label": "yes"}],
                                }
                            ]
                        },
                    }
                ]
            },
        }
        events = _extract_stream_json_events(json.dumps(event))
        # ask_user_question event AND a turn_done (empty text is fine).
        kinds = [e[0] for e in events]
        assert "ask_user_question" in kinds
        assert "turn_done" in kinds
        turn_done = next(e for e in events if e[0] == "turn_done")
        assert turn_done[1]["text"] == ""

    def test_exit_plan_mode_text_flows_into_turn_done(self):
        """v0.7.74 Codex nit: the ExitPlanMode plan body is part
        of what the judge needs to assess. ``turn_done.text``
        must include the plan content so the judge sees the
        proposal alongside any prose.
        """
        event = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "Here's the plan:"},
                    {
                        "type": "tool_use",
                        "id": "toolu_plan",
                        "name": "ExitPlanMode",
                        "input": {"plan": "## Step 1\nFoo\n\n## Step 2\nBar"},
                    },
                ]
            },
        }
        events = _extract_stream_json_events(json.dumps(event))
        turn_done = next(e for e in events if e[0] == "turn_done")
        assert "Here's the plan:" in turn_done[1]["text"]
        assert "[plan proposed]" in turn_done[1]["text"]
        assert "## Step 1" in turn_done[1]["text"]
        assert "## Step 2" in turn_done[1]["text"]

    def test_assistant_text_only_yields_output_then_turn_done(self):
        # v0.7.74 — the assistant turn parser now appends a
        # synthetic ``turn_done`` event after the user-visible
        # output events so in-process consumers (goal-loop runner)
        # have a clean turn-boundary signal. Browser-bound SSE
        # subscribers see both (turn_done is harmless on the
        # frontend's existing handler map — it falls through).
        event = {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "hello"}]},
        }
        events = _extract_stream_json_events(json.dumps(event))
        assert events == [
            ("output", {"line": "hello"}),
            ("turn_done", {"text": "hello"}),
        ]

    def test_exit_plan_mode_split_off_as_dedicated_event(self):
        """v0.7.65 — ``ExitPlanMode`` tool_use emits its own
        ``exit_plan_mode`` SSE event so the frontend can mount an
        approve/decline card instead of treating it as a generic
        chip."""
        event = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "Here's my plan:"},
                    {
                        "type": "tool_use",
                        "id": "toolu_plan",
                        "name": "ExitPlanMode",
                        "input": {
                            "plan": "## Step 1\nDo X\n\n## Step 2\nDo Y",
                        },
                    },
                ]
            },
        }
        events = _strip_turn_done(_extract_stream_json_events(json.dumps(event)))
        assert len(events) == 2
        assert events[0] == ("output", {"line": "Here's my plan:"})
        assert events[1][0] == "exit_plan_mode"
        assert events[1][1]["tool_use_id"] == "toolu_plan"
        assert events[1][1]["plan"].startswith("## Step 1")

    def test_ask_user_question_split_off_from_surrounding_text(self):
        questions = [
            {
                "question": "Pick one",
                "header": "Pick",
                "multiSelect": False,
                "options": [
                    {"label": "A", "description": "a"},
                    {"label": "B", "description": "b"},
                ],
            }
        ]
        event = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "Need your input:"},
                    {
                        "type": "tool_use",
                        "id": "toolu_abc",
                        "name": "AskUserQuestion",
                        "input": {"questions": questions},
                    },
                    {"type": "text", "text": "Thanks."},
                ]
            },
        }
        events = _strip_turn_done(_extract_stream_json_events(json.dumps(event)))
        # 3 events, chronological order preserved
        assert len(events) == 3
        assert events[0] == ("output", {"line": "Need your input:"})
        assert events[1][0] == "ask_user_question"
        assert events[1][1]["tool_use_id"] == "toolu_abc"
        assert events[1][1]["questions"] == questions
        assert events[2] == ("output", {"line": "Thanks."})

    def test_other_tool_use_stays_in_output_bubble(self):
        """Non-AskUserQuestion tools still render as chips in the
        ``output`` event."""
        event = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "Reading file."},
                    {
                        "type": "tool_use",
                        "id": "toolu_read",
                        "name": "Read",
                        "input": {"file_path": "/etc/hosts"},
                    },
                ]
            },
        }
        events = _strip_turn_done(_extract_stream_json_events(json.dumps(event)))
        assert len(events) == 1
        ev_type, ev_data = events[0]
        assert ev_type == "output"
        assert "Reading file." in ev_data["line"]
        assert 'tool-call--file' in ev_data["line"]

    def test_unknown_event_returns_empty_list(self):
        for payload in (
            {"type": "system", "subtype": "init"},
            {"type": "result"},
            {"type": "rate_limit_event"},
        ):
            assert _extract_stream_json_events(json.dumps(payload)) == []

    def test_hook_response_with_permission_decision_emits_badge(self):
        """v0.7.66 — a system/hook_response with a PreToolUse
        permission decision in its ``output`` should become a
        ``hook_decision`` SSE event for the read-only badge."""
        hook_event = {
            "type": "system",
            "subtype": "hook_response",
            "hook_event": "PreToolUse",
            "hook_name": "approve-bash",
            "tool_name": "Bash",
            "tool_input": {"command": "ls /tmp"},
            "outcome": "success",
            "output": json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "allow",
                    }
                }
            ),
        }
        events = _extract_stream_json_events(json.dumps(hook_event))
        assert len(events) == 1
        ev_type, payload = events[0]
        assert ev_type == "hook_decision"
        assert payload["decision"] == "allow"
        assert payload["tool_name"] == "Bash"
        assert payload["tool_input"] == {"command": "ls /tmp"}
        assert payload["outcome"] == "success"

    def test_hook_response_without_permission_is_filtered(self):
        """Hooks that just write to stdout or have no
        ``hookSpecificOutput.permissionDecision`` are noise and
        should NOT show up as badges."""
        hook_event = {
            "type": "system",
            "subtype": "hook_response",
            "hook_event": "SessionStart",
            "hook_name": "context-mode-init",
            "output": json.dumps(
                {"hookSpecificOutput": {"additionalContext": "boilerplate"}}
            ),
        }
        assert _extract_stream_json_events(json.dumps(hook_event)) == []
        # Also non-JSON output
        hook_event["output"] = "[HarnessSync] 11 targets out of sync"
        assert _extract_stream_json_events(json.dumps(hook_event)) == []
        # Empty output
        hook_event["output"] = ""
        assert _extract_stream_json_events(json.dumps(hook_event)) == []

    def test_delta_emits_output_delta_event(self):
        """v0.7.67 — ``content_block_delta`` text events now go out
        as ``output_delta`` (no separator) instead of ``output``."""
        event = {
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "Hello"},
        }
        events = _extract_stream_json_events(json.dumps(event))
        assert events == [("output_delta", {"text": "Hello"})]

    def test_assistant_text_skipped_after_delta_when_state_carried(self):
        """When the session has seen recent deltas, the trailing
        ``assistant`` event's text block is dropped (deltas already
        streamed it). Tool_use blocks still come through."""
        si = _make_session_info(stream_json=True)
        si.had_recent_delta = True

        event = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "Hello world"},
                    {
                        "type": "tool_use",
                        "id": "toolu_x",
                        "name": "Read",
                        "input": {"file_path": "/etc/hosts"},
                    },
                ]
            },
        }
        events = _strip_turn_done(
            _extract_stream_json_events(json.dumps(event), session_info=si)
        )
        # No output with "Hello world" — only the tool chip.
        assert len(events) == 1
        ev_type, ev_data = events[0]
        assert ev_type == "output"
        assert "Hello world" not in ev_data["line"]
        assert "tool-call--file" in ev_data["line"]
        # State reset for the next turn.
        assert si.had_recent_delta is False

    def test_delta_then_assistant_state_flow(self):
        """End-to-end: a delta sets state, the assistant event consumes
        it and resets, the next delta starts a fresh streaming turn."""
        si = _make_session_info(stream_json=True)
        # Turn 1
        _extract_stream_json_events(
            json.dumps(
                {
                    "type": "content_block_delta",
                    "delta": {"type": "text_delta", "text": "Hi"},
                }
            ),
            session_info=si,
        )
        assert si.had_recent_delta is True
        _extract_stream_json_events(
            json.dumps(
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": "Hi"}]},
                }
            ),
            session_info=si,
        )
        assert si.had_recent_delta is False  # reset

        # Turn 2: a fresh delta should set it again
        _extract_stream_json_events(
            json.dumps(
                {
                    "type": "content_block_delta",
                    "delta": {"type": "text_delta", "text": "Sec"},
                }
            ),
            session_info=si,
        )
        assert si.had_recent_delta is True

    def test_assistant_text_kept_when_no_state(self):
        """Without ``session_info`` (existing tests, back-compat), text
        blocks are always preserved."""
        event = {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Hello"}]},
        }
        events = _strip_turn_done(_extract_stream_json_events(json.dumps(event)))
        assert events == [("output", {"line": "Hello"})]

    def test_thinking_block_emits_dedicated_event(self):
        """v0.7.68 — extended-thinking ``thinking`` content blocks
        emit as ``thinking`` SSE events, not text output."""
        event = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "thinking", "thinking": "Let me reason..."},
                    {"type": "text", "text": "The answer is 42."},
                ]
            },
        }
        events = _strip_turn_done(_extract_stream_json_events(json.dumps(event)))
        # Two events: thinking (first), then output with the text.
        assert len(events) == 2
        assert events[0] == ("thinking", {"text": "Let me reason..."})
        assert events[1] == ("output", {"line": "The answer is 42."})

    def test_thinking_block_preserves_chronological_order(self):
        """A thinking block AFTER text flushes pending text first so
        the chat renders text → thinking → following text in order."""
        event = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "Quick answer:"},
                    {"type": "thinking", "thinking": "actually let me reconsider"},
                    {"type": "text", "text": "Final answer: 42"},
                ]
            },
        }
        events = _strip_turn_done(_extract_stream_json_events(json.dumps(event)))
        assert len(events) == 3
        assert events[0] == ("output", {"line": "Quick answer:"})
        assert events[1] == ("thinking", {"text": "actually let me reconsider"})
        assert events[2] == ("output", {"line": "Final answer: 42"})

    def test_empty_thinking_is_filtered(self):
        """No ``thinking`` event for an empty/missing thinking body."""
        event = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "thinking", "thinking": ""},
                    {"type": "text", "text": "Hello"},
                ]
            },
        }
        events = _strip_turn_done(_extract_stream_json_events(json.dumps(event)))
        assert events == [("output", {"line": "Hello"})]

    def test_hook_response_with_deny_decision(self):
        hook_event = {
            "type": "system",
            "subtype": "hook_response",
            "hook_event": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /"},
            "outcome": "success",
            "output": json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                    }
                }
            ),
        }
        events = _extract_stream_json_events(json.dumps(hook_event))
        assert len(events) == 1
        assert events[0][1]["decision"] == "deny"

    def test_non_json_line_passes_through(self):
        events = _extract_stream_json_events("plain text line")
        assert events == [("output", {"line": "plain text line"})]


class TestHealStrayBacktickBeforeHeading:
    r"""v0.7.64 — claude sometimes inlines a file or block of code
    under a single (never-closed) backtick:

        "Here's the file:`# Heading\\n..."

    Marked treats the lone ` as a literal and the rest as one
    paragraph; ``#`` is no longer at line-start so no h1 renders.
    ``_heal_stray_backtick_before_heading`` recovers the structure
    by replacing the backtick with a paragraph break."""

    def test_replaces_backtick_immediately_before_h1(self):
        text = "Here's the file (99 lines):`# Title\nbody"
        out = _heal_stray_backtick_before_heading(text)
        assert out == "Here's the file (99 lines):\n\n# Title\nbody"

    def test_replaces_for_all_atx_levels(self):
        for hashes in ("#", "##", "###", "####", "#####", "######"):
            text = f"intro:`{hashes} Heading\nbody"
            out = _heal_stray_backtick_before_heading(text)
            assert out == f"intro:\n\n{hashes} Heading\nbody"

    def test_preserves_balanced_inline_code(self):
        """A backtick that's followed by non-header text is a real
        inline code span — leave it alone."""
        text = "Run `npm install` to install"
        assert _heal_stray_backtick_before_heading(text) == text

    def test_preserves_fenced_code_blocks(self):
        """Triple-backtick fences shouldn't be touched."""
        text = "Some text\n```bash\n# This is a comment\necho hi\n```"
        assert _heal_stray_backtick_before_heading(text) == text

    def test_no_change_when_no_backtick(self):
        text = "intro\n\n# Title\nbody"
        assert _heal_stray_backtick_before_heading(text) == text

    def test_at_line_start_no_match(self):
        """The pattern requires a non-whitespace char before the
        backtick — ``\\n`# Title`` shouldn't match (that's likely
        a real fence-open with stray whitespace)."""
        text = "\n`# Title\nbody"
        assert _heal_stray_backtick_before_heading(text) == text


class TestUnwrapMarkdownFences:
    """v0.7.53 — when claude wraps file contents in a ``markdown``
    fence, lift them out so marked renders the document instead of
    showing literal ``#`` characters in a code block."""

    def test_unwraps_markdown_lang(self):
        text = "Contents:\n\n```markdown\n# Heading\n\nbody\n```\n"
        out = _unwrap_markdown_fences(text)
        assert "```" not in out
        assert "# Heading" in out
        assert "body" in out

    def test_unwraps_md_lang(self):
        text = "```md\n# Title\n```"
        out = _unwrap_markdown_fences(text)
        assert "# Title" in out
        assert "```" not in out

    def test_preserves_other_fence_languages(self):
        # bash / python / json / untagged fences are code samples;
        # they must NOT be unwrapped.
        for fence_lang in ("bash", "python", "json", ""):
            text = f"```{fence_lang}\nprint('hi')\n```"
            assert _unwrap_markdown_fences(text) == text

    def test_handles_multiple_markdown_fences(self):
        text = (
            "first:\n```markdown\n# one\n```\n\n"
            "second:\n```md\n# two\n```\n"
        )
        out = _unwrap_markdown_fences(text)
        assert "# one" in out
        assert "# two" in out
        assert "```" not in out

    def test_no_markdown_fence_is_a_noop(self):
        text = "plain prose with `inline` code"
        assert _unwrap_markdown_fences(text) == text


class TestRenderToolUse:
    """v0.7.51 — tool_use blocks render as collapsible HTML widgets
    (``<details>`` + chip-styled summary + ``<pre>`` body) so chat
    panels can show distinct tag styling for tool names / paths and
    let users click-to-expand the full input."""

    def test_bash_returns_details_with_shell_kind(self):
        rendered = _render_tool_use(
            {"name": "Bash", "input": {"command": "ls /tmp"}}
        )
        assert '<details class="tool-call tool-call--shell">' in rendered
        assert '<span class="tool-name">▸ Bash</span>' in rendered
        # Command chip in the summary…
        assert '<code class="tool-arg">ls /tmp</code>' in rendered
        # …and full JSON input in the expanded body. ``html.escape``
        # turns the JSON quotes into ``&quot;`` — that's the wire
        # form ``v-html`` will hand to the browser.
        assert '<pre class="tool-detail">' in rendered
        assert "&quot;command&quot;: &quot;ls /tmp&quot;" in rendered
        assert "</details>" in rendered

    def test_file_ops_use_path_chip(self):
        for name in ("Read", "Edit", "Write", "MultiEdit", "NotebookEdit"):
            rendered = _render_tool_use(
                {"name": name, "input": {"file_path": "/etc/hosts"}}
            )
            assert f'<span class="tool-name">▸ {name}</span>' in rendered
            assert '<code class="tool-path">/etc/hosts</code>' in rendered
            assert "tool-call--file" in rendered

    def test_grep_renders_pattern_and_path_chips(self):
        rendered = _render_tool_use(
            {"name": "Grep", "input": {"pattern": "TODO", "path": "src/"}}
        )
        assert '<code class="tool-pattern">TODO</code>' in rendered
        assert '<span class="tool-sep">in</span>' in rendered
        assert '<code class="tool-path">src/</code>' in rendered
        assert "tool-call--search" in rendered

    def test_mcp_tool_short_arg_inline_chip(self):
        rendered = _render_tool_use(
            {
                "name": "mcp__plugin_context-mode__ctx_search",
                "input": {"query": "session manager"},
            }
        )
        assert '<code class="tool-arg">session manager</code>' in rendered
        assert "tool-call--tool" in rendered

    def test_long_arg_is_truncated_in_summary_full_in_body(self):
        long_query = "x" * 200
        rendered = _render_tool_use(
            {"name": "ctx_execute", "input": {"command": long_query}}
        )
        # Summary chip is one-line truncated at ~80.
        import re

        chip = re.search(r'<code class="tool-arg">([^<]*)</code>', rendered)
        assert chip is not None
        assert len(chip.group(1)) <= 81  # 80 + ellipsis
        assert chip.group(1).endswith("…")
        # But the full payload is in the expanded body.
        assert long_query in rendered

    def test_tool_without_input_renders_no_args_placeholder(self):
        rendered = _render_tool_use({"name": "ToolSearch", "input": {}})
        assert '<span class="tool-name">▸ ToolSearch</span>' in rendered
        assert '<div class="tool-detail-empty">(no arguments)</div>' in rendered

    def test_html_is_escaped_in_chips_and_body(self):
        """A path / command with HTML-sensitive chars must not break
        out of the chip — DOMPurify sanitizes downstream but we
        still emit safe HTML at the source."""
        rendered = _render_tool_use(
            {
                "name": "Bash",
                "input": {"command": "echo '<script>x</script>'"},
            }
        )
        assert "<script>" not in rendered
        assert "&lt;script&gt;" in rendered

    def test_task_renders_subagent_and_description(self):
        rendered = _render_tool_use(
            {
                "name": "Task",
                "input": {
                    "subagent_type": "Explore",
                    "description": "find session manager",
                },
            }
        )
        assert "tool-call--task" in rendered
        assert '<span class="tool-meta">(Explore)</span>' in rendered
        assert '<code class="tool-arg">find session manager</code>' in rendered

    def test_content_block_delta_non_text(self):
        event = {"type": "content_block_delta", "delta": {"type": "input_json_delta"}}
        assert _extract_stream_json_text(json.dumps(event)) is None

    def test_unknown_event_type_returns_none(self):
        event = {"type": "system", "data": "init"}
        assert _extract_stream_json_text(json.dumps(event)) is None

    def test_assistant_empty_content_returns_none(self):
        event = {"type": "assistant", "message": {"content": []}}
        assert _extract_stream_json_text(json.dumps(event)) is None


# ---------------------------------------------------------------------------
# SessionInfo dataclass
# ---------------------------------------------------------------------------


class TestSessionInfo:
    def test_defaults(self):
        si = _make_session_info()
        assert si.execution_type == "direct"
        assert si.execution_mode == "autonomous"
        assert si.idle_timeout_seconds == 3600
        assert si.max_lifetime_seconds == 14400
        assert si.paused is False
        assert si.stream_json is False
        assert si.worktree_path is None


# ---------------------------------------------------------------------------
# get_session_info
# ---------------------------------------------------------------------------


class TestGetSessionInfo:
    def test_returns_none_for_unknown(self):
        assert ProjectSessionManager.get_session_info("psess-nope") is None

    def test_returns_dict_for_known(self):
        si = _make_session_info(session_id="psess-abc123", pid=42, pgid=42)
        ProjectSessionManager._sessions["psess-abc123"] = si

        info = ProjectSessionManager.get_session_info("psess-abc123")
        assert info is not None
        assert info["session_id"] == "psess-abc123"
        assert info["pid"] == 42
        assert info["status"] == "active"
        assert info["paused"] is False
        assert info["execution_type"] == "direct"
        assert info["execution_mode"] == "autonomous"
        assert "created_at" in info
        assert "last_activity_at" in info


# ---------------------------------------------------------------------------
# get_output
# ---------------------------------------------------------------------------


class TestGetOutput:
    def test_empty_for_unknown_session(self):
        assert ProjectSessionManager.get_output("psess-nope") == []

    def test_returns_last_n_lines(self):
        si = _make_session_info(buffer_lines=["line1", "line2", "line3", "line4", "line5"])
        ProjectSessionManager._sessions["psess-buf"] = si

        result = ProjectSessionManager.get_output("psess-buf", last_n=3)
        assert result == ["line3", "line4", "line5"]

    def test_returns_all_if_fewer_than_n(self):
        si = _make_session_info(buffer_lines=["a", "b"])
        ProjectSessionManager._sessions["psess-buf2"] = si

        result = ProjectSessionManager.get_output("psess-buf2", last_n=100)
        assert result == ["a", "b"]


# ---------------------------------------------------------------------------
# pause_session / resume_session
# ---------------------------------------------------------------------------


class TestPauseResume:
    @patch("app.services.project_session_manager.update_project_session")
    def test_pause_session_success(self, mock_update):
        si = _make_session_info(session_id="psess-pause")
        ProjectSessionManager._sessions["psess-pause"] = si

        result = ProjectSessionManager.pause_session("psess-pause")
        assert result is True
        assert si.paused is True
        assert si.status == "paused"
        mock_update.assert_called_once_with("psess-pause", status="paused")

    def test_pause_session_not_found(self):
        assert ProjectSessionManager.pause_session("psess-nope") is False

    @patch("app.services.project_session_manager.update_project_session")
    def test_resume_session_success(self, mock_update):
        si = _make_session_info(session_id="psess-resume", paused=True, status="paused")
        ProjectSessionManager._sessions["psess-resume"] = si

        result = ProjectSessionManager.resume_session("psess-resume")
        assert result is True
        assert si.paused is False
        assert si.status == "active"
        mock_update.assert_called_once_with("psess-resume", status="active")

    def test_resume_session_not_found(self):
        assert ProjectSessionManager.resume_session("psess-nope") is False


# ---------------------------------------------------------------------------
# send_input
# ---------------------------------------------------------------------------


class TestSendInput:
    def test_send_input_not_found(self):
        assert ProjectSessionManager.send_input("psess-nope", "hello") is False

    def test_send_input_inactive_session(self):
        si = _make_session_info(session_id="psess-done", status="completed")
        ProjectSessionManager._sessions["psess-done"] = si
        assert ProjectSessionManager.send_input("psess-done", "hello") is False

    @patch("os.write")
    def test_send_input_success(self, mock_write):
        si = _make_session_info(session_id="psess-input")
        ProjectSessionManager._sessions["psess-input"] = si

        result = ProjectSessionManager.send_input("psess-input", "hello")
        assert result is True
        mock_write.assert_called_once_with(99, b"hello\n")

    @patch("os.write", side_effect=OSError("broken pipe"))
    def test_send_input_write_failure(self, mock_write):
        si = _make_session_info(session_id="psess-fail")
        ProjectSessionManager._sessions["psess-fail"] = si

        result = ProjectSessionManager.send_input("psess-fail", "hello")
        assert result is False

    def test_send_input_pipe_mode_writes_to_popen_stdin(self):
        """v0.7.44 — pipe-mode sessions write to ``popen.stdin`` instead
        of the PTY master fd. Reserve a session with a Popen mock and
        verify ``send_input`` routes through it."""
        fake_popen = MagicMock()
        fake_popen.stdin = MagicMock()
        si = _make_session_info(session_id="psess-pipe")
        si.popen = fake_popen
        ProjectSessionManager._sessions["psess-pipe"] = si

        with patch("os.write") as mock_pty_write:
            result = ProjectSessionManager.send_input("psess-pipe", "hello")

        assert result is True
        fake_popen.stdin.write.assert_called_once_with(b"hello\n")
        fake_popen.stdin.flush.assert_called_once()
        # PTY fd path must NOT be touched in pipe mode.
        mock_pty_write.assert_not_called()

    def test_send_input_pipe_mode_handles_broken_stdin(self):
        """A closed stdin (BrokenPipeError) should surface as a clean
        False, not a traceback into the route handler."""
        fake_popen = MagicMock()
        fake_popen.stdin = MagicMock()
        fake_popen.stdin.write.side_effect = BrokenPipeError("EPIPE")
        si = _make_session_info(session_id="psess-broken")
        si.popen = fake_popen
        ProjectSessionManager._sessions["psess-broken"] = si

        result = ProjectSessionManager.send_input("psess-broken", "hi")
        assert result is False


# ---------------------------------------------------------------------------
# stop_session
# ---------------------------------------------------------------------------


class TestStopSession:
    def test_stop_session_not_found(self):
        assert ProjectSessionManager.stop_session("psess-nope") is False

    @patch("app.services.project_session_manager.update_project_session")
    @patch("os.waitpid", return_value=(1234, 0))
    @patch("os.killpg")
    def test_stop_session_success(self, mock_killpg, mock_waitpid, mock_update):
        si = _make_session_info(session_id="psess-stop", pid=1234, pgid=1234)
        ProjectSessionManager._sessions["psess-stop"] = si

        result = ProjectSessionManager.stop_session("psess-stop")
        assert result is True
        mock_killpg.assert_called_once()
        mock_update.assert_called_once()
        assert si.status == "completed"

    @patch("app.services.project_session_manager.update_project_session")
    @patch("os.waitpid", side_effect=ChildProcessError)
    @patch("os.killpg", side_effect=ProcessLookupError)
    def test_stop_session_already_dead(self, mock_killpg, mock_waitpid, mock_update):
        si = _make_session_info(session_id="psess-dead", pid=9999, pgid=9999)
        ProjectSessionManager._sessions["psess-dead"] = si

        result = ProjectSessionManager.stop_session("psess-dead")
        assert result is True


# ---------------------------------------------------------------------------
# _format_sse
# ---------------------------------------------------------------------------


class TestFormatSse:
    def test_format(self):
        result = ProjectSessionManager._format_sse("output", {"line": "hello"})
        assert result.startswith("event: output\n")
        assert '"line": "hello"' in result
        assert result.endswith("\n\n")


# ---------------------------------------------------------------------------
# Pipe transport (v0.7.44, option A) — end-to-end roundtrip
# ---------------------------------------------------------------------------


class TestPipeTransport:
    """End-to-end test for ``use_pty=False`` against a real subprocess.

    Uses ``cat`` so the test does not depend on ``claude`` being on
    PATH; ``cat`` echoes stdin to stdout line-by-line which is enough
    to verify the pipe-mode plumbing (send_input → popen.stdin →
    child → popen.stdout → reader thread → ring buffer).
    """

    def test_use_pty_false_roundtrips_input(self, tmp_path):
        # ``isolated_db`` (autouse in conftest) gives us a working
        # temp DB. The session insert needs a real project row so the
        # FK is satisfied.
        from app.db.connection import get_connection

        with get_connection() as conn:
            conn.execute(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES ('proj-pipe', 'pipe-test', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
            conn.commit()

        session_id = ProjectSessionManager.create_session(
            project_id="proj-pipe",
            cmd=["cat"],
            cwd=str(tmp_path),
            use_pty=False,
        )

        # Confirm the session is in pipe mode (not PTY).
        si = ProjectSessionManager._sessions[session_id]
        assert si.popen is not None

        sent = ProjectSessionManager.send_input(session_id, "hello-from-test")
        assert sent is True

        # The reader's select() timeout is 0.5s — poll briefly.
        import time as _time

        for _ in range(40):  # up to 4 seconds
            lines = ProjectSessionManager.get_output(session_id, last_n=10)
            if any("hello-from-test" in line for line in lines):
                break
            _time.sleep(0.1)
        else:
            pytest.fail(
                f"Pipe-mode roundtrip never surfaced the echoed line. "
                f"Buffer contents: {ProjectSessionManager.get_output(session_id)}"
            )

        ProjectSessionManager.stop_session(session_id)


# ---------------------------------------------------------------------------
# _broadcast
# ---------------------------------------------------------------------------


class TestBroadcast:
    def test_broadcast_to_subscribers(self):
        q1 = Queue()
        q2 = Queue()
        ProjectSessionManager._subscribers["psess-bc"] = [q1, q2]

        ProjectSessionManager._broadcast("psess-bc", "output", {"line": "hi"})

        msg1 = q1.get_nowait()
        msg2 = q2.get_nowait()
        assert msg1 == msg2
        assert "hi" in msg1

    def test_broadcast_no_subscribers(self):
        # Should not raise
        ProjectSessionManager._broadcast("psess-none", "output", {"line": "hi"})


# ---------------------------------------------------------------------------
# cleanup_dead_sessions
# ---------------------------------------------------------------------------


class TestCleanupDeadSessions:
    @patch("app.services.project_session_manager.update_project_session")
    @patch("os.kill", side_effect=ProcessLookupError)
    @patch(
        "app.services.project_session_manager.get_active_sessions",
        return_value=[{"id": "psess-dead1", "pid": 99999}],
    )
    def test_cleans_dead_processes(self, mock_get, mock_kill, mock_update):
        ProjectSessionManager.cleanup_dead_sessions()
        mock_update.assert_called_once()
        args, kwargs = mock_update.call_args
        assert args[0] == "psess-dead1"
        assert kwargs["status"] == "failed"

    @patch("os.kill")  # No error means process is alive
    @patch(
        "app.services.project_session_manager.get_active_sessions",
        return_value=[{"id": "psess-alive", "pid": 12345}],
    )
    def test_leaves_alive_processes(self, mock_get, mock_kill):
        with patch("app.services.project_session_manager.update_project_session") as mock_update:
            ProjectSessionManager.cleanup_dead_sessions()
            mock_update.assert_not_called()

    @patch(
        "app.services.project_session_manager.get_active_sessions",
        side_effect=Exception("DB error"),
    )
    def test_handles_db_error(self, mock_get):
        # Should not raise
        ProjectSessionManager.cleanup_dead_sessions()

    @patch("os.kill", side_effect=PermissionError)
    @patch(
        "app.services.project_session_manager.get_active_sessions",
        return_value=[{"id": "psess-perm", "pid": 1}],
    )
    def test_permission_error_leaves_session(self, mock_get, mock_kill):
        with patch("app.services.project_session_manager.update_project_session") as mock_update:
            ProjectSessionManager.cleanup_dead_sessions()
            mock_update.assert_not_called()

    @patch(
        "app.services.project_session_manager.get_active_sessions",
        return_value=[{"id": "psess-nopid", "pid": None}],
    )
    def test_skips_sessions_without_pid(self, mock_get):
        with patch("app.services.project_session_manager.update_project_session") as mock_update:
            ProjectSessionManager.cleanup_dead_sessions()
            mock_update.assert_not_called()


# ---------------------------------------------------------------------------
# check_resource_limits
# ---------------------------------------------------------------------------


class TestCheckResourceLimits:
    @patch.object(ProjectSessionManager, "stop_session")
    def test_idle_timeout(self, mock_stop):
        si = _make_session_info(
            session_id="psess-idle",
            idle_timeout_seconds=60,
            last_activity_at=datetime.now() - timedelta(seconds=120),
        )
        ProjectSessionManager._sessions["psess-idle"] = si

        ProjectSessionManager.check_resource_limits()
        mock_stop.assert_called_once_with("psess-idle")

    @patch.object(ProjectSessionManager, "stop_session")
    def test_max_lifetime(self, mock_stop):
        si = _make_session_info(
            session_id="psess-old",
            max_lifetime_seconds=60,
            created_at=datetime.now() - timedelta(seconds=120),
        )
        ProjectSessionManager._sessions["psess-old"] = si

        ProjectSessionManager.check_resource_limits()
        mock_stop.assert_called_once_with("psess-old")

    @patch.object(ProjectSessionManager, "stop_session")
    def test_within_limits(self, mock_stop):
        si = _make_session_info(session_id="psess-ok")
        ProjectSessionManager._sessions["psess-ok"] = si

        ProjectSessionManager.check_resource_limits()
        mock_stop.assert_not_called()

    @patch.object(ProjectSessionManager, "stop_session")
    def test_skips_completed_sessions(self, mock_stop):
        si = _make_session_info(
            session_id="psess-done",
            status="completed",
            idle_timeout_seconds=1,
            last_activity_at=datetime.now() - timedelta(seconds=9999),
        )
        ProjectSessionManager._sessions["psess-done"] = si

        ProjectSessionManager.check_resource_limits()
        mock_stop.assert_not_called()


# ---------------------------------------------------------------------------
# subscribe (partial — tests the non-blocking paths)
# ---------------------------------------------------------------------------


class TestSubscribe:
    def test_subscribe_completed_session(self):
        si = _make_session_info(session_id="psess-comp", status="completed", buffer_lines=["line1"])
        ProjectSessionManager._sessions["psess-comp"] = si

        events = list(ProjectSessionManager.subscribe("psess-comp"))
        # Should get catchup output + complete event
        assert len(events) == 2
        assert "line1" in events[0]
        assert "complete" in events[1]

    def test_subscribe_unknown_session(self):
        events = list(ProjectSessionManager.subscribe("psess-unknown"))
        assert len(events) == 1
        assert "error" in events[0]
        assert "Session not found" in events[0]


# ---------------------------------------------------------------------------
# v0.7.97 — SessionPersistError cleanup (PR #139 deferred MINOR)
# ---------------------------------------------------------------------------


class TestSessionPersistErrorCleanup:
    """When ``create_session``'s post-spawn INSERT fails with a FK
    violation (the SA-bridge race), the PSM must:
      1. Stop the just-spawned subprocess.
      2. Drop the in-memory ``_sessions`` entry so the SSE/output
         surfaces don't return data for a session the DB has no
         record of.
      3. Raise ``SessionPersistError`` so the caller (the bridge
         route) can turn it into a 409 instead of letting it
         escape as a 500.
    """

    def test_session_persist_error_is_exported(self):
        # Smoke test the symbol is reachable from the module.
        from app.services.project_session_manager import SessionPersistError

        assert issubclass(SessionPersistError, RuntimeError)
        err = SessionPersistError("boom")
        assert str(err) == "boom"
        # Default structured fields are None when omitted.
        assert err.session_id is None
        assert err.constraint_hint is None

    def test_session_persist_error_structured_fields(self):
        """v0.7.97 codex pass-2 NIT: SessionPersistError carries
        ``session_id`` + ``constraint_hint`` so log scrapers and
        future UI surfaces can disambiguate races without parsing
        the message string.
        """
        from app.services.project_session_manager import SessionPersistError

        err = SessionPersistError(
            "msg", session_id="psess-x", constraint_hint="super_agent_id"
        )
        assert err.session_id == "psess-x"
        assert err.constraint_hint == "super_agent_id"

    def test_extract_fk_hint_parses_column_name(self):
        from app.services.project_session_manager import _extract_fk_hint

        # SQLite default message — no column → None.
        assert _extract_fk_hint("FOREIGN KEY constraint failed") is None
        # Hypothetical informative message — column extracted.
        assert (
            _extract_fk_hint(
                "FOREIGN KEY constraint failed (super_agent_id)"
            )
            == "super_agent_id"
        )
        # Unrecognized column — None.
        assert _extract_fk_hint("FOREIGN KEY constraint failed (custom_id)") is None

    def test_fk_failure_kills_subprocess_and_drops_entry(self, monkeypatch):
        """Exercise the exception path without spawning a real
        subprocess: pre-seed a fake ``_sessions`` entry, run the
        cleanup logic directly via a patched IntegrityError.
        """
        import sqlite3 as _sqlite3
        from app.services.project_session_manager import (
            ProjectSessionManager,
            SessionPersistError,
        )

        sid = "psess-racetest"
        ProjectSessionManager._sessions[sid] = _make_session_info(
            session_id=sid
        )

        stop_calls: list[dict] = []

        # Updated signature: stop_session now accepts ``wait`` kwarg
        # (v0.7.97 fast-kill path for the FK-cleanup branch).
        def fake_stop(session_id, wait=True):
            stop_calls.append({"session_id": session_id, "wait": wait})
            return True

        monkeypatch.setattr(ProjectSessionManager, "stop_session", fake_stop)

        # Reproduce the except-branch behaviour directly so the
        # test stays hermetic (no fork/spawn). This mirrors the
        # cleanup block inside ``create_session``.
        try:
            try:
                raise _sqlite3.IntegrityError(
                    "FOREIGN KEY constraint failed (super_agent_id)"
                )
            except _sqlite3.IntegrityError as exc:
                from app.services.project_session_manager import _extract_fk_hint

                hint = _extract_fk_hint(str(exc))
                ProjectSessionManager.stop_session(sid, wait=False)
                with ProjectSessionManager._lock:
                    ProjectSessionManager._sessions.pop(sid, None)
                raise SessionPersistError(
                    "Session persist failed: parent resource missing",
                    session_id=sid,
                    constraint_hint=hint,
                ) from exc
        except SessionPersistError as caught:
            assert "parent resource missing" in str(caught)
            assert caught.session_id == sid
            assert caught.constraint_hint == "super_agent_id"
        else:
            raise AssertionError("SessionPersistError not raised")

        # Subprocess kill attempted with the fast-kill flag, in-
        # memory entry gone.
        assert stop_calls == [{"session_id": sid, "wait": False}], (
            f"stop_session must be called with wait=False; got {stop_calls}"
        )
        assert sid not in ProjectSessionManager._sessions

    def test_watchdog_escalates_to_sigkill_when_sigterm_ignored(
        self, monkeypatch
    ):
        """v0.7.97 codex pass-3 MINOR coverage: when the spawned
        process ignores SIGTERM and runs past the grace window,
        the watchdog must SIGKILL the pgid. PTY path (popen=None).
        """
        import threading as _threading

        from app.services.project_session_manager import (
            ProjectSessionManager,
        )

        killpg_calls: list[tuple] = []

        def fake_killpg(pgid, sig):
            killpg_calls.append((pgid, sig))

        # popen=None simulates a PTY (fork-based) session. waitpid
        # with WNOHANG returning (0, 0) means "still running" — the
        # watchdog never sees an exit and escalates to SIGKILL.
        def fake_waitpid(_pid, _flags):
            return (0, 0)

        monkeypatch.setattr(
            "app.services.project_session_manager.os.killpg", fake_killpg
        )
        monkeypatch.setattr(
            "app.services.project_session_manager.os.waitpid", fake_waitpid
        )
        # Collapse the grace window: sleep no-op + monotonic jumps
        # past the deadline on the second call.
        monkeypatch.setattr(
            "app.services.project_session_manager.time.sleep",
            lambda _: None,
        )
        monotonic_values = iter([0.0, 10.0])
        monkeypatch.setattr(
            "app.services.project_session_manager.time.monotonic",
            lambda: next(monotonic_values),
        )

        sid = "psess-watchdog-escalate"
        ProjectSessionManager._spawn_kill_watchdog(sid, 9001, 9001, None)

        # Wait for the daemon thread to run.
        for _ in range(50):
            if killpg_calls:
                break
            _threading.Event().wait(0.02)

        import signal as _signal

        assert (9001, _signal.SIGKILL) in killpg_calls, (
            f"watchdog must SIGKILL when SIGTERM ignored; got {killpg_calls}"
        )

    def test_watchdog_returns_when_process_exits_naturally(
        self, monkeypatch
    ):
        """v0.7.97 — when the process exits inside the grace
        window (popen.poll() returns non-None), the watchdog must
        NOT send SIGKILL. Pop-mode path.
        """
        import threading as _threading
        from types import SimpleNamespace

        from app.services.project_session_manager import (
            ProjectSessionManager,
        )

        killpg_calls: list[tuple] = []

        def fake_killpg(pgid, sig):
            killpg_calls.append((pgid, sig))

        monkeypatch.setattr(
            "app.services.project_session_manager.os.killpg", fake_killpg
        )
        monkeypatch.setattr(
            "app.services.project_session_manager.time.sleep",
            lambda _: None,
        )
        # Always within the grace window — loop polls poll() and
        # exits naturally on the first iteration.
        monkeypatch.setattr(
            "app.services.project_session_manager.time.monotonic",
            lambda: 0.0,
        )

        # popen.poll() returns 0 = exited cleanly.
        popen = SimpleNamespace(
            poll=lambda: 0,
            wait=lambda timeout=None: 0,
        )

        sid = "psess-watchdog-natural"
        ProjectSessionManager._spawn_kill_watchdog(sid, 9100, 9100, popen)

        _threading.Event().wait(0.1)

        assert killpg_calls == [], (
            "watchdog must not SIGKILL when process exited naturally; "
            f"got {killpg_calls}"
        )

    def test_watchdog_pty_path_returns_on_reaped_child(self, monkeypatch):
        """v0.7.97 — PTY session (popen=None) uses
        ``os.waitpid(pid, WNOHANG)``. When it returns a non-zero
        first element (the child was reaped), the watchdog must
        return without escalating to SIGKILL.
        """
        import threading as _threading

        from app.services.project_session_manager import (
            ProjectSessionManager,
        )

        killpg_calls: list[tuple] = []

        def fake_killpg(pgid, sig):
            killpg_calls.append((pgid, sig))

        # Return (pid, exit_status) — child was reaped → return early.
        def fake_waitpid(pid, _flags):
            return (pid, 0)

        monkeypatch.setattr(
            "app.services.project_session_manager.os.killpg", fake_killpg
        )
        monkeypatch.setattr(
            "app.services.project_session_manager.os.waitpid", fake_waitpid
        )
        monkeypatch.setattr(
            "app.services.project_session_manager.time.sleep",
            lambda _: None,
        )
        monkeypatch.setattr(
            "app.services.project_session_manager.time.monotonic",
            lambda: 0.0,
        )

        sid = "psess-watchdog-pty"
        ProjectSessionManager._spawn_kill_watchdog(sid, 9200, 9200, None)

        _threading.Event().wait(0.1)

        assert killpg_calls == [], (
            "watchdog PTY path must not SIGKILL when waitpid reports "
            f"the child was reaped; got {killpg_calls}"
        )

    def test_stop_session_wait_false_spawns_kill_watchdog(self, monkeypatch):
        """v0.7.97 codex pass-2 MINOR — ``wait=False`` must spawn a
        background watchdog that handles SIGTERM-ignoring children.
        Without it, the FK-cleanup branch drops the ``_sessions``
        entry and the process becomes invisible to the periodic
        sweep + crash-recovery path.
        """
        from app.services.project_session_manager import (
            ProjectSessionManager,
        )

        sid = "psess-watchdog"
        ProjectSessionManager._sessions[sid] = _make_session_info(
            session_id=sid, pid=4242, pgid=4242
        )

        watchdog_calls: list[tuple] = []

        def fake_spawn(session_id, pid, pgid, popen, *args, **kwargs):
            watchdog_calls.append((session_id, pid, pgid))

        # Stub the syscalls + the watchdog spawner so we don't fork.
        monkeypatch.setattr(
            "app.services.project_session_manager.os.killpg",
            lambda *_a, **_k: None,
        )
        monkeypatch.setattr(
            ProjectSessionManager, "_spawn_kill_watchdog", fake_spawn
        )

        assert ProjectSessionManager.stop_session(sid, wait=False) is True
        assert watchdog_calls == [(sid, 4242, 4242)], (
            f"wait=False must spawn the kill watchdog; got {watchdog_calls}"
        )

        ProjectSessionManager._sessions.pop(sid, None)

    def test_stop_session_wait_false_skips_5s_wait(self, monkeypatch):
        """v0.7.97 — ``wait=False`` sends SIGTERM and returns
        immediately on the *main thread* without entering the 5s
        wait loop. (The watchdog runs in a daemon thread and is
        verified by ``test_stop_session_wait_false_spawns_kill_watchdog``
        above — stubbed here so its own ``time.sleep`` calls don't
        trip the boom_sleep guard.)
        """
        from app.services.project_session_manager import (
            ProjectSessionManager,
        )

        sid = "psess-fastkill"
        ProjectSessionManager._sessions[sid] = _make_session_info(
            session_id=sid, pid=12345, pgid=12345
        )

        killpg_calls: list[tuple] = []

        def fake_killpg(pgid, sig):
            killpg_calls.append((pgid, sig))

        def boom_sleep(_):
            raise AssertionError(
                "stop_session(wait=False) must not call time.sleep "
                "on the main thread"
            )

        monkeypatch.setattr(
            "app.services.project_session_manager.os.killpg", fake_killpg
        )
        monkeypatch.setattr(
            "app.services.project_session_manager.time.sleep", boom_sleep
        )
        # Stub the watchdog so its background thread's time.sleep
        # doesn't fire the boom_sleep guard.
        monkeypatch.setattr(
            ProjectSessionManager,
            "_spawn_kill_watchdog",
            lambda *_a, **_k: None,
        )

        result = ProjectSessionManager.stop_session(sid, wait=False)
        assert result is True
        # SIGTERM delivered exactly once; no SIGKILL escalation on
        # the main thread.
        import signal as _signal

        assert killpg_calls == [(12345, _signal.SIGTERM)]

        # Cleanup.
        ProjectSessionManager._sessions.pop(sid, None)
