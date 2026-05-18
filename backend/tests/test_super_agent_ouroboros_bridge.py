"""Tests for the v0.7.91 SuperAgent → goal_loop Ouroboros bridge.

Covers route-level validation + the wiring of the SA's
backend_type / preferred_model into the spawned goal_loop
session config. The handler.start path is patched so the test
doesn't need a real PSM subprocess.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from litestar.testing import create_test_client

from app.db.connection import get_connection
from app.db.ids import _get_unique_project_id
from app.db.rbac import create_user_role
from app_litestar.auth import provide_caller
from app_litestar.routes.super_agents_cluster import super_agents_router


@pytest.fixture
def client():
    with create_test_client(
        route_handlers=[super_agents_router],
        dependencies={"caller": provide_caller},
    ) as c:
        yield c


def _seed_admin_key():
    create_user_role("admin-bridge", "Admin", "admin")


def _seed_project_and_sa(
    *, sa_backend: str = "claude", sa_model: str | None = "claude-sonnet-4-5"
) -> tuple[str, str]:
    """Returns (project_id, super_agent_id)."""
    with get_connection() as conn:
        pid = _get_unique_project_id(conn)
        conn.execute(
            "INSERT INTO projects (id, name, local_path) VALUES (?, ?, ?)",
            (pid, "bridge-test", "/tmp/bridge-test"),
        )
        sa_id = "sa-bridgetst1"
        conn.execute(
            """
            INSERT INTO super_agents (id, name, backend_type, preferred_model)
            VALUES (?, ?, ?, ?)
            """,
            (sa_id, "Bridge SA", sa_backend, sa_model),
        )
        conn.commit()
    return pid, sa_id


def test_ouroboros_run_requires_project_id(client, isolated_db):
    del isolated_db
    _seed_admin_key()
    _, sa_id = _seed_project_and_sa()
    resp = client.post(
        f"/admin/super-agents/{sa_id}/ouroboros-runs",
        headers={"X-API-Key": "admin-bridge"},
        json={"goal": "do thing"},
    )
    assert resp.status_code == 400
    assert "project_id" in resp.text.lower()


def test_ouroboros_run_requires_goal(client, isolated_db):
    del isolated_db
    _seed_admin_key()
    pid, sa_id = _seed_project_and_sa()
    resp = client.post(
        f"/admin/super-agents/{sa_id}/ouroboros-runs",
        headers={"X-API-Key": "admin-bridge"},
        json={"project_id": pid},
    )
    assert resp.status_code == 400
    assert "goal" in resp.text.lower()


def test_ouroboros_run_unknown_super_agent_returns_404(client, isolated_db):
    del isolated_db
    _seed_admin_key()
    resp = client.post(
        "/admin/super-agents/sa-doesnotexist/ouroboros-runs",
        headers={"X-API-Key": "admin-bridge"},
        json={"project_id": "proj-x", "goal": "do thing"},
    )
    assert resp.status_code == 404


def test_ouroboros_run_unknown_project_returns_404(client, isolated_db):
    del isolated_db
    _seed_admin_key()
    _, sa_id = _seed_project_and_sa()
    resp = client.post(
        f"/admin/super-agents/{sa_id}/ouroboros-runs",
        headers={"X-API-Key": "admin-bridge"},
        json={"project_id": "proj-nonexistent", "goal": "do thing"},
    )
    assert resp.status_code == 404


def test_ouroboros_run_wires_sa_backend_and_ouroboros_flag(client, isolated_db):
    """The spawned goal_loop session config must inherit the SA's
    backend_type / preferred_model AND have ``ouroboros: True``
    forced on so the run gets the hypothesis loop.
    """
    del isolated_db
    _seed_admin_key()
    pid, sa_id = _seed_project_and_sa(
        sa_backend="gemini", sa_model="gemini-2.5-pro"
    )

    captured: dict = {}

    def fake_start(self, session_config):
        captured.update(session_config)
        return {"session_id": "psess-test1234", "pid": 4242, "status": "active"}

    # Patch the handler.start so we don't need a real PSM subprocess.
    with patch(
        "app.services.execution_type_handler.GoalLoopSessionHandler.start",
        new=fake_start,
    ):
        # The route also resolves the project's cwd via
        # ProjectWorkspaceService; stub that so we don't depend
        # on the project actually existing on disk.
        with patch(
            "app.services.project_workspace_service."
            "ProjectWorkspaceService.resolve_working_directory",
            return_value="/tmp/bridge-test",
        ):
            resp = client.post(
                f"/admin/super-agents/{sa_id}/ouroboros-runs",
                headers={"X-API-Key": "admin-bridge"},
                json={
                    "project_id": pid,
                    "goal": "ship feature X",
                    "max_iterations": 5,
                    "max_wall_seconds": 600,
                },
            )

    assert resp.status_code == 201
    body = resp.json()
    assert body["session_id"] == "psess-test1234"
    assert body["super_agent_id"] == sa_id

    cfg = captured.get("goal_loop_config") or {}
    assert cfg["goal"] == "ship feature X"
    assert cfg["max_iterations"] == 5
    assert cfg["max_wall_seconds"] == 600
    assert cfg["judge_backend_kind"] == "gemini", (
        "judge must inherit the SA's backend_type"
    )
    assert cfg["judge_model_override"] == "gemini-2.5-pro", (
        "judge must inherit the SA's preferred_model"
    )
    assert cfg["ouroboros"] is True, "bridge must force Ouroboros on"
