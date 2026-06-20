"""Route tests for the GRD life-harness round endpoints + evolve deprecation."""

from litestar.testing import create_test_client

from app.db.connection import get_connection
from app.db.grd_harness_rounds import upsert_harness_round
from app_litestar.auth import provide_caller
from app_litestar.routes.grd_routes import grd_router


def _client():
    return create_test_client(
        route_handlers=[grd_router],
        dependencies={"caller": provide_caller},
    )


def _seed_project(path: str, pid: str = "proj-h") -> str:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, status, local_path) VALUES (?, 'H', 'active', ?)",
            (pid, path),
        )
        conn.commit()
    return pid


def test_harness_round_triggers_runner(isolated_db, monkeypatch, tmp_path):
    import app.services.grd_harness_round_runner as runner

    calls = {}
    monkeypatch.setattr(
        runner,
        "run_round",
        lambda project_id, cwd, **kw: calls.update(project_id=project_id, kw=kw) or True,
    )
    pid = _seed_project(str(tmp_path))
    with _client() as c:
        resp = c.post(f"/api/projects/{pid}/grd/harness/round", json={"auto": True})
    assert resp.status_code == 201
    assert resp.json()["status"] == "running"
    assert calls["project_id"] == pid
    assert calls["kw"]["auto"] is True


def test_harness_round_400_when_gd_missing(isolated_db, monkeypatch, tmp_path):
    import app.services.grd_harness_round_runner as runner

    monkeypatch.setattr(runner, "run_round", lambda *a, **k: False)
    pid = _seed_project(str(tmp_path))
    with _client() as c:
        resp = c.post(f"/api/projects/{pid}/grd/harness/round", json={})
    assert resp.status_code == 400


def test_list_and_get_harness_rounds(isolated_db, tmp_path):
    pid = _seed_project(str(tmp_path))
    upsert_harness_round(project_id=pid, round_id="r1", status="applied", summary="s")
    with _client() as c:
        lst = c.get(f"/api/projects/{pid}/grd/harness/rounds")
        one = c.get(f"/api/projects/{pid}/grd/harness/rounds/r1")
    assert lst.status_code == 200
    assert [r["round_id"] for r in lst.json()["rounds"]] == ["r1"]
    assert one.status_code == 200
    assert one.json()["status"] == "applied"


def test_revert_harness_round(isolated_db, monkeypatch, tmp_path):
    import app.services.grd_harness_round_runner as runner

    monkeypatch.setattr(
        runner,
        "revert_round",
        lambda cwd, rid: {"success": True, "output": "reverted", "error": None},
    )
    pid = _seed_project(str(tmp_path))
    with _client() as c:
        resp = c.post(f"/api/projects/{pid}/grd/harness/rounds/r1/revert")
    assert resp.status_code == 201
    assert resp.json()["success"] is True


def test_evolve_start_is_deprecated(isolated_db, tmp_path):
    pid = _seed_project(str(tmp_path))
    with _client() as c:
        resp = c.post(f"/api/projects/{pid}/grd/evolve/start", json={})
    assert resp.status_code == 201
    body = resp.json()
    assert body["deprecated"] is True
    assert "harness/round" in body["use"]
