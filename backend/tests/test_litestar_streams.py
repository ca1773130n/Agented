"""Smoke tests for the wave 78 streaming endpoints.

Tests focus on validation paths (unknown ID → 404, missing body → 400).
Actual streaming behavior is exercised by the existing Flask integration
tests prior to migration; ports preserve the same generator + headers.
"""

from litestar.testing import create_test_client

from app_litestar.auth import provide_caller
from app_litestar.routes.streams import (
    backends_stream_router,
    execution_stream_router,
    project_stream_router,
    setup_stream_router,
    teams_stream_router,
)


def _client():
    return create_test_client(
        route_handlers=[
            execution_stream_router,
            project_stream_router,
            backends_stream_router,
            setup_stream_router,
            teams_stream_router,
        ],
        dependencies={"caller": provide_caller},
    )


def test_stream_unknown_execution_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/executions/missing/stream")
    assert resp.status_code == 404


def test_stream_unknown_setup_404(isolated_db):
    with _client() as c:
        resp = c.get("/api/setup/missing/stream")
    assert resp.status_code == 404


def test_stream_project_chat_unknown_project_404(isolated_db):
    with _client() as c:
        resp = c.get("/api/projects/missing/chat/stream")
    assert resp.status_code == 404


def test_stream_backend_connect_unknown_session_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/backends/claude/connect/missing/stream")
    assert resp.status_code == 404


def test_stream_team_generation_requires_description(isolated_db):
    with _client() as c:
        resp = c.post("/admin/teams/generate/stream", json={})
    assert resp.status_code == 400


def test_stream_team_generation_short_description(isolated_db):
    with _client() as c:
        resp = c.post(
            "/admin/teams/generate/stream",
            json={"description": "short"},
        )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Successful stream coverage (replaces deleted Flask test_chat_streaming.py).
#
# The deleted Flask suite proved the migrated streaming contract — these tests
# now hold the line on:
#   - SSE headers (Cache-Control: no-cache, Connection: keep-alive,
#     X-Accel-Buffering: no, Content-Type: text/event-stream)
#   - generator iteration (the Stream actually yields the service's events)
#   - Last-Event-ID cursor handling on project chat + super-agent chat
# ---------------------------------------------------------------------------


def _expected_sse_headers(resp) -> None:
    """Assert every Litestar stream applies the SSE headers `streams.SSE_HEADERS`."""
    assert resp.headers["cache-control"] == "no-cache"
    assert resp.headers["connection"] == "keep-alive"
    assert resp.headers["x-accel-buffering"] == "no"
    assert "text/event-stream" in resp.headers["content-type"]


def test_stream_execution_yields_subscribe_events_and_headers(isolated_db, monkeypatch):
    """An execution stream returns the SSE headers and proxies the service generator."""
    from app.services import execution_log_service as svc

    # Pretend the execution exists and the subscribe generator emits 3 events.
    monkeypatch.setattr(svc.ExecutionLogService, "get_execution", lambda eid: {"id": eid})

    sentinel_events = [
        "event: log\ndata: line-1\n\n",
        "event: log\ndata: line-2\n\n",
        "event: complete\ndata: {}\n\n",
    ]
    monkeypatch.setattr(
        svc.ExecutionLogService,
        "subscribe",
        classmethod(lambda cls, eid: iter(sentinel_events)),
    )

    with _client() as c:
        resp = c.get("/admin/executions/exec-1/stream")
    assert resp.status_code == 200
    _expected_sse_headers(resp)
    body = resp.text
    for chunk in sentinel_events:
        assert chunk in body


def test_stream_setup_yields_events(isolated_db, monkeypatch):
    from app.services import setup_execution_service as svc

    monkeypatch.setattr(
        svc.SetupExecutionService, "get_status", classmethod(lambda cls, eid: {"status": "running"})
    )
    monkeypatch.setattr(
        svc.SetupExecutionService,
        "subscribe",
        classmethod(lambda cls, eid: iter(["event: log\ndata: setup-line\n\n"])),
    )
    with _client() as c:
        resp = c.get("/api/setup/exec-x/stream")
    assert resp.status_code == 200
    _expected_sse_headers(resp)
    assert "setup-line" in resp.text


def test_stream_project_chat_passes_last_event_id_cursor(isolated_db, monkeypatch):
    """Project chat stream forwards Last-Event-ID as the seq cursor; junk → 0."""
    from app.database import get_super_agent_sessions
    from app.services import chat_state_service as svc
    from app_litestar.routes import streams as streams_module

    captured: list[int] = []

    def fake_subscribe(session_id, last_seq=0):
        captured.append(last_seq)
        yield "event: state_delta\ndata: {}\n\n"

    monkeypatch.setattr(svc.ChatStateService, "subscribe", fake_subscribe)
    monkeypatch.setattr(
        streams_module,
        "get_project",
        lambda pid: {"id": pid, "manager_super_agent_id": "sa-x"},
    )
    monkeypatch.setattr(
        streams_module,
        "get_super_agent_sessions",
        lambda sa_id: [{"id": "sess-1", "status": "active"}],
    )

    with _client() as c:
        resp = c.get(
            "/api/projects/proj-1/chat/stream",
            headers={"Last-Event-ID": "42"},
        )
        assert resp.status_code == 200
        _expected_sse_headers(resp)
        assert captured[-1] == 42

        # Junk header → falls back to 0.
        resp = c.get(
            "/api/projects/proj-1/chat/stream",
            headers={"Last-Event-ID": "not-a-number"},
        )
        assert resp.status_code == 200
        assert captured[-1] == 0


def test_stream_super_agent_chat_passes_last_event_id_cursor(isolated_db, monkeypatch):
    """Super-agent chat stream parses Last-Event-ID identically."""
    from app.services import chat_state_service as svc
    from app_litestar.routes.streams import super_agents_stream_router

    captured: list[int] = []

    def fake_subscribe(session_id, last_seq=0):
        captured.append(last_seq)
        yield "event: state_delta\ndata: {}\n\n"

    monkeypatch.setattr(svc.ChatStateService, "subscribe", fake_subscribe)

    client = create_test_client(
        route_handlers=[super_agents_stream_router],
        dependencies={"caller": provide_caller},
    )
    with client as c:
        resp = c.get(
            "/admin/super-agents/sa-x/sessions/sess-1/chat/stream",
            headers={"Last-Event-ID": "7"},
        )
    assert resp.status_code == 200
    _expected_sse_headers(resp)
    assert captured == [7]
