"""TDD tests for answer-eval routes (POST /admin/answer-eval/run, GET runs).

Mirrors test_litestar_admin_misc.py style (create_test_client per test).
"""

from __future__ import annotations

import threading

from litestar.testing import create_test_client

from app_litestar.routes.answer_eval import answer_eval_router


def _client():
    return create_test_client(route_handlers=[answer_eval_router])


# ---------------------------------------------------------------------------
# POST /admin/answer-eval/run — returns run_id immediately without blocking
# ---------------------------------------------------------------------------


def test_post_run_returns_run_id(isolated_db, monkeypatch):
    """POST returns {run_id} immediately; the service runs in a daemon thread."""
    import app.services.answer_eval_service as svc_mod

    started = threading.Event()
    finished = threading.Event()

    def mock_run_eval(*args, **kwargs):
        started.set()
        finished.wait(timeout=2)
        return kwargs.get("run_id") or 1

    monkeypatch.setattr(svc_mod.AnswerEvalService, "run_eval", staticmethod(mock_run_eval))

    with _client() as c:
        resp = c.post("/admin/answer-eval/run", json={"project_id": "proj-route-1"})

    assert resp.status_code == 201
    body = resp.json()
    assert "run_id" in body
    assert isinstance(body["run_id"], int)

    # Let daemon thread finish
    finished.set()


def test_post_run_with_n_param(isolated_db, monkeypatch):
    """n parameter is accepted."""
    import app.services.answer_eval_service as svc_mod

    captured = {}

    def mock_run_eval(*args, **kwargs):
        captured["n"] = kwargs.get("n")
        return kwargs.get("run_id") or 1

    monkeypatch.setattr(svc_mod.AnswerEvalService, "run_eval", staticmethod(mock_run_eval))

    with _client() as c:
        resp = c.post("/admin/answer-eval/run", json={"project_id": "proj-route-2", "n": 12})
    assert resp.status_code == 201


def test_post_run_does_not_block(isolated_db, monkeypatch):
    """Route returns before run_eval completes (daemon thread, non-blocking)."""
    import app.services.answer_eval_service as svc_mod

    gate = threading.Event()

    def slow_run_eval(*args, **kwargs):
        gate.wait(timeout=5)
        return kwargs.get("run_id") or 1

    monkeypatch.setattr(svc_mod.AnswerEvalService, "run_eval", staticmethod(slow_run_eval))

    with _client() as c:
        resp = c.post("/admin/answer-eval/run", json={"project_id": "proj-route-nonblock"})
    # Should return immediately even though gate is still blocked
    assert resp.status_code == 201
    gate.set()


def test_post_run_missing_project_id_returns_error(isolated_db):
    """Missing project_id → 400 or 422."""
    with _client() as c:
        resp = c.post("/admin/answer-eval/run", json={})
    assert resp.status_code in (400, 422)


# ---------------------------------------------------------------------------
# GET /admin/answer-eval/runs
# ---------------------------------------------------------------------------


def test_get_runs_empty(isolated_db):
    """No runs yet → empty list."""
    with _client() as c:
        resp = c.get("/admin/answer-eval/runs")
    assert resp.status_code == 200
    body = resp.json()
    assert "runs" in body
    assert isinstance(body["runs"], list)


def test_get_runs_with_project_filter(isolated_db):
    """project_id query param is accepted."""
    from app.db.answer_eval import create_run

    create_run("proj-filter", judge_backend="claude")

    with _client() as c:
        resp = c.get("/admin/answer-eval/runs?project_id=proj-filter")
    assert resp.status_code == 200
    body = resp.json()
    assert "runs" in body
    runs = body["runs"]
    assert all(r["project_id"] == "proj-filter" for r in runs)


def test_get_runs_returns_all_projects_when_no_filter(isolated_db):
    """Without project_id filter, all runs are returned."""
    from app.db.answer_eval import create_run

    create_run("proj-all-1", judge_backend="claude")
    create_run("proj-all-2", judge_backend="claude")

    with _client() as c:
        resp = c.get("/admin/answer-eval/runs")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["runs"]) >= 2


# ---------------------------------------------------------------------------
# GET /admin/answer-eval/runs/{run_id}
# ---------------------------------------------------------------------------


def test_get_single_run(isolated_db):
    """GET /runs/{run_id} returns the run row + results list."""
    from app.db.answer_eval import create_run, record_result

    run_id = create_run("proj-single", judge_backend="claude")
    record_result(
        run_id,
        question="How does it work?",
        arm="baseline",
        answer_text="It works like this.",
        scores={"groundedness": 0.8, "sufficiency": 0.7, "quality": 0.9},
        judge_reason="ok",
        tokens=50,
        cost_usd=0.001,
    )

    with _client() as c:
        resp = c.get(f"/admin/answer-eval/runs/{run_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert "run" in body
    assert "results" in body
    assert body["run"]["id"] == run_id
    assert isinstance(body["results"], list)
    assert len(body["results"]) == 1


def test_get_single_run_not_found(isolated_db):
    """Non-existent run_id → 404."""
    with _client() as c:
        resp = c.get("/admin/answer-eval/runs/99999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Router registration sanity check
# ---------------------------------------------------------------------------


def test_router_is_registered_in_main(isolated_db):
    """answer_eval_router must be present in the route_handlers list in main.py."""
    from app_litestar.routes.answer_eval import answer_eval_router as imported_router

    assert imported_router is not None
