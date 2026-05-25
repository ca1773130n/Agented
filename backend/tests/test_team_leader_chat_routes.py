"""Routes for the per-project Team Leader chat panel.

Resolution is read-only against the DB except for the side-effects
of creating a project-SA instance + leader session, both of which
are exercised by their own dedicated tests in
``test_super_agent_session_service.py`` and ``test_instance_service.py``.
Here we only check the route contract.
"""

from __future__ import annotations

import pytest
from litestar.testing import TestClient

from app.db.connection import get_connection
from app_litestar.main import create_app


@pytest.fixture
def client(isolated_db):
    import os

    os.environ["AGENTED_LITESTAR_SKIP_STARTUP"] = "1"
    app = create_app()
    with TestClient(app=app) as c:
        c.headers.update({"X-API-Key": "test-key"})
        yield c


def _seed_super_agent(sa_id: str, name: str = "Leader"):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO super_agents (id, name) VALUES (?, ?)",
            (sa_id, name),
        )
        conn.commit()


def _seed_project(
    project_id: str, *, manager_sa_id: str | None = None,
    tesserae_root: str | None = None,
):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO projects "
            "(id, name, manager_super_agent_id, tesserae_project_root) "
            "VALUES (?, 'P', ?, ?)",
            (project_id, manager_sa_id, tesserae_root),
        )
        conn.commit()


def test_open_chat_404_unknown_project(client):
    r = client.post(
        "/admin/projects/proj-ghost/team-leader/chat/session"
    )
    assert r.status_code == 404


def test_open_chat_400_no_manager_configured(client):
    _seed_project("proj-no-mgr", manager_sa_id=None)
    r = client.post(
        "/admin/projects/proj-no-mgr/team-leader/chat/session"
    )
    assert r.status_code in (400, 422)
    body = r.json()
    msg = body.get("message") or body.get("detail") or str(body)
    assert "team leader" in msg.lower() or "manager" in msg.lower()


def test_open_chat_resolves_super_agent_and_session(client, tmp_path):
    """Happy path: project + manager SA → instance + session created;
    response carries both IDs, the leader name, and tesserae_enabled."""
    _seed_super_agent("sa-leader-x", name="Morpheus")
    _seed_project(
        "proj-leader-x",
        manager_sa_id="sa-leader-x",
        tesserae_root=str(tmp_path),
    )

    r = client.post(
        "/admin/projects/proj-leader-x/team-leader/chat/session"
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["project_id"] == "proj-leader-x"
    assert body["leader_template_id"] == "sa-leader-x"
    assert body["leader_name"] == "Morpheus"
    assert body["tesserae_enabled"] is True
    # IDs must be non-empty
    assert body["super_agent_id"]
    assert body["session_id"]


def test_open_chat_idempotent_reuses_existing_session(client):
    """Two consecutive opens return the SAME session_id (and the same
    instance). The chat panel can refresh / reconnect without
    spawning a new conversation."""
    _seed_super_agent("sa-leader-y")
    _seed_project("proj-leader-y", manager_sa_id="sa-leader-y")
    first = client.post(
        "/admin/projects/proj-leader-y/team-leader/chat/session",
    ).json()
    second = client.post(
        "/admin/projects/proj-leader-y/team-leader/chat/session",
    ).json()
    assert first["super_agent_id"] == second["super_agent_id"]
    assert first["session_id"] == second["session_id"]


def test_open_chat_tesserae_disabled_flag_off_when_not_set(client):
    _seed_super_agent("sa-leader-z")
    _seed_project(
        "proj-leader-z", manager_sa_id="sa-leader-z",
        tesserae_root=None,
    )
    r = client.post(
        "/admin/projects/proj-leader-z/team-leader/chat/session"
    )
    body = r.json()
    assert body["tesserae_enabled"] is False
