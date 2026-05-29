"""Detector enrichment: confidence + severity, wider H2/H3/H4 coverage."""

from __future__ import annotations

from app.services.harness_failure_annotator import (
    TurnEvent,
    _apply_priority_protocol,
)


def _tool_result(idx: int, error: str) -> TurnEvent:
    return TurnEvent(index=idx, role="tool_result", tool_error=error)


def test_incidents_carry_confidence_and_severity():
    events = [_tool_result(0, "missing required argument: path")]
    out = _apply_priority_protocol(events, outcome="failed")
    assert out, "expected an h2_invalid_tool_call incident"
    ev = out[0]["evidence"]
    assert 0.0 <= ev["confidence"] <= 1.0
    assert ev["severity"] in ("low", "medium", "high")


def test_invalid_tool_call_scored_high():
    out = _apply_priority_protocol(
        [_tool_result(0, "unknown argument: foo")],
        outcome="failed",
    )
    ev = out[0]["evidence"]
    assert ev["confidence"] >= 0.9
    assert ev["severity"] == "high"


def test_h3_missing_file_detected():
    out = _apply_priority_protocol(
        [_tool_result(0, "ENOENT: no such file or directory, open '/tmp/x'")],
        outcome="failed",
    )
    kinds = {i["kind"] for i in out}
    assert "h3_missing_file" in kinds


def test_h3_permission_denied_detected():
    out = _apply_priority_protocol(
        [_tool_result(0, "EACCES: permission denied, open '/etc/shadow'")],
        outcome="failed",
    )
    kinds = {i["kind"] for i in out}
    assert "h3_permission_denied" in kinds


def _assistant(idx: int, text: str = "", tool: str | None = None) -> TurnEvent:
    return TurnEvent(index=idx, role="assistant", content_text=text, tool_name=tool)


def test_h2_repeated_tool_failure_detected():
    events = [
        _tool_result(0, "bash: boom: command failed"),
        _tool_result(1, "bash: boom: command failed"),
    ]
    out = _apply_priority_protocol(events, outcome="failed")
    assert "h2_repeated_tool_failure" in {i["kind"] for i in out}


def test_h4_abandoned_goal_detected():
    events = [
        _assistant(0, "I can't continue, giving up on this task."),
    ]
    out = _apply_priority_protocol(events, outcome="failed")
    assert "h4_abandoned_goal" in {i["kind"] for i in out}


def test_score_incident_preserves_existing_confidence():
    from app.services.harness_failure_annotator import _score_incident

    inc = {
        "layer": "h2",
        "kind": "h2_invalid_tool_call",
        "event_index": 0,
        "evidence": {"confidence": 0.123, "severity": "critical"},
    }
    out = _score_incident(inc)
    assert out["evidence"]["confidence"] == 0.123
    assert out["evidence"]["severity"] == "critical"


def test_h3_plain_path_without_error_keyword_not_flagged():
    out = _apply_priority_protocol(
        [_tool_result(0, "opened /tmp/x successfully")], outcome="failed"
    )
    kinds = {i["kind"] for i in out}
    assert "h3_missing_file" not in kinds
    assert "h3_permission_denied" not in kinds


def test_h4_no_abandon_phrase_not_flagged():
    out = _apply_priority_protocol(
        [_assistant(0, "Working on the task, making progress.")], outcome="failed"
    )
    assert "h4_abandoned_goal" not in {i["kind"] for i in out}
