"""End-to-end tests for team-session observation.

Verifies the team-execution path that lets the Life-Harness takeaway
extractor + failure annotator attach to ``session_kind='team_session'``:

  1. ``team_executions`` row gets inserted on register.
  2. Terminal status (completed / failed) updates the row + emits a
     session-complete event.
  3. ``_fetch_team_session`` aggregates component executions' stdout
     into a single SessionPayload.
  4. ``extract_for_session('team_session', ...)`` produces takeaways
     that land in ``session_takeaways`` with the right session_kind /
     session_id / project_id.
"""

from __future__ import annotations

import json

from app.db import harness_takeaways as repo
from app.db.team_executions import (
    backfill_project_id_from_components,
    get_team_execution,
    insert_team_execution,
    resolve_project_id_for_team,
    update_team_execution_status,
)
from app.services import harness_takeaway_extractor as extractor
from app.services.harness_failure_annotator import _fetch_team_session


def _make_assistant_stream(*texts: str) -> str:
    return "\n".join(
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": t},
                    ]
                },
            }
        )
        for t in texts
    )


def _seed_team(team_id: str = "team-obs", *, project_id: str | None = None) -> None:
    """Plant a minimal team row (+ project_teams binding when given)."""
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO teams (id, name, color, enabled, "
            "topology) VALUES (?, 'Obs Team', '#000000', 1, 'sequential')",
            (team_id,),
        )
        if project_id:
            conn.execute(
                "INSERT OR IGNORE INTO projects (id, name) VALUES (?, 'P')",
                (project_id,),
            )
            conn.execute(
                "INSERT OR IGNORE INTO project_teams (project_id, team_id) VALUES (?, ?)",
                (project_id, team_id),
            )
        conn.commit()


def _seed_component_execution(
    execution_id: str,
    stream: str,
    *,
    project_id: str | None = None,
    status: str = "completed",
) -> None:
    """Plant an execution_logs row, optionally bound to a project via
    a project_paths row keyed by a synthetic trigger_id."""
    from app.db.connection import get_connection

    with get_connection() as conn:
        trigger_id = None
        if project_id:
            conn.execute(
                "INSERT OR IGNORE INTO projects (id, name) VALUES (?, 'P')",
                (project_id,),
            )
            trigger_id = f"trg-{execution_id}"
            conn.execute(
                "INSERT OR IGNORE INTO triggers (id, name, prompt_template, "
                "enabled) VALUES (?, 'test', 'do', 1)",
                (trigger_id,),
            )
            conn.execute(
                "INSERT INTO project_paths (project_id, trigger_id, "
                "local_project_path) VALUES (?, ?, '/tmp/p')",
                (project_id, trigger_id),
            )
        conn.execute(
            """INSERT INTO execution_logs
                   (execution_id, trigger_id, trigger_type, started_at,
                    backend_type, status, stdout_log)
               VALUES (?, ?, 'manual', datetime('now'), 'claude', ?, ?)""",
            (execution_id, trigger_id, status, stream),
        )
        conn.commit()


# ---------- DB helpers ------------------------------------------------------


def test_insert_and_get_team_execution(isolated_db):
    _seed_team("team-a")
    insert_team_execution(
        "team-exec-a",
        "team-a",
        "sequential",
        "manual",
        message="hi",
    )
    row = get_team_execution("team-exec-a")
    assert row is not None
    assert row["team_id"] == "team-a"
    assert row["status"] == "running"
    assert row["execution_ids"] == []


def test_resolve_project_id_via_project_teams(isolated_db):
    _seed_team("team-b", project_id="proj-team-b")
    assert resolve_project_id_for_team("team-b") == "proj-team-b"


def test_resolve_project_id_returns_none_when_unbound(isolated_db):
    _seed_team("team-unbound")
    assert resolve_project_id_for_team("team-unbound") is None


def test_update_team_execution_status_records_terminal(isolated_db):
    _seed_team("team-c")
    insert_team_execution("team-exec-c", "team-c", "parallel", "manual")
    update_team_execution_status(
        "team-exec-c",
        "completed",
        execution_ids=["exec-1", "exec-2"],
    )
    row = get_team_execution("team-exec-c")
    assert row["status"] == "completed"
    assert row["execution_ids"] == ["exec-1", "exec-2"]
    assert row["completed_at"] is not None


def test_update_does_not_clobber_existing_project_id(isolated_db):
    _seed_team("team-d", project_id="proj-team-d")
    insert_team_execution(
        "team-exec-d",
        "team-d",
        "sequential",
        "manual",
        project_id="proj-team-d",
    )
    # Try to overwrite with a different project_id — COALESCE keeps original.
    update_team_execution_status(
        "team-exec-d",
        "completed",
        project_id="proj-team-other",
    )
    row = get_team_execution("team-exec-d")
    assert row["project_id"] == "proj-team-d"


def test_backfill_project_id_from_components(isolated_db):
    """Team isn't bound to a project, but a component execution is —
    the backfill copies the component's project_id onto the team row."""
    _seed_team("team-e")
    _seed_component_execution(
        "exec-comp-e",
        _make_assistant_stream("hello"),
        project_id="proj-from-component",
    )
    insert_team_execution("team-exec-e", "team-e", "sequential", "manual")
    update_team_execution_status(
        "team-exec-e",
        "completed",
        execution_ids=["exec-comp-e"],
    )
    resolved = backfill_project_id_from_components("team-exec-e")
    assert resolved == "proj-from-component"
    row = get_team_execution("team-exec-e")
    assert row["project_id"] == "proj-from-component"


