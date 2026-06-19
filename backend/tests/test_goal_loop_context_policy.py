# backend/tests/test_goal_loop_context_policy.py
from app.services import goal_loop_runner as glr


def test_carry_uses_send_continue(monkeypatch):
    calls = {"continue": 0, "reset": 0}
    monkeypatch.setattr(
        glr, "_send_continue", lambda *a, **k: calls.__setitem__("continue", calls["continue"] + 1)
    )
    monkeypatch.setattr(
        glr,
        "_advance_iteration",
        lambda *a, **k: calls.__setitem__("reset", calls["reset"] + 1),
        raising=False,
    )
    glr._next_iteration(policy="carry", session_id="s", cwd="/tmp", goal="g")
    assert calls["continue"] == 1 and calls["reset"] == 0


def test_reset_spawns_fresh_session(monkeypatch):
    calls = {"continue": 0, "reset": 0}
    monkeypatch.setattr(
        glr, "_send_continue", lambda *a, **k: calls.__setitem__("continue", calls["continue"] + 1)
    )
    monkeypatch.setattr(
        glr, "_advance_iteration", lambda *a, **k: calls.__setitem__("reset", calls["reset"] + 1)
    )
    glr._next_iteration(policy="reset", session_id="s", cwd="/tmp", goal="g")
    assert calls["reset"] == 1 and calls["continue"] == 0
