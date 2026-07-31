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
def client(isolated_db, monkeypatch):
    # An inherited real AGENTED_API_KEY in the shell env makes the ApiKey
    # middleware reject the fixture's dummy "test-key" (401 on every route).
    # Drop it so bootstrap-auth against the empty user_roles table applies.
    monkeypatch.delenv("AGENTED_API_KEY", raising=False)
    monkeypatch.setenv("AGENTED_LITESTAR_SKIP_STARTUP", "1")
    app = create_app()
    with TestClient(app=app) as c:
        c.headers.update({"X-API-Key": "test-key"})
        yield c


def _seed_project(
    project_id: str,
    *,
    root: str | None = None,
    name: str = "Test",
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
    # `_cli_status_cache` is module-level and process-wide, so any earlier test
    # that saw a real tesserae install leaves "installed" cached and this test
    # never reaches the patched `which`. It passed alone and failed in-file —
    # order dependence, not a route bug.
    from app_litestar.routes.memory_system import _cli_status_cache

    _cli_status_cache.clear()
    with patch("app_litestar.routes.memory_system.shutil.which", return_value=None):
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
    (hs / "manifest.json").write_text(
        json.dumps(
            {
                "version": "1",
                "sessions": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
            }
        )
    )
    _seed_project("proj-with-manifest", root=str(tmp_path))

    r = client.get("/admin/system/memory/tesserae/projects")
    p = next(x for x in r.json()["projects"] if x["project_id"] == "proj-with-manifest")
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
    r = client.post("/admin/system/memory/tesserae/projects/proj-refresh-off/refresh")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["imported"] == 0
    assert body["skipped_reason"] == "tesserae_disabled"


def test_refresh_404_unknown_project(client):
    r = client.post("/admin/system/memory/tesserae/projects/proj-ghost/refresh")
    assert r.status_code == 404


# ---------- per-op endpoints (init / ingest / compile / build-site /
#            status / job) ---------------------------------------------------


def test_status_returns_workspace_introspection(client, tmp_path):
    import json

    tess = tmp_path / ".tesserae"
    tess.mkdir()
    # Plant a graph + manifest so status reports the populated state
    (tess / "graph.json").write_text('{"nodes": [{"x": 1}]}' + " " * 200)
    hs = tess / "harness_sessions"
    hs.mkdir()
    (hs / "manifest.json").write_text(
        json.dumps(
            {
                "version": "1",
                "sessions": [{"id": "a"}],
            }
        )
    )
    _seed_project("proj-status", root=str(tmp_path))

    r = client.get("/admin/system/memory/tesserae/projects/proj-status/status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["workspace_initialized"] is True
    assert body["graph_compiled"] is True
    assert body["session_count"] == 1


def test_status_404_unknown_project(client):
    r = client.get("/admin/system/memory/tesserae/projects/proj-ghost/status")
    assert r.status_code == 404


def test_init_invokes_cli_with_init_subcommand(client, tmp_path):
    _seed_project("proj-init", root=str(tmp_path))

    class _FakeResult:
        returncode = 0
        stdout = "Initialized project wiki"
        stderr = ""

    captured: dict = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["cwd"] = kwargs.get("cwd")
        return _FakeResult()

    from app.services import tesserae_integration as ti

    with patch.object(ti.subprocess, "run", side_effect=_fake_run):
        r = client.post("/admin/system/memory/tesserae/projects/proj-init/init")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["ok"] is True
    # Modern top-level form (0.9.0 retired `tesserae project init`).
    assert captured["cmd"][1] == "init"
    assert "project" not in captured["cmd"][:2]
    assert captured["cwd"] == str(tmp_path)


def test_ingest_skips_when_no_paths_exist(client, tmp_path):
    """Default ingest paths (CLAUDE.md / README.md / etc.) don't exist
    in tmp_path → ingest reports ``no_paths_to_ingest`` and never
    invokes the CLI."""
    _seed_project("proj-ingest-empty", root=str(tmp_path))
    from app.services import tesserae_integration as ti

    with patch.object(ti.subprocess, "run") as mock_run:
        r = client.post("/admin/system/memory/tesserae/projects/proj-ingest-empty/ingest")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["ok"] is False
    assert body["reason"] == "no_paths_to_ingest"
    mock_run.assert_not_called()


def test_ingest_passes_resolved_paths_to_cli(client, tmp_path):
    (tmp_path / "README.md").write_text("# readme")
    (tmp_path / "CLAUDE.md").write_text("# claude")
    _seed_project("proj-ingest-yes", root=str(tmp_path))

    class _FakeResult:
        returncode = 0
        stdout = "Ingested"
        stderr = ""

    captured: dict = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeResult()

    from app.services import tesserae_integration as ti

    with patch.object(ti.subprocess, "run", side_effect=_fake_run):
        r = client.post("/admin/system/memory/tesserae/projects/proj-ingest-yes/ingest")
    assert r.status_code == 201
    assert r.json()["ok"] is True
    # Both README.md + CLAUDE.md should be in the argv.
    argv_str = " ".join(captured["cmd"])
    assert "README.md" in argv_str
    assert "CLAUDE.md" in argv_str


def test_compile_dispatches_async_returns_job_id(client, tmp_path):
    _seed_project("proj-compile", root=str(tmp_path))
    r = client.post("/admin/system/memory/tesserae/projects/proj-compile/compile")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "running"
    assert body["op"] == "compile"
    assert body["job_id"].startswith("tess-compile-")


def test_compile_404_unknown_project(client):
    r = client.post("/admin/system/memory/tesserae/projects/proj-ghost/compile")
    assert r.status_code == 404


def test_compile_rejects_disabled_project(client):
    _seed_project("proj-disabled", root=None)
    r = client.post("/admin/system/memory/tesserae/projects/proj-disabled/compile")
    # ValidationException → 400 or 422
    assert r.status_code in (400, 422)


def test_job_status_404_unknown_job(client):
    r = client.get("/admin/system/memory/tesserae/jobs/tess-bogus-aabbccdd")
    assert r.status_code == 404


# ---------- GET /admin/system/memory/lint --------------------------------
# NOTE: the HTTP layer of this file shares a pre-existing env-dependent 401 (a
# provided-but-unseeded X-API-Key is rejected locally), so the lint handler is
# pinned via a direct call — the route is a 1-line passthrough to build_lint,
# whose parsing is covered in test_tesserae_integration.py.


def test_get_memory_lint_handler_passes_through(isolated_db):
    from app_litestar.routes.memory_system import get_memory_lint

    fake = {
        "ok": True,
        "report": {
            "findings": [{"severity": "warning", "code": "GRAPH_WIKI_DRIFT", "message": "d"}],
            "by_code": {"GRAPH_WIKI_DRIFT": 1},
            "by_severity": {"info": 0, "warning": 1, "error": 0},
        },
        "reason": None,
    }
    # get_memory_lint is a Litestar route handler; call the wrapped fn directly.
    handler = get_memory_lint.fn
    with patch("app.services.tesserae_integration.build_lint", return_value=fake) as bl:
        out = handler(refresh=True)
    bl.assert_called_once_with(refresh=True)
    assert out["report"]["by_severity"]["warning"] == 1


def test_graph_status_handler_passes_through(isolated_db):
    from app_litestar.routes.memory_system import get_graph_status

    fake = {"ok": True, "status": {"nodes": 42, "edges": 7}, "reason": None}
    with patch("app.services.tesserae_integration.graph_status", return_value=fake) as gs:
        out = get_graph_status.fn()
    gs.assert_called_once_with()
    assert out["status"]["nodes"] == 42


def test_graph_query_handler_passes_args_through(isolated_db):
    from app_litestar.routes.memory_system import query_graph as query_graph_route

    fake = {"ok": True, "question": "loop", "hits": [{"node_id": "n1"}], "reason": None}
    with patch("app.services.tesserae_integration.query_graph", return_value=fake) as qg:
        out = query_graph_route.fn(q="loop", top_k=5, kind="papers")
    qg.assert_called_once_with("loop", top_k=5, kind="papers")
    assert out["hits"][0]["node_id"] == "n1"


def test_start_research_handler_dispatches_async(isolated_db):
    from app_litestar.routes.memory_system import start_research

    with patch("app.services.tesserae_integration.run_research_async", return_value="tess-research-abc") as rr:
        out = start_research.fn(
            data={"query": "why deferred?", "breadth": 4, "depth": 2, "max_iters": 6, "top_k": 5}
        )
    rr.assert_called_once_with("why deferred?", breadth=4, depth=2, max_iters=6, top_k=5)
    assert out["job_id"] == "tess-research-abc"
    assert out["status"] == "running"


def test_start_research_handler_requires_query(isolated_db):
    from litestar.exceptions import ValidationException

    from app_litestar.routes.memory_system import start_research

    with patch("app.services.tesserae_integration.run_research_async") as rr:
        for bad in ({}, {"query": ""}, {"query": "   "}, {"query": 5}):
            try:
                start_research.fn(data=bad)
                raise AssertionError(f"expected ValidationException for {bad}")
            except ValidationException:
                pass
        # non-int knob rejected too
        try:
            start_research.fn(data={"query": "q", "breadth": "big"})
            raise AssertionError("expected ValidationException for non-int breadth")
        except ValidationException:
            pass
        rr.assert_not_called()


def test_config_handler_passes_through(isolated_db):
    from app_litestar.routes.memory_system import get_memory_config

    fake = {"ok": True, "provider": "codex", "effort": "medium", "liveness_ok": True, "source": "x", "reason": None}
    with patch("app.services.tesserae_integration.config_status", return_value=fake) as cs:
        out = get_memory_config.fn()
    cs.assert_called_once_with()
    assert out["provider"] == "codex" and out["liveness_ok"] is True


def test_engine_refresh_handler_dispatches_async(isolated_db):
    from app_litestar.routes.memory_system import engine_refresh

    with patch("app.services.tesserae_integration.engine_refresh_async", return_value="tess-engine-xyz") as er:
        out = engine_refresh.fn()
    er.assert_called_once_with()
    assert out["job_id"] == "tess-engine-xyz"
    assert out["op"] == "engine-refresh"
