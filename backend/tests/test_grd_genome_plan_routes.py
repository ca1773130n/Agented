"""HTTP-level tests for the GRD genome / plan-selection / promote / tournament
routes.

These mirror ``tests/test_grd_harness_routes.py`` (same app/router/auth/
``isolated_db`` setup). They monkeypatch the runner functions
(``grd_genome_patterns_runner.mine_patterns`` / ``promote_suggestion`` and
``grd_plan_selection_runner.select_candidate`` / ``plan_tournament``) to capture
the kwargs the handlers pass and return canned results, so the route wiring is
exercised without invoking the real ``gd`` CLI.
"""

from litestar.testing import create_test_client

import app.services.grd_genome_patterns_runner as patterns_runner
import app.services.grd_plan_selection_runner as selection_runner
from app.db.connection import get_connection
from app_litestar.auth import provide_caller
from app_litestar.routes.grd_routes import grd_router


def _client():
    return create_test_client(
        route_handlers=[grd_router],
        dependencies={"caller": provide_caller},
    )


def _seed_project(path: str, pid: str = "proj-gp") -> str:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, status, local_path) VALUES (?, 'GP', 'active', ?)",
            (pid, path),
        )
        conn.commit()
    return pid


# ---------------------------------------------------------------------------
# genome/patterns (mine_patterns)
# ---------------------------------------------------------------------------


def test_mine_patterns_success_passes_flags_and_returns_body(isolated_db, monkeypatch, tmp_path):
    calls = {}

    def fake_mine(project_id, cwd, **kw):
        calls.update(project_id=project_id, cwd=cwd, kw=kw)
        return {"success": True, "data": {"suggestions": []}, "error": None, "mirrored": "gsg-1"}

    monkeypatch.setattr(patterns_runner, "mine_patterns", fake_mine)
    pid = _seed_project(str(tmp_path))
    with _client() as c:
        resp = c.post(
            f"/api/projects/{pid}/grd/genome/patterns",
            json={"apply": True, "min_occurrences": 3, "effect_size": 0.2, "fdr_q": 0.05},
        )
    # POST handlers return Litestar's default 201 on success.
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    assert body["mirrored"] == "gsg-1"
    assert calls["project_id"] == pid
    assert calls["cwd"] == str(tmp_path)
    assert calls["kw"] == {
        "apply": True,
        "min_occurrences": 3,
        "effect_size": 0.2,
        "fdr_q": 0.05,
    }


def test_mine_patterns_failure_returns_400(isolated_db, monkeypatch, tmp_path):
    monkeypatch.setattr(
        patterns_runner,
        "mine_patterns",
        lambda *a, **k: {"success": False, "data": None, "error": "boom", "mirrored": None},
    )
    pid = _seed_project(str(tmp_path))
    with _client() as c:
        resp = c.post(f"/api/projects/{pid}/grd/genome/patterns", json={})
    assert resp.status_code == 400


def test_mine_patterns_unknown_project_returns_404(isolated_db, monkeypatch, tmp_path):
    called = {"hit": False}

    def fake_mine(*a, **k):
        called["hit"] = True
        return {"success": True, "data": {}, "error": None, "mirrored": None}

    monkeypatch.setattr(patterns_runner, "mine_patterns", fake_mine)
    with _client() as c:
        resp = c.post("/api/projects/proj-nope/grd/genome/patterns", json={})
    assert resp.status_code == 404
    assert called["hit"] is False


# ---------------------------------------------------------------------------
# genome/suggestions (mirrored-row GET)
# ---------------------------------------------------------------------------


def test_get_genome_suggestions_404_when_no_row(isolated_db, tmp_path):
    pid = _seed_project(str(tmp_path))
    with _client() as c:
        resp = c.get(f"/api/projects/{pid}/grd/genome/suggestions")
    assert resp.status_code == 404


