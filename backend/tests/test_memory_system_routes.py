"""Routes for the Settings → Memory System card.

The Tesserae CLI is mocked at the ``shutil.which`` boundary so tests
work even on machines without it installed; the per-project state
reads SQLite + filesystem directly.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

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


def _seed_project(
    project_id: str, *, root: str | None = None, name: str = "Test",
    local_path: str | None = None,
):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO projects "
            "(id, name, local_path, tesserae_project_root) "
            "VALUES (?, ?, ?, ?)",
            (project_id, name, local_path, root),
        )
        conn.commit()


# ---------- GET /admin/system/memory -------------------------------------

def test_list_memory_systems_envelope(client):
    """Always returns the bundled memory-system list. Designed to
    grow — test guards against accidental schema breaks."""
    r = client.get("/admin/system/memory")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "memory_systems" in body
    by_id = {f["id"]: f for f in body["memory_systems"]}
    assert "tesserae" in by_id
    t = by_id["tesserae"]
    assert "name" in t
    assert "summary" in t
    assert "cli" in t
    assert "installed" in t["cli"]
    assert "enabled_project_count" in t


def test_list_memory_systems_reports_cli_uninstalled(client):
    """When the CLI isn't on PATH, ``cli.installed`` is False and the
    operator gets a clear hint instead of a silent failure later."""
    with patch("app_litestar.routes.memory_system.shutil.which",
               return_value=None):
        r = client.get("/admin/system/memory")
    body = r.json()
    t = next(f for f in body["memory_systems"] if f["id"] == "tesserae")
    assert t["cli"]["installed"] is False
    assert t["cli"]["path"] is None


# ---------- GET /admin/system/memory/tesserae/projects -------------------

def test_list_tesserae_projects_empty(client):
    r = client.get("/admin/system/memory/tesserae/projects")
    assert r.status_code == 200, r.text
    assert r.json() == {"projects": []}


def test_list_tesserae_projects_disabled_and_enabled(client, tmp_path):
    _seed_project("proj-off", root=None, name="Off")
    (tmp_path / ".tesserae").mkdir()
    _seed_project("proj-on", root=str(tmp_path), name="On")

    r = client.get("/admin/system/memory/tesserae/projects")
    by_id = {p["project_id"]: p for p in r.json()["projects"]}
    assert by_id["proj-off"]["enabled"] is False
    assert by_id["proj-off"]["workspace_initialized"] is False
    assert by_id["proj-on"]["enabled"] is True
    assert by_id["proj-on"]["workspace_initialized"] is True


def test_list_tesserae_projects_session_count_from_manifest(client, tmp_path):
    import json
    tess = tmp_path / ".tesserae"
    tess.mkdir()
    hs = tess / "harness_sessions"
    hs.mkdir()
    (hs / "manifest.json").write_text(json.dumps({
        "version": "1",
        "sessions": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
    }))
    _seed_project("proj-with-manifest", root=str(tmp_path))

    r = client.get("/admin/system/memory/tesserae/projects")
    p = next(x for x in r.json()["projects"]
             if x["project_id"] == "proj-with-manifest")
    assert p["session_count"] == 3
    assert p["last_imported_at"] is not None


# ---------- POST set/unset --------------------------------------------------

def test_set_tesserae_root_enables_project(client, tmp_path):
    _seed_project("proj-set", root=None)
    r = client.post(
        "/admin/system/memory/tesserae/projects/proj-set",
        json={"root": str(tmp_path)},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["project"]["enabled"] is True
    assert Path(body["project"]["tesserae_project_root"]) == tmp_path.resolve()


def test_unset_tesserae_root_disables_project(client, tmp_path):
    _seed_project("proj-unset", root=str(tmp_path))
    r = client.post(
        "/admin/system/memory/tesserae/projects/proj-unset",
        json={"root": None},
    )
    body = r.json()
    assert body["project"]["enabled"] is False
    assert body["project"]["tesserae_project_root"] is None


def test_set_tesserae_root_404_unknown_project(client):
    r = client.post(
        "/admin/system/memory/tesserae/projects/proj-ghost",
        json={"root": "/tmp/wherever"},
    )
    assert r.status_code == 404


def test_set_tesserae_root_validation_missing_body(client):
    _seed_project("proj-no-body")
    r = client.post(
        "/admin/system/memory/tesserae/projects/proj-no-body",
        json={},
    )
    assert r.status_code in (400, 422)


# ---------- POST refresh ----------------------------------------------------

def test_refresh_returns_skipped_reason_when_disabled(client):
    _seed_project("proj-refresh-off", root=None)
    r = client.post(
        "/admin/system/memory/tesserae/projects/proj-refresh-off/refresh"
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["imported"] == 0
    assert body["skipped_reason"] == "tesserae_disabled"


def test_refresh_404_unknown_project(client):
    r = client.post(
        "/admin/system/memory/tesserae/projects/proj-ghost/refresh"
    )
    assert r.status_code == 404
