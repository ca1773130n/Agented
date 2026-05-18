"""Tests for ``goal_loop_runner``.

Covers: continue-prompt synthesis, cap enforcement (iteration +
wall-time), stale-check sanity layer, and the runner-state
snapshot. Uses a fake PSM (`subscribe_raw` / `send_input` /
`_broadcast` / `stop_session`) so no real subprocesses spawn.
"""

from __future__ import annotations

import json
import threading
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
    # v0.7.87 — Ouroboros is default; the continue prompt asks
    # for hypothesis markers instead of the legacy
    # "Address the gap and continue." tail. The presence of the
    # markers is what the agent uses to score itself next turn.
    assert "**Hypothesis:**" in p
    assert "**Predicted outcome:**" in p
    # No iteration counter — spec calls this out explicitly.
    assert "iteration" not in p.lower()
    assert "iter" not in p.lower()


def test_continue_prompt_stable_across_calls():
    a = goal_loop_runner._continue_prompt("g", "r")
    b = goal_loop_runner._continue_prompt("g", "r")
    assert a == b


def test_initial_prompt_includes_goal_and_start_verb():
    """Codex blocker #1: the runner sends an initial kickoff prompt
    before entering the polling loop, otherwise claude has nothing
    to respond to. The wording should make the start verb obvious
    so the model doesn't treat it as a status update.
    """
    p = goal_loop_runner._initial_prompt("ship X")
    assert "Goal: ship X" in p
    assert "Start working toward the goal" in p
    # Should NOT carry a 'Last check' line — there is no prior turn.
    assert "Last check" not in p


# -----------------------------------------------------------------
# Runner integration with a fake PSM
# -----------------------------------------------------------------


class _FakePSM:
    """Minimal stand-in for ``ProjectSessionManager`` exposing
    only the surface ``GoalLoopRunner`` consumes.

    By default ``send_input`` only records the call. Tests that
    want auto-echo (the fake PSM responds to each prompt with a
    new turn_done) can set ``auto_echo = True`` — this is the
    "drive the loop without per-iteration test pushes" mode.
    Without it the runner sends its initial / continue prompts
    and then idles on ``queue.get`` until the test pushes more
    events or stops the runner.
    """

    def __init__(self):
        self.queue: Queue = Queue()
        self.sent_inputs: list[str] = []
        self.broadcasts: list[tuple[str, str, dict]] = []
        self.stopped: list[str] = []
        self.auto_echo = False
        self.auto_echo_counter = 0

    def subscribe_raw(self, session_id: str) -> Queue:
        return self.queue

    def unsubscribe_raw(self, session_id: str, queue: Queue) -> None:
        pass

    def send_input(self, session_id: str, payload: str) -> bool:
        self.sent_inputs.append(payload)
        if self.auto_echo:
            self.auto_echo_counter += 1
            self.queue.put(
                ("turn_done", {"text": f"echo turn {self.auto_echo_counter}"})
            )
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
    yield psm
    # v0.7.74 — kill any runner threads this test left behind so
    # they don't leak into the next test (their DB writes would
    # hit the real DB after the per-test monkeypatch unwinds,
    # causing spurious "no such table" crashes elsewhere).
    with goal_loop_runner._runners_lock:
        live_ids = list(goal_loop_runner._runners.keys())
    for sid in live_ids:
        goal_loop_runner.stop_runner(sid)
        try:
            psm.queue.put(("__end__", {}))
        except Exception:
            pass
    # Give the threads up to 1s to exit cleanly.
    deadline = __import__("time").monotonic() + 1.0
    while __import__("time").monotonic() < deadline:
        with goal_loop_runner._runners_lock:
            if not goal_loop_runner._runners:
                break
        __import__("time").sleep(0.05)


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
    # v0.7.74 — the runner sends the initial kickoff prompt before
    # it ever sees a turn_done, so exactly ONE input is written.
    # No continue prompt because the first verdict was 'met'.
    assert len(fake_psm.sent_inputs) == 1
    initial = json.loads(fake_psm.sent_inputs[0])
    assert "Goal: do thing" in initial["message"]["content"][0]["text"]
    assert "Start working toward the goal" in initial["message"]["content"][0]["text"]


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
    # Enable auto-echo so each continue prompt triggers the next
    # turn_done; without it the runner would idle after the
    # initial prompt waiting for events.
    fake_psm.auto_echo = True
    goal_loop_runner.start_runner(
        "psess-cap",
        {"goal": "g", "max_iterations": 3, "max_wall_seconds": 60},
        cwd=None,
    )
    assert _drive(_RunnerStateLookup("psess-cap"))
    # Stopped due to iteration cap.
    assert fake_psm.stopped == ["psess-cap"]
    end_event = [
        b for b in fake_psm.broadcasts if b[1] == "goal_loop_ended"
    ]
    assert end_event and end_event[0][2]["reason"] == "iteration_cap"
    # Sends: initial kickoff + continue after iter 1 + continue
    # after iter 2 = 3 writes. Iter 3 hits the cap so no further
    # continue.
    assert len(fake_psm.sent_inputs) == 3
    initial = json.loads(fake_psm.sent_inputs[0])
    assert "Start working toward the goal" in initial["message"]["content"][0]["text"]
    second = json.loads(fake_psm.sent_inputs[1])
    # v0.7.87 — Ouroboros is the default continue shape; the
    # legacy "Address the gap and continue." tail was removed.
    assert "**Hypothesis:**" in second["message"]["content"][0]["text"]


