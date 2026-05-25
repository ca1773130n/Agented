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


def test_h4_detects_stagnation_in_failed_tool_using_session():
    """A tool-using agent session that FAILED with 5+ consecutive text
    turns IS a stagnation signal — the agent stopped making tool calls
    and "talked to itself" before giving up. Both gates required:
    (1) at least one tool call in the session, (2) outcome in failed
    set."""
    events = (
        [TurnEvent(0, "assistant", tool_name="Read", tool_args={"path": "x"})]
        + [TurnEvent(i, "assistant", content_text="thinking…")
           for i in range(1, 6)]
    )
    incs = detect_h4(events, outcome="failed")
    assert any(i["kind"] == "h4_stagnation" for i in incs)


def test_h4_does_not_flag_stagnation_for_pure_chat_session():
    """Regression from the live-DB dogfood: a super-agent / project-
    session conversation with 0 tool calls is chat-by-design, not
    degeneration. Even if outcome is failed, no stagnation flag —
    counting text turns has no meaning when tools aren't available."""
    events = [TurnEvent(i, "assistant", content_text="thinking…")
              for i in range(10)]
    for outcome in ("failed", "completed", "timeout", "success"):
        incs = detect_h4(events, outcome=outcome)
        stag = [i for i in incs if i["kind"] == "h4_stagnation"]
        assert stag == [], (
            f"chat session with outcome={outcome} should NOT flag "
            f"stagnation; got {stag}"
        )


def test_h4_does_not_flag_stagnation_when_outcome_is_completed():
    """Regression: a tool-using session that COMPLETED successfully
    with verbose text turns isn't a "failure" the operator needs to
    act on. Only stagnation during a failure run is actionable."""
    events = (
        [TurnEvent(0, "assistant", tool_name="Read", tool_args={"path": "x"})]
        + [TurnEvent(i, "assistant", content_text="thinking…")
           for i in range(1, 7)]
    )
    incs = detect_h4(events, outcome="completed")
    assert not any(i["kind"] == "h4_stagnation" for i in incs)


def test_parse_stream_unwraps_json_array_wrapping():
    """Regression from dogfood: ``execution_logs.stdout_log`` is stored
    as a single JSON array wrapping already-Claude-shaped entries —
    ``[{"type": "system", ...}, {"type": "assistant", ...}]`` — instead
    of newline-delimited JSONL. The parser used to reject the leading
    ``[`` and produce 0 events for every trigger execution. The bridge
    (_to_claude_jsonl) unwraps the array."""
    from app.services.harness_failure_annotator import (
        _to_claude_jsonl, parse_claude_stream,
    )
    wrapped = json.dumps([
        {"type": "system", "subtype": "init", "session_id": "x"},
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "hello from claude"},
        ]}},
    ])
    bridged = _to_claude_jsonl(wrapped)
    events = parse_claude_stream(bridged)
    assistant = [e for e in events if e.role == "assistant"]
    assert assistant
    assert any("hello from claude" in e.content_text for e in assistant)


def test_parse_stream_surfaces_setup_failure_from_result_event():
    """Dogfood regression: Two weekly cron triggers had been silently
    no-op-running for weeks because their slash-command wasn't
    registered. Claude exited cleanly (shell status=success) but the
    ``type: result`` event said ``num_turns=0`` with
    ``result: "Unknown command: /vulnerability-scan"``. The parser
    used to drop the result event entirely, so no detector ever fired.
    The fix surfaces num_turns=0 / is_error=true result events as
    synthetic tool_result+error so H3 picks them up."""
    from app.services.harness_failure_annotator import (
        parse_claude_stream, detect_h3,
    )
    # Simulated stream: system init + result with num_turns=0
    stream = "\n".join([
        json.dumps({"type": "system", "subtype": "init"}),
        json.dumps({
            "type": "result", "subtype": "success", "is_error": False,
            "num_turns": 0, "result": "Unknown command: /vulnerability-scan",
        }),
    ])
    events = parse_claude_stream(stream)
    err_events = [e for e in events
                  if e.role == "tool_result" and e.tool_error]
    assert err_events
    assert "Unknown command" in err_events[0].tool_error

    # And H3 flags it as a setup failure.
    incs = detect_h3(events)
    setup = [i for i in incs if i["kind"] == "h3_setup_failure"]
    assert setup
    assert "Unknown command" in setup[0]["evidence"]["error"]


def test_parse_stream_ignores_successful_result_events():
    """The normal path: a result event with num_turns>0 and is_error=false
    is a healthy recap and shouldn't synthesize a fake tool_error."""
    from app.services.harness_failure_annotator import parse_claude_stream
    stream = "\n".join([
        json.dumps({"type": "system", "subtype": "init"}),
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "done"},
        ]}}),
        json.dumps({
            "type": "result", "subtype": "success", "is_error": False,
            "num_turns": 1, "result": "All checks passed.",
        }),
    ])
    events = parse_claude_stream(stream)
    err_events = [e for e in events
                  if e.role == "tool_result" and e.tool_error]
    assert err_events == []


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
        "trigger_execution", "exec-aaaaaa", stream,
        project_id=None, backend_type="claude", outcome="failed",
    )
    assert counts["total"] >= 1
    assert counts["primary_layer"] == "h2"

    summary = repo.get_annotation("trigger_execution", "exec-aaaaaa")
    assert summary is not None
    assert summary["primary_layer"] == "h2"
    assert summary["h2_count"] >= 1
    incs = repo.list_incidents("trigger_execution", "exec-aaaaaa")
    assert all(i["evidence"] for i in incs)


def test_annotate_replaces_prior_incidents(annotation_tables):
    annotate_from_text(
        "trigger_execution", "exec-bbbbbb",
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "answer_action({})"},
        ]}}),
        project_id=None, backend_type="claude", outcome="failed",
    )
    # Re-annotate with a clean trajectory — prior incidents must be cleared.
    annotate_from_text(
        "trigger_execution", "exec-bbbbbb", "",
        project_id=None, backend_type="claude", outcome="success",
    )
    summary = repo.get_annotation("trigger_execution", "exec-bbbbbb")
    assert summary["incident_count"] == 0
    assert summary["primary_layer"] is None
    assert repo.list_incidents("trigger_execution", "exec-bbbbbb") == []


def test_annotate_propagates_project_id_to_summary(annotation_tables):
    """Session-scope pivot: project_id is stored on the annotation roll-up
    so the Activity-lane summary can filter by project."""
    annotate_from_text(
        "super_agent", "sa-zzz",
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "take_action({})"},
        ]}}),
        project_id="proj-xyz", backend_type="claude", outcome="failed",
    )
    summary = repo.get_annotation("super_agent", "sa-zzz")
    assert summary["project_id"] == "proj-xyz"
    counts = repo.summary_counts(project_id="proj-xyz")
    assert counts["h2"] >= 1
    assert counts["total"] >= 1
