"""Tests for the defensive AskUserQuestion JSON-in-text lifter.

When claude doesn't have AskUserQuestion as a structured tool (or
hallucinates the call as a JSON payload inside a text block), the
operator sees raw JSON instead of clickable options. PSM's
``_extract_text_ask_question`` and the call site in
``_extract_stream_json_events`` lift that JSON into the same
``ask_user_question`` SSE event the structured ``tool_use`` path
emits, so InteractiveQuestionCard renders buttons either way.

v0.7.72.
"""

from __future__ import annotations

import json

from app.services.project_session_manager import (
    _extract_stream_json_events,
    _extract_text_ask_question,
    _looks_like_ask_user_question,
    _scan_balanced_object,
)

CANONICAL_QUESTIONS = [
    {
        "question": "Which backtick should I remove?",
        "header": "Backtick",
        "multiSelect": False,
        "options": [
            {"label": "None — display artifact", "description": "no edit"},
            {"label": "First in-file backtick", "description": "line 44"},
            {"label": "All backticks in file", "description": "strip all"},
        ],
    }
]


# -----------------------------------------------------------------
# Pure helpers
# -----------------------------------------------------------------


def test_looks_like_ask_user_question_accepts_canonical_shape():
    payload = {"questions": CANONICAL_QUESTIONS}
    assert _looks_like_ask_user_question(payload) is True


def test_looks_like_rejects_missing_options():
    payload = {"questions": [{"question": "q?"}]}
    assert _looks_like_ask_user_question(payload) is False


def test_looks_like_rejects_non_string_question():
    payload = {"questions": [{"question": 123, "options": [{"label": "a"}]}]}
    assert _looks_like_ask_user_question(payload) is False


def test_looks_like_rejects_empty_questions():
    assert _looks_like_ask_user_question({"questions": []}) is False


def test_scan_balanced_object_returns_full_object_bounds():
    text = 'noise {"questions": [{"a": [1, 2]}, {"b": {"c": 1}}]} trailing'
    bounds = _scan_balanced_object(text, text.index('"questions"'))
    assert bounds is not None
    start, end = bounds
    assert text[start] == "{"
    assert text[end - 1] == "}"
    # Round-trip through json.loads to confirm we caught a whole object.
    assert json.loads(text[start:end]) == {"questions": [{"a": [1, 2]}, {"b": {"c": 1}}]}


def test_scan_balanced_object_handles_braces_in_strings():
    text = '{"questions": [{"label": "weird {} brace"}]}'
    bounds = _scan_balanced_object(text, text.index('"questions"'))
    assert bounds is not None
    start, end = bounds
    assert json.loads(text[start:end])["questions"][0]["label"] == "weird {} brace"


# -----------------------------------------------------------------
# _extract_text_ask_question
# -----------------------------------------------------------------


def test_lift_from_fenced_json_block():
    blob = json.dumps({"questions": CANONICAL_QUESTIONS}, indent=2)
    text = f"Here's what I want to ask:\n\n```json\n{blob}\n```\n\nPlease pick."
    stripped, payload = _extract_text_ask_question(text)
    assert payload is not None
    assert payload["tool_use_id"] == ""
    assert payload["questions"][0]["header"] == "Backtick"
    assert "```json" not in stripped
    assert "Here's what I want to ask:" in stripped
    assert "Please pick." in stripped


def test_lift_from_inline_unfenced_json():
    blob = json.dumps({"questions": CANONICAL_QUESTIONS})
    text = f"preamble {blob} trailing words"
    stripped, payload = _extract_text_ask_question(text)
    assert payload is not None
    assert payload["questions"][0]["options"][2]["label"] == "All backticks in file"
    assert "questions" not in stripped
    assert "preamble" in stripped
    assert "trailing words" in stripped


def test_lift_supports_multi_question_payload():
    payload_in = {
        "questions": [
            {"question": "q1", "options": [{"label": "a"}, {"label": "b"}]},
            {
                "question": "q2",
                "header": "h2",
                "multiSelect": True,
                "options": [{"label": "x"}, {"label": "y"}],
            },
        ]
    }
    text = json.dumps(payload_in)
    _, lifted = _extract_text_ask_question(text)
    assert lifted is not None
    assert len(lifted["questions"]) == 2
    assert lifted["questions"][1]["multiSelect"] is True


def test_no_lift_when_no_askq_shape():
    text = 'random JSON {"foo": "bar"} and {"questions": "not an array"}'
    stripped, payload = _extract_text_ask_question(text)
    assert payload is None
    assert stripped == text


def test_no_lift_for_plain_prose():
    text = "Just a normal claude reply with no JSON to speak of."
    stripped, payload = _extract_text_ask_question(text)
    assert payload is None
    assert stripped == text


# -----------------------------------------------------------------
# End-to-end through _extract_stream_json_events
# -----------------------------------------------------------------


def test_stream_event_emits_synthetic_ask_user_question():
    payload = {"questions": CANONICAL_QUESTIONS}
    text_block_text = (
        "Looking at this. Here's the picker:\n\n"
        "```json\n" + json.dumps(payload, indent=2) + "\n```\n\nPick one."
    )
    line = json.dumps(
        {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": text_block_text}]},
        }
    )
    events = _extract_stream_json_events(line, None)
    kinds = [e[0] for e in events]
    assert "ask_user_question" in kinds
    auq = next(e for e in events if e[0] == "ask_user_question")
    assert auq[1]["tool_use_id"] == ""
    assert auq[1]["questions"][0]["question"].startswith("Which backtick")
    # Surrounding prose still surfaces as an ``output`` event so the
    # operator sees the lead-in, just without the duplicated JSON.
    output_events = [e for e in events if e[0] == "output"]
    assert any("Looking at this" in e[1]["line"] for e in output_events)


def test_stream_event_preserves_structured_tool_use_path():
    # The pre-existing structured ``tool_use`` path must keep working
    # alongside the new text-lift. Verify a real tool_use still emits
    # an ask_user_question event with the real tool_use_id.
    line = json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_abc",
                        "name": "AskUserQuestion",
                        "input": {"questions": CANONICAL_QUESTIONS},
                    }
                ]
            },
        }
    )
    events = _extract_stream_json_events(line, None)
    auq = next(e for e in events if e[0] == "ask_user_question")
    assert auq[1]["tool_use_id"] == "toolu_abc"
    assert auq[1]["questions"][0]["header"] == "Backtick"