def test_get_genome_suggestions_returns_mirrored_row(isolated_db, monkeypatch, tmp_path):
    # The handler does ``from app.db import get_genome_suggestions`` at call
    # time, so the patch target is the source module attribute.
    import app.db as db

    monkeypatch.setattr(db, "get_genome_suggestions", lambda pid: {"id": "gsg-1", "rows": 2})
    pid = _seed_project(str(tmp_path))
    with _client() as c:
        resp = c.get(f"/api/projects/{pid}/grd/genome/suggestions")
    assert resp.status_code == 200
    assert resp.json()["id"] == "gsg-1"


# ---------------------------------------------------------------------------
# genome/promote-suggestion (promote_suggestion)
# ---------------------------------------------------------------------------


def test_promote_suggestion_success_passes_slug(isolated_db, monkeypatch, tmp_path):
    calls = {}

    def fake_promote(cwd, slug):
        calls.update(cwd=cwd, slug=slug)
        return {"success": True, "data": {"promoted": slug}, "error": None}

    monkeypatch.setattr(patterns_runner, "promote_suggestion", fake_promote)
    pid = _seed_project(str(tmp_path))
    with _client() as c:
        resp = c.post(
            f"/api/projects/{pid}/grd/genome/promote-suggestion",
            json={"slug": "token-rate"},
        )
    assert resp.status_code == 201
    assert resp.json()["data"]["promoted"] == "token-rate"
    assert calls["cwd"] == str(tmp_path)
    assert calls["slug"] == "token-rate"


def test_promote_suggestion_no_slug_returns_400(isolated_db, monkeypatch, tmp_path):
    called = {"hit": False}

    def fake_promote(*a, **k):
        called["hit"] = True
        return {"success": True, "data": None, "error": None}

    monkeypatch.setattr(patterns_runner, "promote_suggestion", fake_promote)
    pid = _seed_project(str(tmp_path))
    with _client() as c:
        resp = c.post(f"/api/projects/{pid}/grd/genome/promote-suggestion", json={})
    assert resp.status_code == 400
    assert called["hit"] is False


def test_promote_suggestion_failure_returns_400(isolated_db, monkeypatch, tmp_path):
    monkeypatch.setattr(
        patterns_runner,
        "promote_suggestion",
        lambda cwd, slug: {"success": False, "data": None, "error": "no such slug"},
    )
    pid = _seed_project(str(tmp_path))
    with _client() as c:
        resp = c.post(
            f"/api/projects/{pid}/grd/genome/promote-suggestion",
            json={"slug": "token-rate"},
        )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# plan/{phase}/select (select_candidate)
# ---------------------------------------------------------------------------


def test_select_candidate_success_passes_flags_and_str_phase(isolated_db, monkeypatch, tmp_path):
    calls = {}

    def fake_select(project_id, cwd, phase, **kw):
        calls.update(project_id=project_id, cwd=cwd, phase=phase, kw=kw)
        return {"success": True, "data": {"winner": "a.md"}, "error": None, "mirrored": "psel-1"}

    monkeypatch.setattr(selection_runner, "select_candidate", fake_select)
    pid = _seed_project(str(tmp_path))
    with _client() as c:
        resp = c.post(
            f"/api/projects/{pid}/grd/plan/12/select",
            json={"dry_run": True, "force": True, "run_verification_commands": True},
        )
    assert resp.status_code == 201
    assert resp.json()["mirrored"] == "psel-1"
    assert calls["project_id"] == pid
    assert calls["cwd"] == str(tmp_path)
    assert calls["phase"] == "12"
    assert isinstance(calls["phase"], str)
    assert calls["kw"] == {"dry_run": True, "force": True, "run_verification_commands": True}


def test_select_candidate_failure_returns_400(isolated_db, monkeypatch, tmp_path):
    monkeypatch.setattr(
        selection_runner,
        "select_candidate",
        lambda *a, **k: {
            "success": False,
            "data": None,
            "error": "no candidates",
            "mirrored": None,
        },
    )
    pid = _seed_project(str(tmp_path))
    with _client() as c:
        resp = c.post(f"/api/projects/{pid}/grd/plan/12/select", json={})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# plan/{phase}/selection (mirrored-row GET)
# ---------------------------------------------------------------------------


