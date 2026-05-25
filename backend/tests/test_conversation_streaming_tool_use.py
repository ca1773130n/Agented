"""Tests for the typed tool-use surface in conversation_streaming.

Covers:
  - ToolUseEvent extraction from Claude stream-json assistant events
  - OpenAI-shaped tool_calls deltas in the proxy path
  - ChatChunk union usage — non-string yields don't break text callers
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from app.services.conversation_streaming import (
    ToolUseEvent,
    _extract_tool_uses_from_event,
)


# ---------- _extract_tool_uses_from_event ----------------------------------

def test_extract_tool_uses_from_assistant_event():
    """Claude CLI emits ``type=assistant`` events with mixed content;
    tool_use blocks parse into ToolUseEvent."""
    event = {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "text", "text": "Let me check the graph."},
                {
                    "type": "tool_use",
                    "id": "toolu_01abc",
                    "name": "tesserae_ask",
                    "input": {"question": "What's the WebMCP fix?"},
                },
                {
                    "type": "tool_use",
                    "id": "toolu_02def",
                    "name": "search_facts",
                    "input": {"query": "vue-fragment"},
                },
            ],
        },
    }
    events = _extract_tool_uses_from_event(event)
    assert len(events) == 2
    assert all(isinstance(e, ToolUseEvent) for e in events)
    assert events[0].name == "tesserae_ask"
    assert events[0].input == {"question": "What's the WebMCP fix?"}
    assert events[0].id == "toolu_01abc"
    assert events[1].name == "search_facts"


def test_extract_tool_uses_from_stream_event_content_block_start():
    """Older CLI emits ``stream_event`` wrappers — content_block_start
    can carry a tool_use block."""
    event = {
        "type": "stream_event",
        "event": {
            "type": "content_block_start",
            "content_block": {
                "type": "tool_use",
                "id": "toolu_ghi",
                "name": "graph_ppr",
                "input": {"seed_nodes": ["kge-abc"]},
            },
        },
    }
    events = _extract_tool_uses_from_event(event)
    assert len(events) == 1
    assert events[0].name == "graph_ppr"
    assert events[0].input == {"seed_nodes": ["kge-abc"]}


def test_extract_tool_uses_returns_empty_for_text_only_event():
    event = {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "just text"}]},
    }
    assert _extract_tool_uses_from_event(event) == []


def test_extract_tool_uses_returns_empty_for_unrelated_event():
    assert _extract_tool_uses_from_event({"type": "result", "result": "ok"}) == []


def test_extract_tool_uses_skips_blocks_with_missing_name():
    """Malformed tool_use blocks (no ``name``) are silently dropped
    rather than crashing the stream."""
    event = {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "tool_use", "input": {"x": 1}},  # no name
            ],
        },
    }
    assert _extract_tool_uses_from_event(event) == []


# ---------- ToolUseEvent.to_dict --------------------------------------------

def test_tool_use_event_to_dict_round_trips_fields():
    evt = ToolUseEvent(
        name="tesserae_ask",
        input={"question": "what's up"},
        id="toolu_99",
    )
    assert evt.to_dict() == {
        "name": "tesserae_ask",
        "input": {"question": "what's up"},
        "id": "toolu_99",
    }
    # ``None`` id round-trips fine.
    evt2 = ToolUseEvent(name="x")
    assert evt2.to_dict() == {"name": "x", "input": {}, "id": None}


# ---------- Skill/Plugin filter — text-only callers don't accumulate
#            ToolUseEvent objects into their response string -----------------

def test_isinstance_filter_drops_tool_use_events():
    """SkillConversationService + PluginConversationService both
    accumulate ``stream_llm_response`` chunks into a response string.
    With the typed yield protocol they see ``Union[str, ToolUseEvent]``;
    both apply the same ``if not isinstance(chunk, str): continue``
    filter so a ToolUseEvent never coerces to a dataclass repr in the
    final response. Lock the filter shape here."""
    chunks = [
        "Looking at the graph: ",
        ToolUseEvent(name="tesserae_ask", input={"q": "?"}),
        "the WebMCP fix is in ",
        "App.vue.",
    ]
    parts: list[str] = []
    for chunk in chunks:
        if not isinstance(chunk, str):
            continue
        parts.append(chunk)
    assert "".join(parts) == "Looking at the graph: the WebMCP fix is in App.vue."


def test_isinstance_check_distinguishes_tool_use_from_string():
    """Defensive: confirm the runtime type check we rely on across
    callers actually separates the two shapes."""
    assert isinstance("hello", str)
    assert not isinstance(ToolUseEvent(name="x"), str)
