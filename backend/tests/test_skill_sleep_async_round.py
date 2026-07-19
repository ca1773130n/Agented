"""The Skill-Sleep round runs in the BACKGROUND so a UI trigger never blocks a
request thread on a multi-minute (up to 600s codex) round. start_round_async
returns immediately with a job_id; the verdict lands via get_round_job."""

import threading
import time

from app.services import skill_sleep_service as sss


def _wait(job_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = sss.get_round_job(job_id)
        if job and job["status"] != "running":
            return job
        time.sleep(0.01)
    return sss.get_round_job(job_id)


def test_start_round_async_returns_immediately_and_does_not_block(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def slow_round(project_id, skill_name, **opts):
        started.set()
        release.wait(2.0)  # simulate a long round
        return {"run_id": 1, "status": "accepted", "accepted": True, "delta": 0.1}

    monkeypatch.setattr(sss.SkillSleepGate, "run_skill_sleep_round", staticmethod(slow_round))

    t0 = time.monotonic()
    job_id = sss.start_round_async("proj-1", "skill-a", n=6)
    elapsed = time.monotonic() - t0

    # The trigger must return basically instantly (work is on a daemon thread),
    # not wait for the round — this is the whole point of the fix.
    assert elapsed < 0.5
    assert started.wait(1.0), "round work should have begun on the background thread"
    assert sss.get_round_job(job_id)["status"] == "running"

    release.set()
    job = _wait(job_id)
    assert job["status"] == "done"
    assert job["verdict"]["status"] == "accepted"


def test_round_job_captures_error_without_crashing(monkeypatch):
    def boom(project_id, skill_name, **opts):
        raise RuntimeError("reflect blew up")

    monkeypatch.setattr(sss.SkillSleepGate, "run_skill_sleep_round", staticmethod(boom))
    job = _wait(sss.start_round_async("p", "s"))
    assert job["status"] == "error"
    assert "reflect blew up" in job["error"]


def test_get_round_job_unknown_is_none():
    assert sss.get_round_job("ssround-doesnotexist") is None


def test_round_jobs_registry_is_bounded(monkeypatch):
    monkeypatch.setattr(sss, "_ROUND_JOBS_MAX", 5)
    monkeypatch.setattr(
        sss.SkillSleepGate,
        "run_skill_sleep_round",
        staticmethod(lambda *a, **k: {"status": "no_candidate"}),
    )
    ids = [sss.start_round_async("p", f"s{i}") for i in range(20)]
    for jid in ids:
        _wait(jid)
    with sss._ROUND_JOBS_LOCK:
        assert len(sss._ROUND_JOBS) <= 5  # oldest evicted, no unbounded growth
