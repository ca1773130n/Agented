"""Per-project AI backend account whitelist + enforcement (v0.7.58).

The whitelist gates non-yolo sessions: ``create_session`` refuses
without a matching ``account_id``. Yolo sessions bypass the gate.

Tests below pin:
* DB helpers (list / add / remove / membership check) — idempotent,
  composite-PK-respecting, cascade-on-project-delete.
* REST endpoints — GET/POST/DELETE shapes.
* ``create_session`` enforcement — 400 / 403 / 201 in the right places.
* Yolo sessions skip the gate.
"""

from __future__ import annotations

import pytest
from litestar.testing import create_test_client

from app.db.connection import get_connection
from app.db.grd import (
    add_allowed_account,
    is_account_allowed_for_project,
    list_allowed_accounts,
    remove_allowed_account,
)
from app_litestar.auth import provide_caller
from app_litestar.routes.grd_routes import grd_router


def _client():
    return create_test_client(
        route_handlers=[grd_router],
        dependencies={"caller": provide_caller},
    )


def _seed_project(project_id: str = "proj-w", name: str = "wl") -> str:
    """Insert a minimal project row. ``local_path`` is filled because
    the session-create route refuses projects without one."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, local_path, created_at, updated_at) "
            "VALUES (?, ?, '/tmp', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (project_id, name),
        )
        conn.commit()
    return project_id


# ── DB helpers ─────────────────────────────────────────────────────


def test_add_list_remove_roundtrip(isolated_db):
    _seed_project()
    assert list_allowed_accounts("proj-w") == []

    assert add_allowed_account("proj-w", "bkd-aaa") is True
    assert add_allowed_account("proj-w", "bkd-bbb") is True

    rows = list_allowed_accounts("proj-w")
    assert {r["account_id"] for r in rows} == {"bkd-aaa", "bkd-bbb"}

    assert is_account_allowed_for_project("proj-w", "bkd-aaa") is True
    assert is_account_allowed_for_project("proj-w", "bkd-zzz") is False

    assert remove_allowed_account("proj-w", "bkd-aaa") is True
    assert remove_allowed_account("proj-w", "bkd-aaa") is False  # already gone
    assert {r["account_id"] for r in list_allowed_accounts("proj-w")} == {"bkd-bbb"}


def test_add_is_idempotent(isolated_db):
    _seed_project()
    assert add_allowed_account("proj-w", "bkd-aaa") is True
    assert add_allowed_account("proj-w", "bkd-aaa") is False
    assert len(list_allowed_accounts("proj-w")) == 1


def test_per_project_isolation(isolated_db):
    _seed_project("proj-a", "a")
    _seed_project("proj-b", "b")
    add_allowed_account("proj-a", "bkd-shared")
    assert is_account_allowed_for_project("proj-a", "bkd-shared") is True
    assert is_account_allowed_for_project("proj-b", "bkd-shared") is False


def test_cascade_delete_on_project(isolated_db):
    """Removing the project clears its whitelist (FK cascade)."""
    _seed_project()
    add_allowed_account("proj-w", "bkd-aaa")
    with get_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM projects WHERE id = 'proj-w'")
        conn.commit()
    assert list_allowed_accounts("proj-w") == []


# ── REST endpoints ────────────────────────────────────────────────


def test_list_endpoint_empty(isolated_db):
    _seed_project()
    with _client() as c:
        resp = c.get("/api/projects/proj-w/allowed-accounts")
    assert resp.status_code == 200
    assert resp.json() == {"allowed_accounts": []}


def test_post_then_get_then_delete(isolated_db):
    _seed_project()
    with _client() as c:
        post = c.post(
            "/api/projects/proj-w/allowed-accounts",
            json={"account_id": "bkd-aaa"},
        )
        assert post.status_code == 201, post.text
        assert post.json()["inserted"] is True

        # Re-post is a no-op (inserted=false).
        again = c.post(
            "/api/projects/proj-w/allowed-accounts",
            json={"account_id": "bkd-aaa"},
        )
        assert again.status_code == 201
        assert again.json()["inserted"] is False

        listed = c.get("/api/projects/proj-w/allowed-accounts")
        assert listed.status_code == 200
        assert [a["account_id"] for a in listed.json()["allowed_accounts"]] == ["bkd-aaa"]

        rm = c.delete("/api/projects/proj-w/allowed-accounts/bkd-aaa")
        assert rm.status_code == 200
        assert rm.json()["removed"] is True

        # Removing again → 404.
        rm2 = c.delete("/api/projects/proj-w/allowed-accounts/bkd-aaa")
        assert rm2.status_code == 404


def test_post_without_account_id_400(isolated_db):
    _seed_project()
    with _client() as c:
        resp = c.post("/api/projects/proj-w/allowed-accounts", json={})
    assert resp.status_code == 400


# ── Enforcement on create_session ─────────────────────────────────


@pytest.fixture
def patch_direct_start(monkeypatch):
    """The session-create route calls ``DirectExecutionHandler.start``,
    which would try to spawn a real subprocess. Replace with a stub
    that records and returns a synthetic session row id."""
    from app.services.execution_type_handler import DirectExecutionHandler

    state: dict = {}

    def fake_start(self, config: dict) -> dict:  # noqa: ARG001
        state["cmd"] = config["cmd"]
        state["yolo"] = config.get("yolo_mode")
        # Pre-create the session row so the route's UPDATE doesn't no-op.
        with get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO project_sessions (id, project_id, status) "
                "VALUES ('psess-wl', ?, 'active')",
                (config["project_id"],),
            )
            conn.commit()
        return {"session_id": "psess-wl", "pid": 1234, "status": "active"}

    monkeypatch.setattr(DirectExecutionHandler, "start", fake_start)
    return state


def test_create_session_non_yolo_requires_account(isolated_db, patch_direct_start):
    _seed_project()
    with _client() as c:
        resp = c.post(
            "/api/projects/proj-w/sessions",
            json={
                "cmd": ["claude"],
                "execution_type": "direct",
                "yolo_mode": False,
                # no account_id, no whitelist either → 403 with the
                # "no allowed accounts" message
            },
        )
    assert resp.status_code == 403


def test_create_session_non_yolo_with_account_not_in_whitelist(isolated_db, patch_direct_start):
    _seed_project()
    add_allowed_account("proj-w", "bkd-aaa")
    with _client() as c:
        resp = c.post(
            "/api/projects/proj-w/sessions",
            json={
                "cmd": ["claude"],
                "execution_type": "direct",
                "yolo_mode": False,
                "account_id": "bkd-zzz",  # not in whitelist
            },
        )
    assert resp.status_code == 403


def test_create_session_non_yolo_with_whitelisted_account_succeeds(isolated_db, patch_direct_start):
    _seed_project()
    add_allowed_account("proj-w", "bkd-aaa")
    with _client() as c:
        resp = c.post(
            "/api/projects/proj-w/sessions",
            json={
                "cmd": ["claude"],
                "execution_type": "direct",
                "yolo_mode": False,
                "account_id": "bkd-aaa",
            },
        )
    assert resp.status_code == 201
    # Non-yolo: --dangerously-skip-permissions must NOT be appended.
    assert "--dangerously-skip-permissions" not in patch_direct_start["cmd"]


def test_create_session_yolo_bypasses_whitelist(isolated_db, patch_direct_start):
    """Yolo sessions skip the whitelist check entirely, even with no
    accounts whitelisted on the project."""
    _seed_project()
    with _client() as c:
        resp = c.post(
            "/api/projects/proj-w/sessions",
            json={
                "cmd": ["claude"],
                "execution_type": "direct",
                "yolo_mode": True,
            },
        )
    assert resp.status_code == 201
    # Yolo: --dangerously-skip-permissions IS appended to the cmd.
    assert "--dangerously-skip-permissions" in patch_direct_start["cmd"]
