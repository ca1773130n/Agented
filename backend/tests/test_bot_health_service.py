"""v0.7.0: bot health rollup service tests.

Bots are tracked in the `triggers` table (renamed from `bots` in the
v0.4 migration). The service externalises them as "bots" because that
is the operator-facing concept; internally it queries
`triggers` + `execution_logs.trigger_id`.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.database import get_connection
from app.services.bot_health_service import (
    DEGRADED_SUCCESS_THRESHOLD,
    LATENCY_ANOMALY_RATIO,
    compute_rollups,
)


def _now():
    return datetime.now(timezone.utc)


def _seed_bot(bot_id="bot-test", name="Test Bot"):
    """Insert a row into `triggers` (the table backing 'bots')."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO triggers (id, name, group_id, detection_keyword, "
            "prompt_template, backend_type, trigger_source, created_at) "
            "VALUES (?, ?, 0, '', '', 'claude', 'manual', ?)",
            (bot_id, name, _now().isoformat()),
        )
        conn.commit()


def _seed_execution(bot_id, status, started_at, duration_ms, error_message=None):
    with get_connection() as conn:
        eid = f"exec-{started_at.timestamp()}-{status}"
        finished_at = started_at + timedelta(milliseconds=duration_ms or 0)
        conn.execute(
            """INSERT INTO execution_logs
               (execution_id, trigger_id, trigger_type, started_at, finished_at,
                duration_ms, backend_type, status, error_message)
               VALUES (?, ?, 'manual', ?, ?, ?, 'claude', ?, ?)""",
            (
                eid,
                bot_id,
                started_at.isoformat(),
                finished_at.isoformat(),
                duration_ms,
                status,
                error_message,
            ),
        )
        conn.commit()


def _find(rollups, bot_id):
    """Return the rollup matching bot_id (helps when other seed rows exist)."""
    return next(r for r in rollups if r.bot_id == bot_id)


class TestComputeRollups:
    def test_no_executions_returns_no_recent_runs_status(self):
        _seed_bot()
        rollups = compute_rollups(window_days=7)
        r = _find(rollups, "bot-test")
        assert r.bot_id == "bot-test"
        assert r.success_count == 0
        assert r.fail_count == 0
        assert r.status_pill == "no_recent_runs"

    def test_all_success_marks_healthy(self):
        _seed_bot()
        now = _now()
        for i in range(10):
            _seed_execution("bot-test", "success", now - timedelta(hours=i), 1000)
        rollups = compute_rollups(window_days=7)
        r = _find(rollups, "bot-test")
        assert r.success_count == 10
        assert r.fail_count == 0
        assert r.status_pill == "healthy"

    def test_all_failures_recently_marks_down(self):
        _seed_bot()
        now = _now()
        for i in range(3):
            _seed_execution(
                "bot-test", "failed", now - timedelta(hours=i), 500, error_message="boom"
            )
        rollups = compute_rollups(window_days=7)
        r = _find(rollups, "bot-test")
        assert r.fail_count == 3
        assert r.success_count == 0
        assert r.status_pill == "down"
        assert r.last_failure_message == "boom"

    def test_below_threshold_marks_degraded(self):
        _seed_bot()
        now = _now()
        # 7 success / 3 fail = 70% < DEGRADED_SUCCESS_THRESHOLD (80%)
        for i in range(7):
            _seed_execution("bot-test", "success", now - timedelta(hours=i), 1000)
        for i in range(3):
            _seed_execution(
                "bot-test",
                "failed",
                now - timedelta(hours=i + 10),
                500,
                error_message="x",
            )
        rollups = compute_rollups(window_days=7)
        r = _find(rollups, "bot-test")
        assert r.status_pill == "degraded"

    def test_p95_anomaly_marks_degraded(self):
        _seed_bot()
        now = _now()
        # 19 fast (100ms), 1 slow (10000ms) — p95 anomaly
        for i in range(19):
            _seed_execution(
                "bot-test", "success", now - timedelta(minutes=i), 100
            )
        _seed_execution("bot-test", "success", now - timedelta(minutes=20), 10000)
        rollups = compute_rollups(window_days=7)
        r = _find(rollups, "bot-test")
        # success rate is 100% but latency anomaly should still flag
        assert r.status_pill == "degraded"

    def test_window_excludes_old_executions(self):
        _seed_bot()
        old = _now() - timedelta(days=30)
        _seed_execution("bot-test", "failed", old, 500, error_message="ancient")
        rollups = compute_rollups(window_days=7)
        r = _find(rollups, "bot-test")
        assert r.fail_count == 0
        assert r.status_pill == "no_recent_runs"

    def test_window_days_validation(self):
        with pytest.raises(ValueError):
            compute_rollups(window_days=0)
        with pytest.raises(ValueError):
            compute_rollups(window_days=91)

    def test_thresholds_are_constants(self):
        # Lock current tunings; if these change, callers need to know.
        assert DEGRADED_SUCCESS_THRESHOLD == 0.80
        assert LATENCY_ANOMALY_RATIO == 5.0

    def test_timeout_counts_as_failure(self):
        # Codex round-1 #1: timeout was previously dropped from both
        # buckets, leaving the bot looking like `no_recent_runs`.
        _seed_bot()
        now = _now()
        _seed_execution(
            "bot-test",
            "timeout",
            now - timedelta(minutes=5),
            30000,
            error_message="exceeded deadline",
        )
        rollups = compute_rollups(window_days=7)
        r = _find(rollups, "bot-test")
        assert r.fail_count == 1
        assert r.success_count == 0
        assert r.status_pill == "down"

    def test_cancelled_counts_as_failure(self):
        _seed_bot()
        now = _now()
        _seed_execution(
            "bot-test",
            "cancelled",
            now - timedelta(minutes=5),
            100,
            error_message="user aborted",
        )
        rollups = compute_rollups(window_days=7)
        r = _find(rollups, "bot-test")
        assert r.fail_count == 1
        assert r.success_count == 0
        assert r.status_pill == "down"

    def test_running_does_not_count(self):
        # Non-terminal states stay out of both buckets — a bot that is
        # only ever observed mid-flight should still read as having no
        # completed runs in the window.
        _seed_bot()
        now = _now()
        _seed_execution("bot-test", "running", now - timedelta(minutes=1), None)
        rollups = compute_rollups(window_days=7)
        r = _find(rollups, "bot-test")
        assert r.success_count == 0
        assert r.fail_count == 0
        assert r.status_pill == "no_recent_runs"
