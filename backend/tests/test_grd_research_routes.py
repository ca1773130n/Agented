"""Research route shape tests (20-01, REQ-14).

Exercises the five ``/api/projects/{id}/research/*`` routes through a
Litestar TestClient. The handler / workspace resolution / on-disk reads are
mocked so the assertions cover route wiring + shapes, not the live loop:

* POST /research/start -> {session_id}
* POST /research/{thread_id}/resume -> {session_id}
* GET /research/threads -> [] for a missing dir AND parsed frontmatter when
  a fixture thread dir is present
* GET /research/threads/{id} -> None-safe THREAD/HYPOTHESES/FINDING bundle
* GET /research/status -> gd passthrough

Per CLAUDE.md the TestClient logger doesn't propagate to caplog, so where a
warning matters we spy on ``module.logger.warning`` via monkeypatch.
"""

from litestar.testing import create_test_client

from app_litestar.auth import provide_caller
from app_litestar.routes import grd_routes as module
from app_litestar.routes.grd_routes import grd_router


def _client():
    return create_test_client(
        route_handlers=[grd_router],
        dependencies={"caller": provide_caller},
    )


def _patch_project(monkeypatch):
    """Make _ensure_project pass for any id."""
    monkeypatch.setattr(module, "get_project", lambda pid: {"id": pid})


def _patch_cwd(monkeypatch, cwd="/resolved/cwd"):
    monkeypatch.setattr(
        module.ProjectWorkspaceService,
        "resolve_working_directory",
        staticmethod(lambda pid: cwd),
    )


# ---------------------------------------------------------------------------
# 404 / validation
# ---------------------------------------------------------------------------


def test_research_start_unknown_project_404(isolated_db):
    with _client() as c:
        resp = c.post("/api/projects/missing/research/start", json={"question": "q"})
    assert resp.status_code == 404


def test_research_start_requires_question(isolated_db, monkeypatch):
    _patch_project(monkeypatch)
    with _client() as c:
        resp = c.post("/api/projects/p/research/start", json={})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /research/start
# ---------------------------------------------------------------------------


def test_research_start_returns_session_id(isolated_db, monkeypatch):
    _patch_project(monkeypatch)

    class FakeHandler:
        def start(self, config):
            assert config["question"] == "does X improve Y?"
            assert config["max_iterations"] == 5
            assert config["no_gates"] is True
            return {"session_id": "sess-r-1"}

    monkeypatch.setattr(module, "get_handler", lambda kind: FakeHandler())

    with _client() as c:
        resp = c.post(
            "/api/projects/p/research/start",
            json={
                "question": "does X improve Y?",
                "max_iterations": 5,
                "no_gates": True,
            },
        )
    assert resp.status_code == 201
    assert resp.json() == {"session_id": "sess-r-1"}


def test_research_start_surfaces_handler_error(isolated_db, monkeypatch):
    _patch_project(monkeypatch)

    class FailHandler:
        def start(self, config):
            return {"error": "no clone configured"}

    monkeypatch.setattr(module, "get_handler", lambda kind: FailHandler())

    with _client() as c:
        resp = c.post("/api/projects/p/research/start", json={"question": "q"})
    assert resp.status_code == 400
    assert "no clone" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /research/{thread_id}/resume
# ---------------------------------------------------------------------------


def test_research_resume_returns_session_id(isolated_db, monkeypatch):
    _patch_project(monkeypatch)

    class FakeHandler:
        def start(self, config):
            assert config["thread_id"] == "thread-abc"
            return {"session_id": "sess-r-2"}

    monkeypatch.setattr(module, "get_handler", lambda kind: FakeHandler())

    with _client() as c:
        resp = c.post("/api/projects/p/research/thread-abc/resume", json={})
    assert resp.status_code == 201
    assert resp.json() == {"session_id": "sess-r-2"}


# ---------------------------------------------------------------------------
# GET /research/threads — empty dir AND frontmatter-present
# ---------------------------------------------------------------------------


def test_research_threads_empty_when_dir_missing(isolated_db, monkeypatch, tmp_path):
    _patch_project(monkeypatch)
    # cwd has no .planning/research/threads/ — the dir does not exist until
    # the first run. The route must return [] rather than erroring.
    _patch_cwd(monkeypatch, cwd=str(tmp_path))

    with _client() as c:
        resp = c.get("/api/projects/p/research/threads")
    assert resp.status_code == 200
    assert resp.json() == {"threads": []}


def test_research_threads_parses_frontmatter(isolated_db, monkeypatch, tmp_path):
    _patch_project(monkeypatch)
    _patch_cwd(monkeypatch, cwd=str(tmp_path))

    thread_dir = tmp_path / ".planning" / "research" / "threads" / "t-001"
    thread_dir.mkdir(parents=True)
    (thread_dir / "THREAD.md").write_text(
        "---\n"
        "id: t-001\n"
        'question: "does X improve Y?"\n'
        "status: active\n"
        "iteration: 3\n"
        "max_iterations: 10\n"
        "---\n\n# notes\n"
    )

    with _client() as c:
        resp = c.get("/api/projects/p/research/threads")
    assert resp.status_code == 200
    threads = resp.json()["threads"]
    assert len(threads) == 1
    t = threads[0]
    assert t["id"] == "t-001"
    assert t["question"] == "does X improve Y?"
    assert t["status"] == "active"
    assert t["iteration"] == 3
    assert t["max_iterations"] == 10


# ---------------------------------------------------------------------------
# GET /research/threads/{id} — None-safe bundle
# ---------------------------------------------------------------------------


def test_research_read_thread_none_safe_when_files_absent(isolated_db, monkeypatch, tmp_path):
    _patch_project(monkeypatch)
    _patch_cwd(monkeypatch, cwd=str(tmp_path))

    with _client() as c:
        resp = c.get("/api/projects/p/research/threads/ghost")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "ghost"
    assert body["thread"] is None
    assert body["hypotheses"] is None
    assert body["finding"] is None


def test_research_read_thread_reads_present_files(isolated_db, monkeypatch, tmp_path):
    _patch_project(monkeypatch)
    _patch_cwd(monkeypatch, cwd=str(tmp_path))

    thread_dir = tmp_path / ".planning" / "research" / "threads" / "t-002"
    thread_dir.mkdir(parents=True)
    (thread_dir / "THREAD.md").write_text("# thread body")
    (thread_dir / "FINDING.md").write_text("# the finding")
    # HYPOTHESES.md deliberately absent -> None

    with _client() as c:
        resp = c.get("/api/projects/p/research/threads/t-002")
    assert resp.status_code == 200
    body = resp.json()
    assert body["thread"] == "# thread body"
    assert body["finding"] == "# the finding"
    assert body["hypotheses"] is None


# ---------------------------------------------------------------------------
# GET /research/status — passthrough
# ---------------------------------------------------------------------------


def test_research_status_passthrough(isolated_db, monkeypatch):
    _patch_project(monkeypatch)
    _patch_cwd(monkeypatch)

    monkeypatch.setattr(
        module.GrdCliService,
        "research_status",
        classmethod(lambda cls, cwd, thread_id=None: {"success": True, "data": {"ok": 1}}),
    )

    with _client() as c:
        resp = c.get("/api/projects/p/research/status")
    assert resp.status_code == 200
    assert resp.json() == {"success": True, "data": {"ok": 1}}
