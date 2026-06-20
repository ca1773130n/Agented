# backend/tests/test_goal_loop_pause_hold.py
import threading
import time

from app.services import goal_loop_runner as glr


class _State:
    def __init__(self):
        self.pause_event = threading.Event()
        self.stop_event = threading.Event()
        self.iteration = 1


def test_returns_immediately_when_not_paused(monkeypatch):
    monkeypatch.setattr(glr.ProjectSessionManager, "_broadcast", lambda *a, **k: None)
    glr._wait_if_paused(_State(), "s")  # no hang


def test_blocks_until_resumed_then_returns(monkeypatch):
    monkeypatch.setattr(glr, "_PAUSE_POLL_SECONDS", 0.01)
    monkeypatch.setattr(glr.ProjectSessionManager, "_broadcast", lambda *a, **k: None)
    st = _State()
    st.pause_event.set()
    t = threading.Thread(target=lambda: glr._wait_if_paused(st, "s"))
    t.start()
    time.sleep(0.05)
    assert t.is_alive()  # still held
    st.pause_event.clear()
    t.join(timeout=2)
    assert not t.is_alive()


def test_breaks_out_on_stop(monkeypatch):
    monkeypatch.setattr(glr, "_PAUSE_POLL_SECONDS", 0.01)
    monkeypatch.setattr(glr.ProjectSessionManager, "_broadcast", lambda *a, **k: None)
    st = _State()
    st.pause_event.set()
    t = threading.Thread(target=lambda: glr._wait_if_paused(st, "s"))
    t.start()
    time.sleep(0.05)
    st.stop_event.set()
    t.join(timeout=2)
    assert not t.is_alive()
