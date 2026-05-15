"""Smoke tests for the wave 74 GRD routes."""

from litestar.testing import create_test_client

from app_litestar.auth import provide_caller
from app_litestar.routes.grd_routes import grd_router


def _client():
    return create_test_client(
        route_handlers=[grd_router],
        dependencies={"caller": provide_caller},
    )


def test_unknown_project_sync_status_404(isolated_db):
    with _client() as c:
        resp = c.get("/api/projects/missing/sync")
    assert resp.status_code == 404


def test_unknown_project_trigger_sync_404(isolated_db):
    with _client() as c:
        resp = c.post("/api/projects/missing/sync", json={})
    assert resp.status_code == 404


def test_list_milestones_unknown_project_404(isolated_db):
    with _client() as c:
        resp = c.get("/api/projects/missing/milestones")
    assert resp.status_code == 404


def test_list_phases_unknown_project_404(isolated_db):
    with _client() as c:
        resp = c.get("/api/projects/missing/phases")
    assert resp.status_code == 404


def test_create_phase_requires_milestone_and_name(isolated_db):
    with _client() as c:
        resp = c.post("/api/projects/missing/phases", json={})
    # project missing first → 404
    assert resp.status_code == 404


def test_list_plans_unknown_project_404(isolated_db):
    with _client() as c:
        resp = c.get("/api/projects/missing/plans")
    assert resp.status_code == 404


def test_update_plan_status_unknown_project_404(isolated_db):
    with _client() as c:
        resp = c.put(
            "/api/projects/missing/plans/p-x/status",
            json={"status": "completed"},
        )
    assert resp.status_code == 404


def test_create_plan_unknown_project_404(isolated_db):
    with _client() as c:
        resp = c.post(
            "/api/projects/missing/plans",
            json={"phase_id": "ph-x", "title": "x"},
        )
    assert resp.status_code == 404


def test_update_plan_unknown_project_404(isolated_db):
    with _client() as c:
        resp = c.put("/api/projects/missing/plans/p-x", json={"title": "x"})
    assert resp.status_code == 404


def test_delete_plan_unknown_project_404(isolated_db):
    with _client() as c:
        resp = c.delete("/api/projects/missing/plans/p-x")
    assert resp.status_code == 404


def test_project_chat_requires_content(isolated_db):
    with _client() as c:
        resp = c.post("/api/projects/missing/chat", json={})
    assert resp.status_code == 400


def test_invoke_planning_requires_command(isolated_db):
    with _client() as c:
        resp = c.post("/api/projects/missing/planning/invoke", json={})
    assert resp.status_code == 400


def test_planning_status_unknown_project_404(isolated_db):
    with _client() as c:
        resp = c.get("/api/projects/missing/planning/status")
    assert resp.status_code == 404


def test_create_session_unknown_project_404(isolated_db):
    with _client() as c:
        resp = c.post(
            "/api/projects/missing/sessions",
            json={"cmd": ["echo", "hi"]},
        )
    assert resp.status_code == 404


def test_list_sessions_unknown_project_404(isolated_db):
    with _client() as c:
        resp = c.get("/api/projects/missing/sessions")
    assert resp.status_code == 404


def test_stop_unknown_session_404(isolated_db):
    with _client() as c:
        resp = c.post("/api/projects/p-x/sessions/missing/stop", json={})
    assert resp.status_code == 404


def test_pause_unknown_session_404(isolated_db):
    with _client() as c:
        resp = c.post("/api/projects/p-x/sessions/missing/pause", json={})
    assert resp.status_code == 404


def test_resume_unknown_session_404(isolated_db):
    with _client() as c:
        resp = c.post("/api/projects/p-x/sessions/missing/resume", json={})
    assert resp.status_code == 404


def test_session_input_requires_text(isolated_db):
    with _client() as c:
        resp = c.post(
            "/api/projects/p-x/sessions/sess-x/input", json={}
        )
    assert resp.status_code == 400


def test_session_input_stream_json_wraps_envelope(isolated_db, monkeypatch):
    """v0.7.46 — when the session is in stream-json mode, the input
    route must wrap the user's text in the Agent SDK V1 envelope
    (``type/session_id/message/parent_tool_use_id``). Missing fields
    caused claude to silently fail to parse the user event."""
    import json as _json

    from app.services.project_session_manager import ProjectSessionManager

    captured: dict[str, str] = {}

    def fake_send_input(session_id: str, payload: str) -> bool:
        captured["session_id"] = session_id
        captured["payload"] = payload
        return True

    monkeypatch.setattr(
        ProjectSessionManager, "is_stream_json", classmethod(lambda cls, sid: True)
    )
    monkeypatch.setattr(
        ProjectSessionManager,
        "send_input",
        classmethod(lambda cls, sid, payload: fake_send_input(sid, payload)),
    )

    with _client() as c:
        resp = c.post(
            "/api/projects/p-x/sessions/psess-abc/input",
            json={"text": "안녕 claude"},
        )

    assert resp.status_code == 201, resp.text
    assert captured["session_id"] == "psess-abc"
    envelope = _json.loads(captured["payload"])
    assert envelope == {
        "type": "user",
        "session_id": "",
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": "안녕 claude"}],
        },
        "parent_tool_use_id": None,
    }