def test_runner_opt_out_uses_legacy_prompts_and_skips_ouroboros_machinery(
    fake_psm, stub_iteration_db, monkeypatch
):
    """v0.7.87 (codex WARN F) — explicit ``ouroboros: false`` in
    the config must restore the legacy plain-continue shape AND
    skip every Ouroboros side effect end-to-end:

      * Initial + continue prompts do NOT include the hypothesis
        markers (regression-test against the default flip).
      * ``_extract_hypothesis`` is not called → no per-iteration
        hypothesis row data.
      * Dead-end recording is gated off (no
        ``add_goal_loop_dead_end`` calls).
      * Convergence termination cannot fire because
        ``recent_iteration_verdicts`` is gated by ``ouroboros`` too.

    Confirms the opt-out is a real escape hatch end-to-end, not
    just at the prompt-helper layer.
    """
    # Judge always returns met=False with a fake binary verdict so
    # the runner enters the continue branch (where the prompt
    # shape divergence lives).
    monkeypatch.setattr(
        goal_loop_runner.GoalJudgeService,
        "judge",
        classmethod(
            lambda cls, goal, text, **kw: JudgeVerdict(
                met=False, source="llm", reason="not yet"
            )
        ),
    )
    # Spy on the Ouroboros side-effect helpers; opt-out must not
    # call them.
    extract_calls: list = []
    monkeypatch.setattr(
        goal_loop_runner,
        "_extract_hypothesis",
        lambda text: (extract_calls.append(text) or (None, None)),
    )
    dead_end_calls: list = []
    monkeypatch.setattr(
        goal_loop_runner,
        "add_goal_loop_dead_end",
        lambda **kw: dead_end_calls.append(kw),
    )
    convergence_calls: list = []
    monkeypatch.setattr(
        goal_loop_runner,
        "recent_iteration_verdicts",
        lambda session_id, limit=3: (
            convergence_calls.append((session_id, limit)) or []
        ),
    )

    fake_psm.auto_echo = True
    goal_loop_runner.start_runner(
        "psess-optout",
        {
            "goal": "g",
            "max_iterations": 3,
            "max_wall_seconds": 60,
            # The explicit opt-out we're regression-testing.
            "ouroboros": False,
        },
        cwd=None,
    )
    assert _drive(_RunnerStateLookup("psess-optout"))
    assert fake_psm.stopped == ["psess-optout"]

    # Prompts: legacy shape, no hypothesis markers.
    initial = json.loads(fake_psm.sent_inputs[0])
    initial_text = initial["message"]["content"][0]["text"]
    assert "Make progress this turn" in initial_text
    assert "Hypothesis" not in initial_text
    second = json.loads(fake_psm.sent_inputs[1])
    second_text = second["message"]["content"][0]["text"]
    assert "Address the gap and continue." in second_text
    assert "Hypothesis" not in second_text

    # No Ouroboros side-effects fired.
    assert extract_calls == [], "opt-out must not call _extract_hypothesis"
    assert dead_end_calls == [], "opt-out must not record dead-ends"
    assert convergence_calls == [], "opt-out must not check convergence"

    # The completed iteration rows must NOT carry an
    # ouroboros_verdict (the binary-mode judge returns None there).
    for _row_id, kwargs in stub_iteration_db["completes"]:
        assert kwargs.get("hypothesis") is None
        assert kwargs.get("predicted_outcome") is None
        assert kwargs.get("ouroboros_verdict") is None


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
    fake_psm.auto_echo = True
    goal_loop_runner.start_runner(
        "psess-audit",
        {"goal": "g", "max_iterations": 2, "max_wall_seconds": 60},
        cwd=None,
    )
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
    fake_psm.auto_echo = True
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


