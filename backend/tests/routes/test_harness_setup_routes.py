"""P5 — ``/api/projects/{id}/harness-setup`` trigger / status / SSE stream.

Mirrors test_forge_bindings_routes.py (TestClient + isolated_db). The real
off-thread ``TeamHarnessSetupService.setup`` is monkeypatched to a synchronous
stub that writes step rows and flips status to 'ready' so the SSE stream
terminates deterministically.
"""

from __future__ import annotations

import pytest
from litestar.testing import create_test_client

from app.db import create_project
from app.db.projects import (
    get_harness_setup_status,
    set_harness_setup_status,
    upsert_harness_setup_step,
)
from app_litestar.auth import provide_caller
from app_litestar.routes import grd_routes
from app_litestar.routes.grd_routes import grd_router


def _client():
    return create_test_client(
        route_handlers=[grd_router],
        dependencies={"caller": provide_caller},
    )


@pytest.fixture
def project_id(isolated_db):
    del isolated_db
    return create_project(name="harness-test", description="fixture")


def _sync_stub(project_id: str) -> str:
    """Synchronous stand-in for the real off-thread setup."""
    upsert_harness_setup_step(project_id, "grd_init", "ok", detail="initialized")
    upsert_harness_setup_step(project_id, "team_topology", "ok", detail="topology")
    set_harness_setup_status(project_id, "ready")
    return "ready"


def test_trigger_returns_202_and_flips_running(project_id, monkeypatch):
    monkeypatch.setattr(grd_routes.TeamHarnessSetupService, "setup", staticmethod(_sync_stub))
    with _client() as c:
        r = c.post(f"/api/projects/{project_id}/harness-setup")
    assert r.status_code == 202
    assert r.json()["harness_setup_status"] == "running"
    # The synchronous stub ran on the spawned thread; final state is ready.
    assert get_harness_setup_status(project_id) in ("running", "ready")


def test_status_returns_step_list(project_id, monkeypatch):
    monkeypatch.setattr(grd_routes.TeamHarnessSetupService, "setup", staticmethod(_sync_stub))
    _sync_stub(project_id)
    with _client() as c:
        r = c.get(f"/api/projects/{project_id}/harness-setup/status")
    assert r.status_code == 200
    body = r.json()
    assert body["harness_setup_status"] == "ready"
    keys = {s["step_key"] for s in body["steps"]}
    assert {"grd_init", "team_topology"} <= keys


def test_status_unknown_project_404(isolated_db):
    del isolated_db
    with _client() as c:
        r = c.get("/api/projects/proj-nope00/harness-setup/status")
    assert r.status_code == 404


def test_stream_is_event_stream_with_step_events(project_id):
    # Pre-seed a ready state so the generator emits step frames then terminates.
    _sync_stub(project_id)
    with _client() as c:
        r = c.get(f"/api/projects/{project_id}/harness-setup/stream")
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    body = r.text
    assert "event: step" in body
    assert '"step": "grd_init"' in body
    assert "event: done" in body
