"""The P3 tap records ToolUseEvents and never breaks streaming."""

from unittest.mock import patch

from app.db import harness_evidence
from app.db.connection import get_connection
from app.services.conversation_streaming import ToolUseEvent
from app.services.streaming_helper import _record_tool_use_evidence


def _make_session(session_id="sess-1", super_agent_id="sa-1"):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO super_agents (id, name) VALUES (?, ?)", (super_agent_id, "Test SA")
        )
        conn.execute(
            "INSERT INTO super_agent_sessions (id, super_agent_id) VALUES (?, ?)",
            (session_id, super_agent_id),
        )
        conn.commit()


def test_tap_records_tool_use_event():
    _make_session()
    evt = ToolUseEvent(name="grep", input={"q": "x"}, id="t1")
    _record_tool_use_evidence("sess-1", "sa-1", evt)
    rows = harness_evidence.list_evidence("sess-1")
    assert len(rows) == 1
    assert rows[0]["tool_name"] == "grep"
    assert rows[0]["tool_input"] == {"q": "x"}
    assert rows[0]["tool_use_id"] == "t1"


def test_tap_swallows_errors_and_never_raises():
    evt = ToolUseEvent(name="grep", input={"q": "x"}, id="t1")
    with patch(
        "app.services.streaming_helper.harness_evidence.record_tool_use",
        side_effect=RuntimeError("db down"),
    ):
        # Must not raise — streaming must never be disrupted by a ledger write.
        _record_tool_use_evidence("sess-1", "sa-1", evt)
