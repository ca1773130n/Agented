"""Tests for ``goal_loop_runner``.

Covers: continue-prompt synthesis, cap enforcement (iteration +
wall-time), stale-check sanity layer, and the runner-state
snapshot. Uses a fake PSM (`subscribe_raw` / `send_input` /
`_broadcast` / `stop_session`) so no real subprocesses spawn.
"""

from __future__ import annotations

import json
import time
from queue import Queue

import pytest

from app.services import goal_loop_runner
from app.services.goal_judge_service import JudgeVerdict


# -----------------------------------------------------------------
# Continue-prompt synthesis (pure)
# -----------------------------------------------------------------


def test_continue_prompt_includes_goal_and_reason():
    p = goal_loop_runner._continue_prompt("ship feature X", "tests still fail")
    assert "Goal: ship feature X" in p
    assert "Last check: tests still fail" in p
    assert "Address the gap and continue." in p
    # No iteration counter — spec calls this out explicitly.
    assert "iteration" not in p.lower()
    assert "iter" not in p.lower()


def test_continue_prompt_stable_across_calls():
    a = goal_loop_runner._continue_prompt("g", "r")
    b = goal_loop_runner._continue_prompt("g", "r")
    assert a == b


# -----------------------------------------------------------------
# Runner integration with a fake PSM
# -----------------------------------------------------------------


class _FakePSM:
    """Minimal stand-in for ``ProjectSessionManager`` exposing
    only the surface ``GoalLoopRunner`` consumes.
    """

    def __init__(self):
        self.queue: Queue = Queue()
        self.sent_inputs: list[str] = []
        self.broadcasts: list[tuple[str, str, dict]] = []
        self.stopped: list[str] = []

    def subscribe_raw(self, session_id: str) -> Queue:
        return self.queue

    def unsubscribe_raw(self, session_id: str, queue: Queue) -> None:
        pass

    def send_input(self, session_id: str, payload: str) -> bool:
        self.sent_inputs.append(payload)
        # Echo a turn_done back so the runner can chain iterations.
        # The text is a marker we can inspect.
        self.queue.put(("turn_done", {"text": f"echo turn for {session_id}"}))
        return True

    def _broadcast(self, session_id: str, event_type: str, data: dict) -> None:
        self.broadcasts.append((session_id, event_type, data))

    def stop_session(self, session_id: str) -> bool:
        self.stopped.append(session_id)
        # Signal the queue end so the runner's drain loop exits.
        self.queue.put(("__end__", {"status": "stopped", "exit_code": 0}))
        return True


@pytest.fixture
def fake_psm(monkeypatch):
    psm = _FakePSM()
    monkeypatch.setattr(goal_loop_runner, "ProjectSessionManager", psm)
    return psm


@pytest.fixture
def stub_iteration_db(monkeypatch):
    """Stub the goal_loop_iterations DB writes so the test doesn't
    need a real DB. Captures calls for inspection.
    """
    calls = {"starts": [], "completes": []}

    def _start(session_id, iteration):
        calls["starts"].append((session_id, iteration))
        return 1

    def _complete(row_id, **kwargs):
        calls["completes"].append((row_id, kwargs))

    monkeypatch.setattr(
        goal_loop_runner, "record_goal_loop_iteration_start", _start
    )
    monkeypatch.setattr(
        goal_loop_runner, "record_goal_loop_iteration_complete", _complete
    )
    return calls


def _drive(state, max_wait_seconds: float = 2.0) -> bool:
    """Wait for the runner thread tied to ``state`` to terminate.

    The runner's ``_run`` calls ``_cleanup`` at the end which
    removes the session from ``_runners``, so absence is the
    termination signal.
    """
    deadline = time.time() + max_wait_seconds
    while time.time() < deadline:
        with goal_loop_runner._runners_lock:
            if state.session_id not in goal_loop_runner._runners:
                return True
        time.sleep(0.05)
    return False


