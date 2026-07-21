"""The Skill-Sleep round runs in the BACKGROUND so a UI trigger never blocks a
request thread on a multi-minute (up to 600s codex) round. start_round_async
returns immediately with a job_id; the verdict lands via get_round_job."""

import threading
import time

import pytest

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


def test_finished_jobs_registry_is_bounded(monkeypatch):
    monkeypatch.setattr(sss, "_ROUND_JOBS_MAX_TERMINAL", 5)
    monkeypatch.setattr(
        sss.SkillSleepGate,
        "run_skill_sleep_round",
        staticmethod(lambda *a, **k: {"status": "no_candidate"}),
    )
    ids = [sss.start_round_async("p", f"s{i}") for i in range(20)]
    for jid in ids:
        _wait(jid)
    with sss._ROUND_JOBS_LOCK:
        assert len(sss._ROUND_JOBS) <= 5  # oldest FINISHED evicted, no unbounded growth


def test_running_job_is_never_evicted(monkeypatch):
    # Regression (codex High): a still-running job must not be evicted by the
    # retention cap — else its status 404s mid-run and its verdict is dropped.
    monkeypatch.setattr(sss, "_ROUND_JOBS_MAX_TERMINAL", 2)
    monkeypatch.setattr(sss, "_MAX_CONCURRENT_ROUNDS", 50)
    release = threading.Event()
    monkeypatch.setattr(
        sss.SkillSleepGate,
        "run_skill_sleep_round",
        staticmethod(lambda *a, **k: (release.wait(3.0), {"status": "no_candidate"})[1]),
    )
    live = [sss.start_round_async("p", f"live{i}") for i in range(3)]  # 3 running, cap is 2 finished
    # all three are still running (blocked on the event) → all observable
    for jid in live:
        job = sss.get_round_job(jid)
        assert job is not None and job["status"] == "running"
    release.set()
    for jid in live:
        _wait(jid)


def test_terminal_cap_holds_after_concurrent_burst_completes(monkeypatch):
    # Regression (codex): prune ran only on start, so a burst of concurrent rounds
    # finishing could leave cap + (concurrency-1) terminal jobs. Prune-on-completion
    # must keep the finished count at the cap even after they all finish at once.
    monkeypatch.setattr(sss, "_ROUND_JOBS_MAX_TERMINAL", 3)
    monkeypatch.setattr(sss, "_MAX_CONCURRENT_ROUNDS", 5)
    # 3 already-finished jobs
    monkeypatch.setattr(
        sss.SkillSleepGate, "run_skill_sleep_round",
        staticmethod(lambda *a, **k: {"status": "no_candidate"}),
    )
    for i in range(3):
        _wait(sss.start_round_async("p", f"done{i}"))
    # now 5 concurrent rounds, all blocked, then released together
    release = threading.Event()
    monkeypatch.setattr(
        sss.SkillSleepGate, "run_skill_sleep_round",
        staticmethod(lambda *a, **k: (release.wait(3.0), {"status": "no_candidate"})[1]),
    )
    burst = [sss.start_round_async("p", f"burst{i}") for i in range(5)]
    release.set()
    for jid in burst:
        _wait(jid)
    with sss._ROUND_JOBS_LOCK:
        assert len(sss._ROUND_JOBS) <= 3  # pruned on completion, not 3+5


def test_concurrency_cap_raises_round_busy(monkeypatch):
    monkeypatch.setattr(sss, "_MAX_CONCURRENT_ROUNDS", 2)
    release = threading.Event()
    monkeypatch.setattr(
        sss.SkillSleepGate,
        "run_skill_sleep_round",
        staticmethod(lambda *a, **k: (release.wait(3.0), {"status": "no_candidate"})[1]),
    )
    sss.start_round_async("p", "a")
    sss.start_round_async("p", "b")
    with pytest.raises(sss.RoundBusyError):
        sss.start_round_async("p", "c")  # 2 already running → busy
    release.set()