# ---------- fetcher ---------------------------------------------------------


def test_fetch_team_session_aggregates_component_streams(isolated_db):
    _seed_team("team-f", project_id="proj-team-f")
    _seed_component_execution(
        "exec-f-1",
        _make_assistant_stream("First agent's takeaway content."),
        project_id="proj-team-f",
    )
    _seed_component_execution(
        "exec-f-2",
        _make_assistant_stream("Second agent's takeaway content."),
        project_id="proj-team-f",
    )
    insert_team_execution(
        "team-exec-f",
        "team-f",
        "sequential",
        "manual",
        project_id="proj-team-f",
    )
    update_team_execution_status(
        "team-exec-f",
        "completed",
        execution_ids=["exec-f-1", "exec-f-2"],
    )
    payload = _fetch_team_session("team-exec-f")
    assert payload is not None
    assert payload.project_id == "proj-team-f"
    assert payload.outcome == "completed"
    assert "First agent's takeaway content." in payload.text
    assert "Second agent's takeaway content." in payload.text


def test_fetch_team_session_returns_none_for_missing_row(isolated_db):
    assert _fetch_team_session("team-exec-missing") is None


def test_fetch_team_session_empty_when_no_components(isolated_db):
    """Row exists but no components ran — payload has empty text, not None."""
    _seed_team("team-g")
    insert_team_execution("team-exec-g", "team-g", "sequential", "manual")
    payload = _fetch_team_session("team-exec-g")
    assert payload is not None
    assert payload.text == ""


# ---------- end-to-end extraction ------------------------------------------


def test_extract_for_session_produces_team_session_takeaways(isolated_db):
    """The full happy path: seed a finished team execution whose
    component stream contains a 'remember' phrase → extract_for_session
    creates takeaways tagged with session_kind='team_session' and the
    team's project_id."""
    _seed_team("team-h", project_id="proj-team-h")
    _seed_component_execution(
        "exec-h-1",
        _make_assistant_stream(
            "Got it, I'll remember that you prefer pytest over unittest for all new test files.",
        ),
        project_id="proj-team-h",
    )
    insert_team_execution(
        "team-exec-h",
        "team-h",
        "sequential",
        "manual",
        project_id="proj-team-h",
    )
    update_team_execution_status(
        "team-exec-h",
        "completed",
        execution_ids=["exec-h-1"],
    )

    ids = extractor.extract_for_session(
        "team_session",
        "team-exec-h",
        project_id="proj-team-h",
    )
    assert ids, "expected at least one takeaway from the team session"
    rows = [repo.get(i) for i in ids]
    # Every row carries the team_session kind + the right session id.
    assert all(r["session_kind"] == "team_session" for r in rows)
    assert all(r["session_id"] == "team-exec-h" for r in rows)
    assert all(r["project_id"] == "proj-team-h" for r in rows)
    # The 'remember pytest' phrase should land as a user_preference.
    prefs = [r for r in rows if r["kind"] == "user_preference"]
    assert prefs
    assert any("pytest" in r["content"] for r in prefs)


def test_role_content_array_converted_to_claude_jsonl(isolated_db):
    """Dogfood regression: ``super_agent_sessions.conversation_log`` is
    stored as ``json.dumps([{"role": ..., "content": ...}, ...])``, NOT
    the Claude JSONL stream format the parser expects. Before the
    fetcher converted it, ``parse_claude_stream`` returned 0 events and
    the extractor produced 0 takeaways from real super-agent sessions."""
    from app.db.connection import get_connection
    from app.services.harness_failure_annotator import (
        _fetch_super_agent_session,
        parse_claude_stream,
    )

    role_content_log = json.dumps(
        [
            {"role": "user", "content": "what's the deploy procedure?"},
            {
                "role": "assistant",
                "content": (
                    "Got it, I'll remember that you prefer deploying via `just deploy` over `make`."
                ),
            },
        ]
    )
    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO super_agents (id, name) VALUES ('sa-conv-fmt', 'SA')")
        conn.execute(
            "INSERT INTO super_agent_sessions (id, super_agent_id, status, "
            "conversation_log) VALUES (?, 'sa-conv-fmt', 'completed', ?)",
            ("sess-conv-format", role_content_log),
        )
        conn.commit()

    payload = _fetch_super_agent_session("sess-conv-format")
    assert payload is not None
    events = parse_claude_stream(payload.text)
    # The parser registers assistant text blocks and tool_result user
    # blocks — plain user text is intentionally skipped. So we expect
    # ≥1 assistant event with the preserved content.
    assistant_events = [e for e in events if e.role == "assistant"]
    assert assistant_events
    assert any("just deploy" in e.content_text for e in assistant_events)


def test_extract_team_session_missing_row_is_noop(isolated_db):
    """extract_for_session on a missing team_session id is a clean no-op
    (the fetcher returns None and the extractor records nothing)."""
    ids = extractor.extract_for_session(
        "team_session",
        "team-exec-ghost",
        project_id="proj-x",
    )
    assert ids == []