def test_runner_stops_when_judge_says_met(fake_psm, stub_iteration_db, monkeypatch):
    monkeypatch.setattr(
        goal_loop_runner.GoalJudgeService,
        "judge",
        classmethod(
            lambda cls, goal, text, **kw: JudgeVerdict(
                met=True, source="llm", reason="done"
            )
        ),
    )
    goal_loop_runner.start_runner(
        "psess-met",
        {"goal": "do thing", "max_iterations": 20, "max_wall_seconds": 60},
        cwd=None,
    )
    # Push a single turn_done; runner judges met → stop.
    fake_psm.queue.put(("turn_done", {"text": "I did it."}))
    assert _drive(_RunnerStateLookup("psess-met"))
    assert fake_psm.stopped == ["psess-met"]
    assert ("psess-met", "goal_loop_ended", {"reason": "met", "detail": "done"}) in fake_psm.broadcasts
    # No continue prompt should have been written.
    assert fake_psm.sent_inputs == []


def test_runner_sends_continue_on_not_met_then_iteration_cap(
    fake_psm, stub_iteration_db, monkeypatch
):
    monkeypatch.setattr(
        goal_loop_runner.GoalJudgeService,
        "judge",
        classmethod(
            lambda cls, goal, text, **kw: JudgeVerdict(
                met=False, source="llm", reason="not yet"
            )
        ),
    )
    goal_loop_runner.start_runner(
        "psess-cap",
        {"goal": "g", "max_iterations": 3, "max_wall_seconds": 60},
        cwd=None,
    )
    # Kick the first turn; the fake PSM echoes each send_input as
    # another turn_done so the loop will iterate 3 times then hit
    # the cap.
    fake_psm.queue.put(("turn_done", {"text": "turn 1"}))
    assert _drive(_RunnerStateLookup("psess-cap"))
    # Stopped due to iteration cap.
    assert fake_psm.stopped == ["psess-cap"]
    end_event = [
        b for b in fake_psm.broadcasts if b[1] == "goal_loop_ended"
    ]
    assert end_event and end_event[0][2]["reason"] == "iteration_cap"
    # First two continue prompts were sent (after iters 1 and 2);
    # iter 3 hits the cap so no continue is synthesized.
    assert len(fake_psm.sent_inputs) == 2
    envelope = json.loads(fake_psm.sent_inputs[0])
    assert envelope["type"] == "user"
    assert "Address the gap and continue." in envelope["message"]["content"][0]["text"]


def test_runner_records_each_iteration(
    fake_psm, stub_iteration_db, monkeypatch
):
    monkeypatch.setattr(
        goal_loop_runner.GoalJudgeService,
        "judge",
        classmethod(
            lambda cls, goal, text, **kw: JudgeVerdict(
                met=False, source="llm", reason="no", tokens_in=10, tokens_out=4
            )
        ),
    )
    goal_loop_runner.start_runner(
        "psess-audit",
        {"goal": "g", "max_iterations": 2, "max_wall_seconds": 60},
        cwd=None,
    )
    fake_psm.queue.put(("turn_done", {"text": "turn"}))
    assert _drive(_RunnerStateLookup("psess-audit"))
    # Two iterations were recorded; each got a start + complete.
    assert len(stub_iteration_db["starts"]) == 2
    assert len(stub_iteration_db["completes"]) == 2
    first_complete = stub_iteration_db["completes"][0][1]
    assert first_complete["verdict"] == "not_met"
    assert first_complete["judge_source"] == "llm"
    assert first_complete["tokens_in"] == 10
    assert first_complete["tokens_out"] == 4


def test_runner_aborts_on_empty_goal(fake_psm, stub_iteration_db):
    goal_loop_runner.start_runner(
        "psess-empty", {"goal": "   ", "max_iterations": 5}, cwd=None
    )
    assert _drive(_RunnerStateLookup("psess-empty"))
    # Should have done nothing — no broadcasts, no inputs, no
    # iteration rows.
    assert fake_psm.broadcasts == []
    assert fake_psm.sent_inputs == []
    assert stub_iteration_db["starts"] == []


