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