def test_get_plan_selection_404_when_no_row(isolated_db, tmp_path):
    pid = _seed_project(str(tmp_path))
    with _client() as c:
        resp = c.get(f"/api/projects/{pid}/grd/plan/12/selection")
    assert resp.status_code == 404


def test_get_plan_selection_returns_mirrored_row(isolated_db, monkeypatch, tmp_path):
    import app.db as db

    monkeypatch.setattr(
        db, "get_plan_selection", lambda pid, phase: {"id": "psel-1", "phase": phase}
    )
    pid = _seed_project(str(tmp_path))
    with _client() as c:
        resp = c.get(f"/api/projects/{pid}/grd/plan/12/selection")
    assert resp.status_code == 200
    assert resp.json()["phase"] == "12"


# ---------------------------------------------------------------------------
# plan/tournament (plan_tournament)
# ---------------------------------------------------------------------------


def test_plan_tournament_success_passes_phase_and_candidates(isolated_db, monkeypatch, tmp_path):
    calls = {}

    def fake_tournament(cwd, phase, candidates):
        calls.update(cwd=cwd, phase=phase, candidates=candidates)
        return {"success": True, "data": {"ranked": ["a.md", "b.md"]}, "error": None}

    monkeypatch.setattr(selection_runner, "plan_tournament", fake_tournament)
    pid = _seed_project(str(tmp_path))
    with _client() as c:
        resp = c.post(
            f"/api/projects/{pid}/grd/plan/tournament",
            json={"phase": 12, "candidates": ["a.md", "b.md"]},
        )
    assert resp.status_code == 201
    assert resp.json()["data"]["ranked"] == ["a.md", "b.md"]
    assert calls["cwd"] == str(tmp_path)
    assert calls["phase"] == "12"
    assert isinstance(calls["phase"], str)
    assert calls["candidates"] == ["a.md", "b.md"]


def test_plan_tournament_missing_phase_returns_400(isolated_db, monkeypatch, tmp_path):
    called = {"hit": False}

    def fake_tournament(*a, **k):
        called["hit"] = True
        return {"success": True, "data": None, "error": None}

    monkeypatch.setattr(selection_runner, "plan_tournament", fake_tournament)
    pid = _seed_project(str(tmp_path))
    with _client() as c:
        resp = c.post(
            f"/api/projects/{pid}/grd/plan/tournament",
            json={"candidates": ["a.md"]},
        )
    assert resp.status_code == 400
    assert called["hit"] is False


def test_plan_tournament_empty_candidates_returns_400(isolated_db, monkeypatch, tmp_path):
    called = {"hit": False}

    def fake_tournament(*a, **k):
        called["hit"] = True
        return {"success": True, "data": None, "error": None}

    monkeypatch.setattr(selection_runner, "plan_tournament", fake_tournament)
    pid = _seed_project(str(tmp_path))
    with _client() as c:
        resp = c.post(
            f"/api/projects/{pid}/grd/plan/tournament",
            json={"phase": 12, "candidates": []},
        )
    assert resp.status_code == 400
    assert called["hit"] is False


def test_plan_tournament_failure_returns_400(isolated_db, monkeypatch, tmp_path):
    monkeypatch.setattr(
        selection_runner,
        "plan_tournament",
        lambda *a, **k: {"success": False, "data": None, "error": "bad candidate"},
    )
    pid = _seed_project(str(tmp_path))
    with _client() as c:
        resp = c.post(
            f"/api/projects/{pid}/grd/plan/tournament",
            json={"phase": 12, "candidates": ["a.md"]},
        )
    assert resp.status_code == 400


def test_plan_tournament_unknown_project_returns_404(isolated_db, monkeypatch, tmp_path):
    called = {"hit": False}

    def fake_tournament(*a, **k):
        called["hit"] = True
        return {"success": True, "data": None, "error": None}

    monkeypatch.setattr(selection_runner, "plan_tournament", fake_tournament)
    with _client() as c:
        resp = c.post(
            "/api/projects/proj-nope/grd/plan/tournament",
            json={"phase": 12, "candidates": ["a.md"]},
        )
    assert resp.status_code == 404
    assert called["hit"] is False