def test_session_input_pty_mode_strips_non_ascii(isolated_db, monkeypatch):
    """The original PTY interactive REPL path must keep its ASCII-only
    sanitization (defense against rogue control chars rewriting the
    user's terminal). Pin that the stream-json branch is NOT taken when
    the session is in PTY mode."""
    from app.services.project_session_manager import ProjectSessionManager

    captured: dict[str, str] = {}

    monkeypatch.setattr(
        ProjectSessionManager, "is_stream_json", classmethod(lambda cls, sid: False)
    )

    def fake_send_input(cls, sid: str, payload: str) -> bool:
        captured["payload"] = payload
        return True

    monkeypatch.setattr(
        ProjectSessionManager, "send_input", classmethod(fake_send_input)
    )

    with _client() as c:
        # Korean + emoji + a printable ASCII tail. PTY mode strips
        # everything outside the [32, 127) range, leaving just the
        # ASCII portion.
        resp = c.post(
            "/api/projects/p-x/sessions/psess-pty/input",
            json={"text": "안녕\thello"},
        )

    assert resp.status_code == 201
    # Tab + ASCII letters survive; Korean does not.
    assert captured["payload"] == "\thello"


def test_create_session_persists_dialog_fields(isolated_db, monkeypatch):
    """v0.7.57 — the new session-start dialog sends name + auto_title
    + yolo_mode. Pin that they're stored on the row and that yolo_mode
    appends ``--dangerously-skip-permissions`` to the cmd."""
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, local_path, created_at, updated_at) "
            "VALUES ('proj-dlg', 'dialog-test', '/tmp', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        conn.commit()

    captured_cmd: dict[str, list] = {}

    def fake_handler_start(self, config: dict) -> dict:  # noqa: ARG001
        captured_cmd["cmd"] = config["cmd"]
        captured_cmd["yolo"] = config.get("yolo_mode")
        return {"session_id": "psess-dlg01", "pid": 1234, "status": "active"}

    # Seed a session row that the route handler will UPDATE after start.
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO project_sessions (id, project_id, status) "
            "VALUES ('psess-dlg01', 'proj-dlg', 'active')"
        )
        conn.commit()

    from app.services.execution_type_handler import DirectExecutionHandler

    monkeypatch.setattr(DirectExecutionHandler, "start", fake_handler_start)

    with _client() as c:
        resp = c.post(
            "/api/projects/proj-dlg/sessions",
            json={
                "cmd": ["claude", "--print", "--input-format", "stream-json",
                        "--output-format", "stream-json", "--verbose"],
                "execution_type": "direct",
                "execution_mode": "interactive",
                "stream_json": True,
                "use_pty": False,
                "name": "Refactor auth",
                "auto_title": False,
                "yolo_mode": True,
            },
        )
    assert resp.status_code == 201, resp.text

    # yolo appended dangerously-skip-permissions
    assert "--dangerously-skip-permissions" in captured_cmd["cmd"]
    assert captured_cmd["yolo"] is True

    # Row got name + flags stamped
    with get_connection() as conn:
        row = conn.execute(
            "SELECT name, auto_title, yolo_mode FROM project_sessions WHERE id = 'psess-dlg01'"
        ).fetchone()
    assert row["name"] == "Refactor auth"
    assert row["auto_title"] == 0
    assert row["yolo_mode"] == 1


def test_create_session_auto_title_blanks_name(isolated_db, monkeypatch):
    """When auto_title is on, the row's ``name`` stays NULL so the
    backend (eventually claude-summary) can fill it later."""
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, local_path, created_at, updated_at) "
            "VALUES ('proj-auto', 'auto-test', '/tmp', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        conn.execute(
            "INSERT INTO project_sessions (id, project_id, status) "
            "VALUES ('psess-auto', 'proj-auto', 'active')"
        )
        # v0.7.58 — non-yolo sessions need a whitelisted account.
        conn.execute(
            "INSERT INTO project_allowed_accounts (project_id, account_id) "
            "VALUES ('proj-auto', 'bkd-auto')"
        )
        conn.commit()

    from app.services.execution_type_handler import DirectExecutionHandler

    monkeypatch.setattr(
        DirectExecutionHandler,
        "start",
        lambda self, cfg: {"session_id": "psess-auto", "pid": 1234, "status": "active"},
    )

    with _client() as c:
        resp = c.post(
            "/api/projects/proj-auto/sessions",
            json={
                "cmd": ["claude"],
                "execution_type": "direct",
                "auto_title": True,
                "yolo_mode": False,
                "account_id": "bkd-auto",  # v0.7.58 — must be whitelisted
                # name passed but should be ignored (auto_title wins)
                "name": "",
            },
        )
    assert resp.status_code == 201

    with get_connection() as conn:
        row = conn.execute(
            "SELECT name, auto_title, yolo_mode FROM project_sessions WHERE id = 'psess-auto'"
        ).fetchone()
    assert row["name"] is None
    assert row["auto_title"] == 1
    assert row["yolo_mode"] == 0


def test_create_ralph_session_unknown_project_404(isolated_db):
    with _client() as c:
        resp = c.post("/api/projects/missing/sessions/ralph", json={})
    assert resp.status_code == 404


def test_create_team_session_unknown_project_404(isolated_db):
    with _client() as c:
        resp = c.post("/api/projects/missing/sessions/team", json={})
    assert resp.status_code == 404


def test_session_output(isolated_db):
    with _client() as c:
        resp = c.get("/api/projects/p-x/sessions/missing/output")
    assert resp.status_code == 200


def test_monitor_unknown_session_404(isolated_db):
    with _client() as c:
        resp = c.get("/api/projects/p-x/sessions/missing/monitor")
    assert resp.status_code == 404
