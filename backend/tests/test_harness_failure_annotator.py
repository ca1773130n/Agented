"""Tests for the Life-Harness failure annotator (T1)."""

from __future__ import annotations

import json

import pytest

from app.db import harness_annotations as repo
from app.services.harness_failure_annotator import (
    TurnEvent,
    _apply_priority_protocol,
    annotate_from_text,
    detect_h2,
    detect_h3,
    detect_h4,
    parse_claude_stream,
)


# init_db() in the ``isolated_db`` fixture already runs create_fresh_schema,
# which now includes ``create_harness_annotation_tables``. So no extra setup
# is needed — alias the fixture under the descriptive name used by tests.
@pytest.fixture
def annotation_tables(isolated_db):
    return isolated_db


# ---------- detectors -------------------------------------------------------

def test_h2_detects_action_in_content():
    events = [
        TurnEvent(0, "assistant", content_text="I will take_action({foo: 1}) now."),
    ]
    incs = detect_h2(events)
    assert len(incs) == 1
    assert incs[0]["kind"] == "h2_tool_in_content"
    assert incs[0]["layer"] == "h2"


def test_h2_detects_invalid_tool_call():
    events = [
        TurnEvent(0, "tool_result", tool_error="Missing required parameter: 'path'"),
    ]
    assert detect_h2(events)[0]["kind"] == "h2_invalid_tool_call"


def test_h3_detects_unknown_parameter():
    events = [
        TurnEvent(0, "tool_result", tool_error="Unknown parameter 'flavour'"),
    ]
    assert detect_h3(events)[0]["kind"] == "h3_contract_violation"


def test_h4_detects_repeated_action():
    args = {"path": "/tmp/x"}
    events = [TurnEvent(i, "assistant", tool_name="read", tool_args=args)
              for i in range(3)]
    incs = detect_h4(events, outcome="success")
    assert any(i["kind"] == "h4_repeat_action" for i in incs)


def test_h4_detects_stagnation_streak():
    events = [TurnEvent(i, "assistant", content_text="thinking…") for i in range(5)]
    incs = detect_h4(events, outcome="success")
    assert any(i["kind"] == "h4_stagnation" for i in incs)


def test_h4_flags_timeout_budget():
    incs = detect_h4([], outcome="timeout")
    assert incs and incs[0]["kind"] == "h4_budget_exhausted"


# ---------- priority protocol ----------------------------------------------

def test_priority_h2_claims_turn_over_h3():
    """If H2 fires on a turn, H3 must not double-count the same turn."""
    events = [
        # H2 textual cue *and* an H3-shaped tool error on the same turn index.
        TurnEvent(0, "assistant", content_text="answer_action({x:1})"),
        TurnEvent(0, "tool_result", tool_error="Unknown parameter 'x'"),
    ]
    out = _apply_priority_protocol(events, outcome="failed")
    h2 = [i for i in out if i["layer"] == "h2"]
    h3 = [i for i in out if i["layer"] == "h3"]
    assert h2 and not h3, out


def test_general_only_when_failed_and_nothing_else():
    out = _apply_priority_protocol([], outcome="failed")
    assert len(out) == 1 and out[0]["layer"] == "general"

    assert _apply_priority_protocol([], outcome="success") == []


# ---------- claude jsonl parser --------------------------------------------

def test_parse_claude_stream_extracts_tool_use_and_results():
    stream = "\n".join([
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "ok"},
            {"type": "tool_use", "name": "Bash", "input": {"cmd": "ls"}},
        ]}}),
        json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "is_error": True, "content": "permission denied"},
        ]}}),
        "not-json garbage line",
    ])
    events = parse_claude_stream(stream)
    kinds = [(e.role, e.tool_name, e.tool_error) for e in events]
    assert ("assistant", "Bash", None) in kinds
    assert any(role == "tool_result" and err == "permission denied"
               for role, _, err in kinds)


def test_parse_claude_stream_tolerates_empty_and_malformed():
    assert parse_claude_stream("") == []
    assert parse_claude_stream("hi\n{not-json}\n") == []


# ---------- end-to-end persistence -----------------------------------------

def test_annotate_from_text_writes_rollup(annotation_tables):
    stream = json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "I'll take_action({a:1})"},
    ]}})
    counts = annotate_from_text(
        "exec-aaaaaa", stream, backend_type="claude", outcome="failed",
    )
    assert counts["total"] >= 1
    assert counts["primary_layer"] == "h2"

    summary = repo.get_annotation("exec-aaaaaa")
    assert summary is not None
    assert summary["primary_layer"] == "h2"
    assert summary["h2_count"] >= 1
    incs = repo.list_incidents("exec-aaaaaa")
    assert all(i["evidence"] for i in incs)


def test_annotate_replaces_prior_incidents(annotation_tables):
    annotate_from_text(
        "exec-bbbbbb",
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "answer_action({})"},
        ]}}),
        backend_type="claude", outcome="failed",
    )
    # Re-annotate with a clean trajectory — prior incidents must be cleared.
    annotate_from_text(
        "exec-bbbbbb", "", backend_type="claude", outcome="success",
    )
    summary = repo.get_annotation("exec-bbbbbb")
    assert summary["incident_count"] == 0
    assert summary["primary_layer"] is None
    assert repo.list_incidents("exec-bbbbbb") == []
