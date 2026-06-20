"""S5 — _build_harness_session normalizes all five session kinds.

REQ-26 consistency gap: project_session / workflow / team_session used to
fall through to None in _build_harness_session, collapsing tesserae signal
coverage to 2/5. Each kind must now return a non-None HarnessSession dict.
"""

import json
from pathlib import Path

import pytest

from app.db.connection import get_connection
from app.services.tesserae_integration import _build_harness_session


def _seed(sql: str, params: tuple) -> None:
    with get_connection() as conn:
        conn.execute(sql, params)
        conn.commit()


def _call(kind: str, sid: str, tmp_path: Path) -> dict:
    return _build_harness_session(
        session_kind=kind,
        session_id=sid,
        project_id="proj-aaaaaa",
        project_name="Demo",
        project_root=tmp_path,
        decisions=["decided-x"],
    )


def test_super_agent_session_normalizes(tmp_path):
    _seed(
        "INSERT INTO super_agents (id, name, backend_type) VALUES (?,?,?)",
        ("sa-111111", "Agent", "claude"),
    )
    _seed(
        "INSERT INTO super_agent_sessions (id, super_agent_id, conversation_log) VALUES (?,?,?)",
        ("sas-111111", "sa-111111", json.dumps([{"role": "user", "content": "hi"}])),
    )
    rec = _call("super_agent", "sas-111111", tmp_path)
    assert rec is not None
    assert rec["metadata"]["session_kind"] == "super_agent"
    assert rec["decisions"] == ["decided-x"]


def test_trigger_execution_normalizes(tmp_path):
    _seed(
        "INSERT INTO execution_logs (execution_id, trigger_type, started_at, "
        "backend_type, status) VALUES (?,?,?,?,?)",
        ("exec-111111", "manual", "2026-01-01T00:00:00Z", "claude", "completed"),
    )
    rec = _call("trigger_execution", "exec-111111", tmp_path)
    assert rec is not None
    assert rec["metadata"]["session_kind"] == "trigger_execution"


def test_project_session_normalizes(tmp_path):
    _seed(
        "INSERT INTO projects (id, name) VALUES (?,?)",
        ("proj-aaaaaa", "Demo"),
    )
    _seed(
        "INSERT INTO project_sessions (id, project_id, status, summary, log_json) "
        "VALUES (?,?,?,?,?)",
        (
            "ps-111111",
            "proj-aaaaaa",
            "completed",
            "did the thing",
            json.dumps([{"role": "assistant", "content": "work"}]),
        ),
    )
    rec = _call("project_session", "ps-111111", tmp_path)
    assert rec is not None
    assert rec["metadata"]["session_kind"] == "project_session"
    assert rec["title"] == "ps-111111"
    assert rec["summary"] == "did the thing"
    assert rec["message_count"] == 1


def test_workflow_normalizes(tmp_path):
    _seed(
        "INSERT INTO workflows (id, name) VALUES (?,?)",
        ("wf-111111", "WF"),
    )
    _seed(
        "INSERT INTO workflow_executions (id, workflow_id, version, status) VALUES (?,?,?,?)",
        ("wfx-111111", "wf-111111", 1, "completed"),
    )
    _seed(
        "INSERT INTO workflow_node_executions (execution_id, node_id, node_type, "
        "status, output_json) VALUES (?,?,?,?,?)",
        ("wfx-111111", "n1", "task", "completed", "node output text"),
    )
    rec = _call("workflow", "wfx-111111", tmp_path)
    assert rec is not None
    assert rec["metadata"]["session_kind"] == "workflow"
    assert rec["title"] == "wfx-111111"
    assert "node output text" in rec["redacted_preview"]


def test_team_session_normalizes(tmp_path):
    _seed(
        "INSERT INTO teams (id, name, topology) VALUES (?,?,?)",
        ("team-111111", "Squad", "pipeline"),
    )
    _seed(
        "INSERT INTO execution_logs (execution_id, trigger_type, started_at, "
        "backend_type, status, stdout_log) VALUES (?,?,?,?,?,?)",
        (
            "exec-team01",
            "manual",
            "2026-01-01T00:00:00Z",
            "claude",
            "completed",
            "component stdout",
        ),
    )
    _seed(
        "INSERT INTO team_executions (id, team_id, topology, status, message, "
        "execution_ids) VALUES (?,?,?,?,?,?)",
        (
            "tex-111111",
            "team-111111",
            "pipeline",
            "completed",
            "team msg",
            json.dumps(["exec-team01"]),
        ),
    )
    rec = _call("team_session", "tex-111111", tmp_path)
    assert rec is not None
    assert rec["metadata"]["session_kind"] == "team_session"
    assert rec["title"] == "tex-111111"
    assert "component stdout" in rec["redacted_preview"]


def test_unknown_kind_returns_none(tmp_path):
    assert _call("bogus_kind", "x", tmp_path) is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
