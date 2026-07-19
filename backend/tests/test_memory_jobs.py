"""Persistent async memory-query jobs: history + read-later + restart-survival."""

import time

from app.db import memory_jobs
from app.services import tesserae_integration as ti


def test_create_finish_get_list(isolated_db):
    memory_jobs.create_job("mq-a", "doctor", label="health", params={"refresh": True})
    memory_jobs.create_job("mq-b", "graph_query", label="bfs", params={"q": "bfs"})
    memory_jobs.finish_job("mq-a", status="completed", result={"ok": True, "n": 3})
    memory_jobs.finish_job("mq-b", status="failed", error="boom", result={"ok": False, "reason": "boom"})

    a = memory_jobs.get_job("mq-a")
    assert a["status"] == "completed" and a["result"] == {"ok": True, "n": 3}
    assert a["params"] == {"refresh": True}

    b = memory_jobs.get_job("mq-b")
    assert b["status"] == "failed" and b["error"] == "boom"

    # list is newest-first and omits the result blob (history view)
    jobs = memory_jobs.list_jobs()
    assert [j["job_id"] for j in jobs] == ["mq-b", "mq-a"]
    assert all("result" not in j for j in jobs)

    # kind filter
    assert [j["job_id"] for j in memory_jobs.list_jobs(kind="doctor")] == ["mq-a"]


def test_run_memory_job_persists_and_polls(isolated_db):
    jid = ti.run_memory_job(
        "graph_query", lambda: {"ok": True, "hits": [1, 2, 3]}, label="q", params={"q": "x"}
    )
    # poll until done (in-memory fast path)
    for _ in range(50):
        job = ti.get_op_job(jid)
        if job and job["status"] != "running":
            break
        time.sleep(0.02)
    assert job["op"] == "graph_query"
    assert job["status"] == "completed"
    assert job["result"] == {"ok": True, "hits": [1, 2, 3]}
    # persisted to history
    assert jid in {j["job_id"] for j in memory_jobs.list_jobs()}


def test_get_op_job_db_fallback_survives_restart(isolated_db):
    jid = ti.run_memory_job("doctor", lambda: {"ok": True, "checks": 1})
    for _ in range(50):
        if ti.get_op_job(jid)["status"] != "running":
            break
        time.sleep(0.02)
    # simulate a process restart: the in-memory cache is gone
    ti._op_jobs.clear()
    job = ti.get_op_job(jid)
    assert job is not None, "must read the persisted job after restart"
    assert job["status"] == "completed" and job["result"] == {"ok": True, "checks": 1}


def test_failing_job_recorded_failed(isolated_db):
    def _boom():
        raise RuntimeError("kaboom")

    jid = ti.run_memory_job("lint", _boom)
    for _ in range(50):
        job = ti.get_op_job(jid)
        if job["status"] != "running":
            break
        time.sleep(0.02)
    assert job["status"] == "failed"
    assert job["result"]["ok"] is False and "kaboom" in job["result"]["reason"]
