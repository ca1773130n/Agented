# backend/tests/test_goal_loop_token_cap.py
from app.services.goal_loop_runner import _token_cap_exceeded


def test_token_cap_off_when_zero():
    assert _token_cap_exceeded(total=10_000, max_tokens=0) is False


def test_token_cap_triggers_at_or_above_limit():
    assert _token_cap_exceeded(total=500_000, max_tokens=500_000) is True
    assert _token_cap_exceeded(total=499_999, max_tokens=500_000) is False
