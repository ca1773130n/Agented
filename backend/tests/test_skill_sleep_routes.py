"""Phase 4 route tests — /admin/projects/{id}/skills/{name}/sleep + adopt + list.

Mirrors test_litestar_projects.py (create_test_client + provide_caller). The
SkillSleepGate service is unit-tested elsewhere; these verify wiring, access,
validation, and response shape — the gate itself is monkeypatched so no LLM
calls fire.
"""

from __future__ import annotations

import json
import time

from litestar.testing import create_test_client

from app.db.rbac import create_user_role
from app_litestar.auth import provide_caller
from app_litestar.routes.health import health_router
from app_litestar.routes.projects import projects_router


def _client():
    return create_test_client(
        route_handlers=[health_router, projects_router],
        dependencies={"caller": provide_caller},
    )


def _make_project(c, key: str) -> str:
    create_user_role(key, "Admin", "admin")
    resp = c.post(
        "/admin/projects/",
        headers={"X-API-Key": key},
        json={"name": "SleepProj", "description": "x"},
    )
    assert resp.status_code == 201
    return resp.json()["project"]["id"]


def test_evaluate_requires_candidate_body(isolated_db):
    with _client() as c:
        pid = _make_project(c, "ss-key-1")
        resp = c.post(
            f"/admin/projects/{pid}/skills/deploy/sleep",
            headers={"X-API-Key": "ss-key-1"},
            json={},
        )
    assert resp.status_code == 400


def test_evaluate_returns_verdict(isolated_db, monkeypatch):
    from app.services import skill_sleep_service as svc

    monkeypatch.setattr(
        svc.SkillSleepGate,
        "evaluate_skill",
        staticmethod(
            lambda project_id, skill_name, **kw: {
                "run_id": 1,
                "status": "accepted",
                "accepted": True,
                "current_score": 0.4,
                "candidate_score": 0.8,
                "delta": 0.4,
                "question_count": 6,
                "reason": "ok",
            }
        ),
    )
    with _client() as c:
        pid = _make_project(c, "ss-key-2")
        resp = c.post(
            f"/admin/projects/{pid}/skills/deploy/sleep",
            headers={"X-API-Key": "ss-key-2"},
            json={"candidate_body": "new body", "n": 4, "seed": 2},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "accepted"
    assert body["accepted"] is True


def test_round_endpoint_runs(isolated_db, monkeypatch):
    from app.services import skill_sleep_service as svc

    monkeypatch.setattr(
        svc.SkillSleepGate,
        "run_skill_sleep_round",
        staticmethod(
            lambda project_id, skill_name, **kw: {
                "run_id": 5,
                "status": "no_candidate",
                "accepted": False,
                "reason": "reflect proposed no material change",
            }
        ),
    )
    # The endpoint is ASYNC: it dispatches and returns a job id, and the round's
    # own outcome is read back from the job. This test asserted the old
    # synchronous shape (`{"status": ...}` straight off the POST) and had been
    # failing with KeyError: 'status' ever since — filed as a known baseline
    # failure rather than read.
    with _client() as c:
        pid = _make_project(c, "ss-key-round")
        resp = c.post(
            f"/admin/projects/{pid}/skills/deploy/sleep/round",
            headers={"X-API-Key": "ss-key-round"},
            json={"n": 4, "seed": 1},
        )
        assert resp.status_code == 201
        job_id = resp.json()["job_id"]
        assert job_id

        # Poll through the ROUTE, not `get_round_job` directly. Reading the job
        # store in-process would prove the worker ran but not that
        # `GET .../sleep/round/{job_id}` works — break that handler or its path
        # and the test would still pass, which is the failure this whole file is
        # being fixed for.
        body = None
        for _ in range(200):
            poll = c.get(
                f"/admin/projects/{pid}/skills/deploy/sleep/round/{job_id}",
                headers={"X-API-Key": "ss-key-round"},
            )
            assert poll.status_code == 200, poll.text
            body = poll.json()
            if body.get("status") in ("done", "error"):
                break
            time.sleep(0.05)

    assert body is not None, "round job vanished"
    assert body["status"] == "done", body
    # Assert the exact field, not a substring of the whole JSON: the stubbed
    # round's verdict has to survive the trip through the job intact.
    assert body["verdict"]["status"] == "no_candidate", body


def test_adopt_404_for_foreign_run(isolated_db):
    from app.db import skill_sleep

    with _client() as c:
        pid = _make_project(c, "ss-key-3")
        # A run that belongs to a DIFFERENT project must 404 here.
        other = skill_sleep.create_run("proj-other", "deploy", skill_id=1)
        resp = c.post(
            f"/admin/projects/{pid}/skill-sleep/{other}/adopt",
            headers={"X-API-Key": "ss-key-3"},
        )
    assert resp.status_code == 404


def test_list_runs_scoped(isolated_db):
    from app.db import skill_sleep

    with _client() as c:
        pid = _make_project(c, "ss-key-4")
        skill_sleep.create_run(pid, "deploy", skill_id=1)
        skill_sleep.create_run("proj-elsewhere", "x", skill_id=2)
        resp = c.get(
            f"/admin/projects/{pid}/skill-sleep",
            headers={"X-API-Key": "ss-key-4"},
        )
    assert resp.status_code == 200
    runs = resp.json()["runs"]
    assert len(runs) == 1
    assert runs[0]["project_id"] == pid