def test_runner_sends_initial_prompt_before_first_turn(
    fake_psm, stub_iteration_db, monkeypatch
):
    """Codex blocker #1 regression test. Without the initial
    kickoff send, the runner would block forever waiting for a
    turn_done that never arrives because claude has nothing to
    respond to.
    """
    # Block the judge so we can observe the runner's first action.
    judge_calls = {"n": 0}

    def slow_judge(cls, *a, **kw):
        judge_calls["n"] += 1
        time.sleep(10)  # long enough that the test finishes first
        return JudgeVerdict(met=False, source="llm", reason="x")

    monkeypatch.setattr(
        goal_loop_runner.GoalJudgeService, "judge", classmethod(slow_judge)
    )
    goal_loop_runner.start_runner(
        "psess-init",
        {"goal": "the goal", "max_iterations": 5, "max_wall_seconds": 60},
        cwd=None,
    )
    # Give the runner thread a beat to start + send the initial.
    deadline = time.time() + 2
    while time.time() < deadline and not fake_psm.sent_inputs:
        time.sleep(0.05)
    assert len(fake_psm.sent_inputs) == 1
    payload = json.loads(fake_psm.sent_inputs[0])
    assert payload["type"] == "user"
    text = payload["message"]["content"][0]["text"]
    assert "Goal: the goal" in text
    assert "Start working" in text
    # Cleanup (fixture's finalizer also covers this, but explicit
    # stop here lets the slow judge return immediately).
    goal_loop_runner.stop_runner("psess-init")
    fake_psm.queue.put(("__end__", {}))


def test_runner_stop_mid_iteration_avoids_misleading_audit(
    fake_psm, stub_iteration_db, monkeypatch
):
    """Codex blocker #4: when the operator stops while the judge
    is running, the runner must NOT broadcast a
    ``goal_iteration_completed`` with the now-stale verdict. The
    iteration row is still finalized (no orphan ``pending``) but
    flagged ``stopped`` so the audit is faithful.
    """
    judge_returned = threading.Event()

    def slow_judge(cls, goal, text, **kw):
        # Wait briefly so the test can set the stop event during
        # the judge call.
        time.sleep(0.3)
        judge_returned.set()
        return JudgeVerdict(met=True, source="llm", reason="would have been met")

    monkeypatch.setattr(
        goal_loop_runner.GoalJudgeService, "judge", classmethod(slow_judge)
    )
    goal_loop_runner.start_runner(
        "psess-mid",
        {"goal": "g", "max_iterations": 5, "max_wall_seconds": 60},
        cwd=None,
    )
    # Trigger iteration 1.
    fake_psm.queue.put(("turn_done", {"text": "turn"}))
    # While judge is running, signal stop.
    time.sleep(0.1)
    goal_loop_runner.stop_runner("psess-mid")
    assert judge_returned.wait(timeout=2)
    fake_psm.queue.put(("__end__", {}))
    assert _drive(_RunnerStateLookup("psess-mid"))

    # The COMPLETED broadcast must NOT include this iteration —
    # only iteration_started should have fired.
    completed_events = [
        b for b in fake_psm.broadcasts if b[1] == "goal_iteration_completed"
    ]
    assert completed_events == []
    # The audit row is finalized with judge_source='stopped' so
    # an operator inspecting the trail sees the truth.
    assert len(stub_iteration_db["completes"]) == 1
    finalized = stub_iteration_db["completes"][0][1]
    assert finalized["judge_source"] == "stopped"
    assert "operator stopped" in (finalized["judge_reason"] or "")


class _RunnerStateLookup:
    """Sentinel that ``_drive`` uses to find the state by id. The
    runner removes the session from ``_runners`` on cleanup, so
    we look up by id rather than holding a state ref that won't be
    invalidated when the dict entry disappears.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
