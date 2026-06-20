# backend/tests/test_goal_loop_human_gate.py
import threading, time
from app.services import goal_loop_runner as glr


class _State:
    def __init__(self):
        self.stop_event = threading.Event()
        self.gate_decision = None
        self.awaiting_human = False
        self.iteration = 2


def test_await_gate_returns_decision(monkeypatch):
    monkeypatch.setattr(glr, "_PAUSE_POLL_SECONDS", 0.01)
    monkeypatch.setattr(glr.ProjectSessionManager, "_broadcast", lambda *a, **k: None)
    st = _State()
    out = {}
    t = threading.Thread(target=lambda: out.update(r=glr._await_gate(st, "s", 2, "every 2", max_wall_seconds=999)))
    t.start(); time.sleep(0.05)
    assert st.awaiting_human is True
    st.gate_decision = ("modify", "add a test")
    t.join(timeout=2)
    assert out["r"] == ("modify", "add a test")
    assert st.awaiting_human is False


def test_await_gate_times_out_to_abort(monkeypatch):
    monkeypatch.setattr(glr, "_PAUSE_POLL_SECONDS", 0.01)
    monkeypatch.setattr(glr.ProjectSessionManager, "_broadcast", lambda *a, **k: None)
    st = _State()
    decision, _ = glr._await_gate(st, "s", 2, "x", max_wall_seconds=0)  # immediate timeout
    assert decision == "abort"


def test_gate_due_helper():
    from app.models.loop_spec import LoopGate
    assert glr._gate_due(LoopGate(mode="every_n", n=3), iteration_no=3) is True
    assert glr._gate_due(LoopGate(mode="every_n", n=3), iteration_no=4) is False
    assert glr._gate_due(None, iteration_no=3) is False