def test_runner_wall_time_cap(fake_psm, stub_iteration_db, monkeypatch):
    monkeypatch.setattr(
        goal_loop_runner.GoalJudgeService,
        "judge",
        classmethod(
            lambda cls, *a, **kw: JudgeVerdict(
                met=False, source="llm", reason="no"
            )
        ),
    )
    # Shrink the poll interval so the cap check fires quickly.
    monkeypatch.setattr(goal_loop_runner, "_QUEUE_POLL_SECONDS", 0.05)
    goal_loop_runner.start_runner(
        "psess-walltime",
        {"goal": "g", "max_iterations": 100, "max_wall_seconds": 1},
        cwd=None,
    )
    # Don't push any turn_done events; the cap check will fire on
    # poll-timeouts and eventually exceed max_wall_seconds=1.
    assert _drive(_RunnerStateLookup("psess-walltime"), max_wait_seconds=4)
    assert fake_psm.stopped == ["psess-walltime"]
    end = [b for b in fake_psm.broadcasts if b[1] == "goal_loop_ended"]
    assert end and end[0][2]["reason"] == "wall_time_cap"


def test_runner_stale_check_disagreement_event(
    fake_psm, stub_iteration_db, monkeypatch
):
    """When deterministic check has been ``not_met`` 5 times in a
    row and the LLM sanity layer says ``met``, the runner emits a
    ``goal_check_disagreement`` event and resets the streak.
    """
    deterministic_call = {"n": 0}

    def fake_judge(cls, goal, text, *, check_cmd=None, **kw):
        # Deterministic = check_cmd is set; LLM sanity layer = no check_cmd.
        if check_cmd:
            deterministic_call["n"] += 1
            return JudgeVerdict(
                met=False, source="deterministic", reason="exit 1"
            )
        return JudgeVerdict(met=True, source="llm", reason="actually fine")

    monkeypatch.setattr(
        goal_loop_runner.GoalJudgeService,
        "judge",
        classmethod(fake_judge),
    )
    goal_loop_runner.start_runner(
        "psess-stale",
        {
            "goal": "g",
            "check_cmd": "false",
            "max_iterations": 20,
            "max_wall_seconds": 60,
        },
        cwd=None,
    )
    # Feed enough turns to trip the streak.
    fake_psm.queue.put(("turn_done", {"text": "turn 1"}))
    # The runner's send_input mock echoes a new turn_done per
    # iteration, so 5 iterations happen automatically.
    # Wait until either the disagreement event fires or the cap.
    deadline = time.time() + 3
    while time.time() < deadline:
        disagreed = [b for b in fake_psm.broadcasts if b[1] == "goal_check_disagreement"]
        if disagreed:
            break
        time.sleep(0.05)
    else:
        # Stop the runner if it didn't trigger so the test fails clean.
        goal_loop_runner.stop_runner("psess-stale")
        fake_psm.queue.put(("__end__", {}))
        pytest.fail("expected goal_check_disagreement event was not emitted")

    # Cleanup — runner is still iterating; signal stop.
    goal_loop_runner.stop_runner("psess-stale")
    fake_psm.queue.put(("__end__", {}))
    assert _drive(_RunnerStateLookup("psess-stale"))


def test_get_runner_state_snapshot(fake_psm, stub_iteration_db, monkeypatch):
    # Don't auto-echo — the snapshot must be readable WHILE the
    # runner is alive and idle (queue empty, polling). The
    # default fake_psm.send_input would chase iterations so fast
    # the runner exits before we can call get_runner_state.
    monkeypatch.setattr(goal_loop_runner, "_QUEUE_POLL_SECONDS", 0.05)
    goal_loop_runner.start_runner(
        "psess-state",
        {"goal": "g", "max_iterations": 10, "max_wall_seconds": 60},
        cwd=None,
    )
    # Sleep briefly so the thread has actually started + entered
    # its drain loop.
    time.sleep(0.1)
    snap = goal_loop_runner.get_runner_state("psess-state")
    assert snap is not None
    assert snap["max_iterations"] == 10
    assert snap["iteration"] == 0  # No turn judged yet
    assert snap["max_wall_seconds"] == 60
    assert snap["elapsed_seconds"] >= 0
    # Cleanup — signal stop + flush the queue so the thread exits.
    goal_loop_runner.stop_runner("psess-state")
    fake_psm.queue.put(("__end__", {}))
    assert _drive(_RunnerStateLookup("psess-state"))


# -----------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------


class _RunnerStateLookup:
    """Sentinel that ``_drive`` uses to find the state by id. The
    runner removes the session from ``_runners`` on cleanup, so
    we look up by id rather than holding a state ref that won't be
    invalidated when the dict entry disappears.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
