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
    assert ev["severity"] in ("low", "medium", "high", "critical")


def test_invalid_tool_call_scored_high():
    out = _apply_priority_protocol(
        [_tool_result(0, "unknown argument: foo")], outcome="failed",
    )
    ev = out[0]["evidence"]
    assert ev["confidence"] >= 0.9
    assert ev["severity"] == "high"
