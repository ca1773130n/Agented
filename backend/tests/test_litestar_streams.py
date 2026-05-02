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
