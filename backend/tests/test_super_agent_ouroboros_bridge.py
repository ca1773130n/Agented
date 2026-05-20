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


def test_ouroboros_run_requires_project_id_when_no_history(client, isolated_db):
    """v0.7.92 — without prior history, omitting project_id must
    still 400 (the fallback resolver returns None and the route
    surfaces a helpful error rather than silently picking).
    """
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
    # v0.7.92 — super_agent_id flows through so the spawned
    # project_sessions row links back to the SA.
    assert captured.get("super_agent_id") == sa_id


def test_ouroboros_run_falls_back_to_recent_project(client, isolated_db):
    """v0.7.92 — when no project_id is supplied AND the SA has a
    prior project_sessions row, the bridge picks that project as
    the default.
    """
    del isolated_db
    _seed_admin_key()
    pid, sa_id = _seed_project_and_sa()

    # Seed a prior project_sessions row linking SA → project.
    with get_connection() as conn:
        from app.db.ids import _get_unique_project_session_id

        psess_id = _get_unique_project_session_id(conn)
        conn.execute(
            """
            INSERT INTO project_sessions
                (id, project_id, super_agent_id, execution_type, status,
                 started_at)
            VALUES (?, ?, ?, 'goal_loop', 'completed',
                    datetime('now', '-1 hour'))
            """,
            (psess_id, pid, sa_id),
        )
        conn.commit()

    captured: dict = {}

    def fake_start(self, session_config):
        captured.update(session_config)
        return {"session_id": "psess-fb1234567", "pid": 1, "status": "active"}

    with patch(
        "app.services.execution_type_handler.GoalLoopSessionHandler.start",
        new=fake_start,
    ), patch(
        "app.services.project_workspace_service."
        "ProjectWorkspaceService.resolve_working_directory",
        return_value="/tmp/bridge-test",
    ):
        resp = client.post(
            f"/admin/super-agents/{sa_id}/ouroboros-runs",
            headers={"X-API-Key": "admin-bridge"},
            json={"goal": "fallback test"},  # no project_id
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["project_id"] == pid, "fallback must use the SA's most-recent project"
    assert captured.get("project_id") == pid


def test_ouroboros_run_forwards_assembled_system_prompt(client, isolated_db):
    """v0.7.92 — the SA's assembled system prompt (from SOUL /
    IDENTITY / ROLE docs) flows through as
    ``system_prompt_override`` so the spawned claude CLI gets
    the SA's identity via ``--append-system-prompt`` (the actual
    flag the claude-cli renderer uses — ``--system-prompt`` is
    a different, overriding flag and a silent-wrong-runs bug).
    """
    del isolated_db
    _seed_admin_key()
    pid, sa_id = _seed_project_and_sa()

    captured: dict = {}

    def fake_start(self, session_config):
        captured.update(session_config)
        return {"session_id": "psess-sp1234567", "pid": 1, "status": "active"}

    fake_prompt = "## ROLE\n\nYou are the test SA.\n"

    with patch(
        "app.services.execution_type_handler.GoalLoopSessionHandler.start",
        new=fake_start,
    ), patch(
        "app.services.project_workspace_service."
        "ProjectWorkspaceService.resolve_working_directory",
        return_value="/tmp/bridge-test",
    ), patch(
        "app.services.super_agent_session_service."
        "SuperAgentSessionService.assemble_system_prompt",
        return_value=fake_prompt,
    ):
        resp = client.post(
            f"/admin/super-agents/{sa_id}/ouroboros-runs",
            headers={"X-API-Key": "admin-bridge"},
            json={"project_id": pid, "goal": "test prompt forwarding"},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["system_prompt_applied"] is True
    assert captured.get("system_prompt_override") == fake_prompt


def test_ouroboros_run_no_system_prompt_when_assembly_returns_empty(
    client, isolated_db
):
    """SAs with no documents → empty assembled prompt → no
    ``--system-prompt`` injection (avoids passing an empty
    string to the claude CLI).
    """
    del isolated_db
    _seed_admin_key()
    pid, sa_id = _seed_project_and_sa()

    captured: dict = {}

    def fake_start(self, session_config):
        captured.update(session_config)
        return {"session_id": "psess-empty12345", "pid": 1, "status": "active"}

    with patch(
        "app.services.execution_type_handler.GoalLoopSessionHandler.start",
        new=fake_start,
    ), patch(
        "app.services.project_workspace_service."
        "ProjectWorkspaceService.resolve_working_directory",
        return_value="/tmp/bridge-test",
    ), patch(
        "app.services.super_agent_session_service."
        "SuperAgentSessionService.assemble_system_prompt",
        return_value="",
    ):
        resp = client.post(
            f"/admin/super-agents/{sa_id}/ouroboros-runs",
            headers={"X-API-Key": "admin-bridge"},
            json={"project_id": pid, "goal": "no doc SA"},
        )

    assert resp.status_code == 201
    assert resp.json()["system_prompt_applied"] is False
    assert captured.get("system_prompt_override") is None


def test_list_ouroboros_runs_returns_super_agent_sessions(client, isolated_db):
    """v0.7.92 — the list endpoint returns project_sessions filtered
    by super_agent_id, oldest-first sort excluded.
    """
    del isolated_db
    _seed_admin_key()
    pid, sa_id = _seed_project_and_sa()
    # Seed another SA so we can confirm the filter excludes it.
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO super_agents (id, name, backend_type) "
            "VALUES ('sa-other', 'Other', 'claude')"
        )
        from app.db.ids import _get_unique_project_session_id

        my_id_1 = _get_unique_project_session_id(conn)
        my_id_2 = _get_unique_project_session_id(conn)
        other_id = _get_unique_project_session_id(conn)
        for sid, link in (
            (my_id_1, sa_id),
            (my_id_2, sa_id),
            (other_id, "sa-other"),
        ):
            conn.execute(
                """
                INSERT INTO project_sessions
                    (id, project_id, super_agent_id, execution_type, status)
                VALUES (?, ?, ?, 'goal_loop', 'completed')
                """,
                (sid, pid, link),
            )
        conn.commit()

    resp = client.get(
        f"/admin/super-agents/{sa_id}/ouroboros-runs",
        headers={"X-API-Key": "admin-bridge"},
    )
    assert resp.status_code == 200
    runs = resp.json()["runs"]
    ids = {r["session_id"] for r in runs}
    assert my_id_1 in ids and my_id_2 in ids
    assert other_id not in ids
    # All listed runs include the iteration_count aggregate.
    for r in runs:
        assert "iteration_count" in r


# --- v0.7.92 review fixes (PR #139 codex feedback) -----------------


def test_goal_loop_handler_uses_append_system_prompt_flag(isolated_db):
    """Regression guard for the silent-wrong-runs bug: the goal_loop
    handler MUST emit ``--append-system-prompt`` (not the lookalike
    ``--system-prompt`` flag, which means something different in
    claude-cli and produces a silently-broken run).

    The mocked-handler bridge tests can't catch this — they swap
    ``handler.start`` out entirely. So construct a session_config
    manually and intercept ``ProjectSessionManager.create_session``
    to capture the cmd that the handler hands down.
    """
    del isolated_db
    from app.services.execution_type_handler import GoalLoopSessionHandler

    captured: dict = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return "psess-flagchk1"

    with patch(
        "app.services.execution_type_handler.ProjectSessionManager.create_session",
        new=fake_create,
    ):
        GoalLoopSessionHandler().start(
            {
                "project_id": "proj-x",
                "cwd": "/tmp",
                "execution_mode": "autonomous",
                "yolo_mode": False,
                "system_prompt_override": "## ROLE\n\nYou are X.",
                "goal_loop_config": {
                    "goal": "g",
                    "max_iterations": 1,
                    "max_wall_seconds": 60,
                },
            }
        )

    cmd = captured.get("cmd") or []
    assert "--append-system-prompt" in cmd, (
        f"goal_loop handler must use --append-system-prompt; got cmd={cmd}"
    )
    assert "--system-prompt" not in cmd, (
        "the bare --system-prompt flag is a silent-wrong-runs bug — "
        "the renderer must use the append variant"
    )


def test_super_agent_delete_does_not_break_with_history(client, isolated_db):
    """v0.7.92 — migration v130 adds ``ON DELETE SET NULL`` on the
    project_sessions.super_agent_id FK so deleting a SuperAgent that
    has historical Ouroboros runs is still allowed; the run history
    is preserved (with the SA pointer nulled out).
    """
    del isolated_db
    _seed_admin_key()
    pid, sa_id = _seed_project_and_sa()

    from app.db.ids import _get_unique_project_session_id

    with get_connection() as conn:
        # FK enforcement is per-connection in SQLite; enable it
        # explicitly so the test reflects production behaviour.
        conn.execute("PRAGMA foreign_keys = ON")
        psess_id = _get_unique_project_session_id(conn)
        conn.execute(
            """
            INSERT INTO project_sessions
                (id, project_id, super_agent_id, execution_type, status)
            VALUES (?, ?, ?, 'goal_loop', 'completed')
            """,
            (psess_id, pid, sa_id),
        )
        conn.commit()

        # Delete the SA — must succeed, history must survive.
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM super_agents WHERE id = ?", (sa_id,))
        conn.commit()

        row = conn.execute(
            "SELECT super_agent_id FROM project_sessions WHERE id = ?",
            (psess_id,),
        ).fetchone()

    assert row is not None, "session row should survive SA deletion"
    assert row[0] is None, "super_agent_id should be nulled, not cascaded"


def test_ouroboros_run_scoped_to_caller_user_id(client, isolated_db):
    """v0.7.92 — when the caller has a ``user_id``, they can only
    spawn runs against SuperAgents they own. Other-owner SAs return
    404 (not 403, to avoid leaking existence).
    """
    del isolated_db
    # Seed two real users so the FK on user_roles.user_id holds.
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO users (id, email) VALUES (?, ?)",
            ("user-alice-id", "alice@test"),
        )
        conn.execute(
            "INSERT INTO users (id, email) VALUES (?, ?)",
            ("user-mallory-id", "mallory@test"),
        )
        conn.commit()

    # Seed a keyed editor (NOT the legacy admin path used by the
    # other tests — those use admin-bridge which has no user_id).
    create_user_role("user-alice", "Alice", "editor", user_id="user-alice-id")

    with get_connection() as conn:
        pid = _get_unique_project_id(conn)
        conn.execute(
            "INSERT INTO projects (id, name, local_path, user_id) "
            "VALUES (?, ?, ?, ?)",
            (pid, "alice-proj", "/tmp/alice", "user-alice-id"),
        )
        # SA owned by a DIFFERENT user.
        conn.execute(
            "INSERT INTO super_agents (id, name, backend_type, user_id) "
            "VALUES ('sa-mallory12', 'Mallory SA', 'claude', 'user-mallory-id')"
        )
        conn.commit()

    resp = client.post(
        "/admin/super-agents/sa-mallory12/ouroboros-runs",
        headers={"X-API-Key": "user-alice"},
        json={"project_id": pid, "goal": "exfil"},
    )
    assert resp.status_code == 404, (
        "scope check must hide other users' SAs as 404 (not 403/200)"
    )


