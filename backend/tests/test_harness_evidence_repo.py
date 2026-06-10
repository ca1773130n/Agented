"""Repository for the P3 evidence ledger."""

from app.db import harness_evidence
from app.db.connection import get_connection


def _make_session(session_id: str = "sess-1", super_agent_id: str = "sa-1") -> None:
    # FKs are ON: super_agent_sessions.super_agent_id REFERENCES super_agents(id),
    # so the parent must exist first.
    with get_connection() as conn:
        conn.execute("INSERT INTO super_agents (id, name) VALUES (?, ?)", (super_agent_id, "Test SA"))
        conn.execute(
            "INSERT INTO super_agent_sessions (id, super_agent_id) VALUES (?, ?)",
            (session_id, super_agent_id),
        )
        conn.commit()


def test_record_tool_use_assigns_monotonic_seq():
    _make_session()
    s1 = harness_evidence.record_tool_use(
        "sess-1", super_agent_id="sa-1", tool_name="grep", tool_input={"q": "x"}, tool_use_id="t1"
    )
    s2 = harness_evidence.record_tool_use(
        "sess-1", super_agent_id="sa-1", tool_name="read", tool_input={"path": "a"}
    )
    assert s1 == 1
    assert s2 == 2


def test_list_evidence_ordered_with_deserialized_input():
    _make_session()
    harness_evidence.record_tool_use("sess-1", super_agent_id="sa-1", tool_name="grep", tool_input={"q": "x"})
    harness_evidence.record_tool_use("sess-1", super_agent_id="sa-1", tool_name="read", tool_input={"path": "a"})
    rows = harness_evidence.list_evidence("sess-1")
    assert [r["seq"] for r in rows] == [1, 2]
    assert rows[0]["tool_name"] == "grep"
    assert rows[0]["tool_input"] == {"q": "x"}


def test_count_evidence():
    _make_session()
    assert harness_evidence.count_evidence("sess-1") == 0
    harness_evidence.record_tool_use("sess-1", super_agent_id="sa-1", tool_name="grep", tool_input={})
    assert harness_evidence.count_evidence("sess-1") == 1


def test_list_evidence_empty_for_unknown_session():
    assert harness_evidence.list_evidence("nope") == []


def test_fk_cascade_delete_removes_evidence():
    _make_session()
    harness_evidence.record_tool_use("sess-1", super_agent_id="sa-1", tool_name="grep", tool_input={})
    with get_connection() as conn:
        conn.execute("DELETE FROM super_agent_sessions WHERE id = ?", ("sess-1",))
        conn.commit()
    assert harness_evidence.list_evidence("sess-1") == []


def test_unique_session_seq_constraint_rejects_duplicate():
    """The UNIQUE(session_id, seq) backstop forbids two rows sharing an ordinal."""
    import sqlite3

    import pytest

    _make_session()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO harness_evidence (session_id, seq, tool_name) VALUES ('sess-1', 1, 'a')"
        )
        conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO harness_evidence (session_id, seq, tool_name) VALUES ('sess-1', 1, 'b')"
            )
            conn.commit()
