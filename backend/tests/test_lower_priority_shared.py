"""Regression tests for the shared-file lower-priority hardening items."""


def test_email_throttle_trips_after_limit():
    import app_litestar.routes.auth as authmod

    authmod._email_attempts.clear()
    email = "throttle@test"
    # First _EMAIL_MAX_ATTEMPTS are allowed; the next trips.
    for _ in range(authmod._EMAIL_MAX_ATTEMPTS):
        assert authmod._email_throttled(email) is False
    assert authmod._email_throttled(email) is True
    # A different email is unaffected.
    assert authmod._email_throttled("other@test") is False


def test_webhook_delivery_dedup_and_repo_rate_limit():
    import app_litestar.routes.webhooks as wh

    wh._seen_delivery_keys.clear()
    wh._repo_last_event.clear()
    assert wh._is_duplicate_key("delivery:abc") is False
    assert wh._is_duplicate_key("delivery:abc") is True  # replay
    # Per-repo rate limit: first allowed, immediate second blocked.
    assert wh._repo_rate_limited("o/r") is False
    assert wh._repo_rate_limited("o/r") is True


def test_fetch_pr_diff_rejects_untrusted_host():
    from app.services.execution_runner import fetch_pr_diff

    # Non-github host must be refused (returns None without fetching).
    assert fetch_pr_diff({"pr_url": "https://evil.example.com/x/y/pull/1"}) is None
    # Non-https github also refused.
    assert fetch_pr_diff({"pr_url": "http://github.com/x/y/pull/1"}) is None


def test_global_concurrency_cap_configured():
    from app.services.execution_queue_service import ExecutionQueueService as Q

    assert Q._GLOBAL_CONCURRENCY_CAP >= 1


def test_team_tracker_sweeps_old_terminal_entries(monkeypatch):
    import app.services.team_execution_tracker as t

    T = t.TeamExecutionTracker
    with T._lock:
        T._executions.clear()
        # An old terminal entry that the (lost) cleanup Timer never removed.
        T._executions["old"] = {"status": "completed", "_ts": 0.0}
    # Registering a new execution sweeps stale terminal entries.
    T.register("new", "team-1", "solo", "manual")
    assert "old" not in T._executions
    assert "new" in T._executions


def test_worktree_rejects_traversal():
    import pytest

    from app.services.worktree_service import WorktreeService

    with pytest.raises(ValueError):
        WorktreeService.create_worktree(
            project_path="/tmp/x", worktree_name="../escape", branch_name="ok"
        )
    with pytest.raises(ValueError):
        WorktreeService.create_worktree(
            project_path="/tmp/x", worktree_name="ok", branch_name="--upload-pack=x"
        )