# --- v0.7.97: delete/start race regression (PR #139 deferred MINOR) -------


def test_ouroboros_run_returns_409_when_persist_fails_on_race(client, isolated_db):
    """v0.7.97 — when the post-spawn INSERT raises
    ``SessionPersistError`` (the FK on ``super_agent_id`` failing
    because the SA was concurrently deleted), the bridge route must
    translate it to a 409 — not let it escape as a 500 — so the
    operator can distinguish "race lost, retry maybe" from "server
    crashed".

    Patches ``GoalLoopSessionHandler.start`` to raise
    ``SessionPersistError`` directly; the underlying PSM cleanup is
    covered separately at the PSM unit level.
    """
    del isolated_db
    _seed_admin_key()
    pid, sa_id = _seed_project_and_sa()

    from app.services.project_session_manager import SessionPersistError

    def fake_start(self, session_config):
        raise SessionPersistError(
            "Session persist failed: parent resource missing"
        )

    with patch(
        "app.services.execution_type_handler.GoalLoopSessionHandler.start",
        new=fake_start,
    ), patch(
        "app.services.project_workspace_service."
        "ProjectWorkspaceService.resolve_working_directory",
        return_value="/tmp/bridge-test",
    ):
        resp = client.post(
            f"/admin/super-agents/{sa_id}/ouroboros-runs",
            headers={"X-API-Key": "admin-bridge"},
            json={"project_id": pid, "goal": "race the delete"},
        )

    assert resp.status_code == 409, (
        f"persist-race must surface as 409, got {resp.status_code}: {resp.text}"
    )
    assert "parent resource missing" in resp.text.lower()
