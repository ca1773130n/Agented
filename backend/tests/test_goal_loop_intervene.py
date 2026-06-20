# backend/tests/test_goal_loop_intervene.py
from app.services.goal_loop_runner import _apply_pending_note


def test_prepends_note_and_clears():
    class S:
        pending_note = "use the cache"

    s = S()
    reason = _apply_pending_note(s, "tests still failing")
    assert reason.startswith("Operator note: use the cache")
    assert "tests still failing" in reason
    assert s.pending_note is None


def test_no_note_returns_reason_unchanged():
    class S:
        pending_note = None

    assert _apply_pending_note(S(), "x") == "x"
