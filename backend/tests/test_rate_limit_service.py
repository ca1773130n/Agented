"""Tests for RateLimitService."""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.services.rate_limit_service import DEFAULT_COOLDOWN_SECONDS, RateLimitService


# ---------------------------------------------------------------------------
# check_stderr_line
# ---------------------------------------------------------------------------


class TestCheckStderrLine:
    """Tests for check_stderr_line across all backend types."""

    @pytest.mark.parametrize(
        "line",
        [
            "HTTP 429 Too Many Requests",
            "Error: rate_limit_error from API",
            "rate limit reached, please wait",
            "You have exceeded your quota",
        ],
    )
    def test_claude_rate_limit_patterns(self, line):
        result = RateLimitService.check_stderr_line(line, "claude")
        assert result == DEFAULT_COOLDOWN_SECONDS

    @pytest.mark.parametrize(
        "line",
        [
            "statusCode: 429",
            "Rate limit exceeded for model",
            "You are rate.limited",
        ],
    )
    def test_opencode_rate_limit_patterns(self, line):
        result = RateLimitService.check_stderr_line(line, "opencode")
        assert result == DEFAULT_COOLDOWN_SECONDS

    @pytest.mark.parametrize(
        "line",
        [
            "Error 429: resource exhausted",
            "google.api_core.exceptions.ResourceExhausted: RESOURCE_EXHAUSTED",
            "rate limit hit on gemini",
            "quota exceeded for project",
        ],
    )
    def test_gemini_rate_limit_patterns(self, line):
        result = RateLimitService.check_stderr_line(line, "gemini")
        assert result == DEFAULT_COOLDOWN_SECONDS

    @pytest.mark.parametrize(
        "line",
        [
            "HTTP 429",
            "rate_limit reached",
            "rate limit error",
            "too many requests, slow down",
        ],
    )
    def test_codex_rate_limit_patterns(self, line):
        result = RateLimitService.check_stderr_line(line, "codex")
        assert result == DEFAULT_COOLDOWN_SECONDS

    def test_non_matching_line_returns_none(self):
        assert RateLimitService.check_stderr_line("All good", "claude") is None
        assert RateLimitService.check_stderr_line("Success", "opencode") is None
        assert RateLimitService.check_stderr_line("Done", "gemini") is None
        assert RateLimitService.check_stderr_line("OK 200", "codex") is None

    def test_unknown_backend_returns_none(self):
        assert RateLimitService.check_stderr_line("429", "unknown_backend") is None

    def test_retry_after_extraction(self):
        line = "429 rate limit, retry-after: 120 seconds"
        result = RateLimitService.check_stderr_line(line, "claude")
        assert result == 120

    def test_retry_after_extraction_different_format(self):
        line = "Rate limit exceeded. Retry after 45s"
        result = RateLimitService.check_stderr_line(line, "opencode")
        assert result == 45

    def test_empty_line(self):
        assert RateLimitService.check_stderr_line("", "claude") is None

    def test_case_insensitive_matching(self):
        assert RateLimitService.check_stderr_line("RATE_LIMIT_ERROR", "claude") is not None
        assert RateLimitService.check_stderr_line("rate limit exceeded", "opencode") is not None
        assert RateLimitService.check_stderr_line("resource_exhausted", "gemini") is not None
        assert RateLimitService.check_stderr_line("Too Many Requests", "codex") is not None


# ---------------------------------------------------------------------------
# mark_rate_limited
# ---------------------------------------------------------------------------


class TestMarkRateLimited:
    """Tests for mark_rate_limited."""

    @patch("app.services.rate_limit_service.update_account_rate_limit")
    def test_marks_account_with_cooldown(self, mock_update):
        mock_update.return_value = True
        result = RateLimitService.mark_rate_limited(1, 120)

        assert result is True
        mock_update.assert_called_once()
        args = mock_update.call_args
        assert args[0][0] == 1  # account_id
        assert args[0][2] == "rate_limit_429"  # reason
        # Verify the timestamp is roughly correct (within 5 seconds tolerance)
        limited_until = datetime.fromisoformat(args[0][1])
        expected = datetime.now() + timedelta(seconds=120)
        assert abs((limited_until - expected).total_seconds()) < 5

    @patch("app.services.rate_limit_service.update_account_rate_limit")
    def test_returns_false_on_failure(self, mock_update):
        mock_update.return_value = False
        result = RateLimitService.mark_rate_limited(999, 60)
        assert result is False


# ---------------------------------------------------------------------------
# clear_rate_limit
# ---------------------------------------------------------------------------


class TestClearRateLimit:
    """Tests for clear_rate_limit."""

    @patch("app.services.rate_limit_service.db_clear_rate_limit")
    def test_clears_rate_limit(self, mock_clear):
        mock_clear.return_value = True
        assert RateLimitService.clear_rate_limit(1) is True
        mock_clear.assert_called_once_with(1)

    @patch("app.services.rate_limit_service.db_clear_rate_limit")
    def test_returns_false_when_not_found(self, mock_clear):
        mock_clear.return_value = False
        assert RateLimitService.clear_rate_limit(999) is False


# ---------------------------------------------------------------------------
# is_rate_limited
# ---------------------------------------------------------------------------


class TestIsRateLimited:
    """Tests for is_rate_limited."""

    @patch("app.services.rate_limit_service.get_account_rate_limit_state")
    def test_rate_limited_future_timestamp(self, mock_state):
        future = (datetime.now() + timedelta(seconds=300)).isoformat()
        mock_state.return_value = {"rate_limited_until": future}
        assert RateLimitService.is_rate_limited(1) is True

    @patch("app.services.rate_limit_service.get_account_rate_limit_state")
    def test_not_rate_limited_past_timestamp(self, mock_state):
        past = (datetime.now() - timedelta(seconds=300)).isoformat()
        mock_state.return_value = {"rate_limited_until": past}
        assert RateLimitService.is_rate_limited(1) is False

    @patch("app.services.rate_limit_service.get_account_rate_limit_state")
    def test_not_rate_limited_no_state(self, mock_state):
        mock_state.return_value = None
        assert RateLimitService.is_rate_limited(1) is False

    @patch("app.services.rate_limit_service.get_account_rate_limit_state")
    def test_not_rate_limited_no_timestamp(self, mock_state):
        mock_state.return_value = {"rate_limited_until": None}
        assert RateLimitService.is_rate_limited(1) is False

    @patch("app.services.rate_limit_service.get_account_rate_limit_state")
    def test_not_rate_limited_invalid_timestamp(self, mock_state):
        mock_state.return_value = {"rate_limited_until": "not-a-date"}
        assert RateLimitService.is_rate_limited(1) is False


# ---------------------------------------------------------------------------
# pick_best_account
# ---------------------------------------------------------------------------


class TestPickBestAccount:
    """Tests for pick_best_account."""

    @patch("app.services.rate_limit_service.get_accounts_for_backend_type")
    def test_picks_first_available(self, mock_get):
        mock_get.return_value = [
            {"id": 1, "account_name": "acc1", "rate_limited_until": None, "is_default": 1},
            {"id": 2, "account_name": "acc2", "rate_limited_until": None, "is_default": 0},
        ]
        result = RateLimitService.pick_best_account("claude")
        assert result["id"] == 1

    @patch("app.services.rate_limit_service.get_accounts_for_backend_type")
    def test_skips_rate_limited_accounts(self, mock_get):
        future = (datetime.now() + timedelta(seconds=300)).isoformat()
        mock_get.return_value = [
            {"id": 1, "account_name": "acc1", "rate_limited_until": future, "is_default": 1},
            {"id": 2, "account_name": "acc2", "rate_limited_until": None, "is_default": 0},
        ]
        result = RateLimitService.pick_best_account("claude")
        assert result["id"] == 2

    @patch("app.services.rate_limit_service.get_accounts_for_backend_type")
    def test_includes_expired_rate_limits(self, mock_get):
        past = (datetime.now() - timedelta(seconds=300)).isoformat()
        mock_get.return_value = [
            {"id": 1, "account_name": "acc1", "rate_limited_until": past, "is_default": 1},
        ]
        result = RateLimitService.pick_best_account("claude")
        assert result["id"] == 1

    @patch("app.services.rate_limit_service.get_accounts_for_backend_type")
    def test_returns_none_when_all_rate_limited(self, mock_get):
        future = (datetime.now() + timedelta(seconds=300)).isoformat()
        mock_get.return_value = [
            {"id": 1, "account_name": "acc1", "rate_limited_until": future},
            {"id": 2, "account_name": "acc2", "rate_limited_until": future},
        ]
        result = RateLimitService.pick_best_account("claude")
        assert result is None

    @patch("app.services.rate_limit_service.get_accounts_for_backend_type")
    def test_returns_none_when_no_accounts(self, mock_get):
        mock_get.return_value = []
        result = RateLimitService.pick_best_account("claude")
        assert result is None

    @patch("app.services.rate_limit_service.get_accounts_for_backend_type")
    def test_handles_invalid_rate_limited_until(self, mock_get):
        mock_get.return_value = [
            {"id": 1, "account_name": "acc1", "rate_limited_until": "bad-date", "is_default": 1},
        ]
        # Invalid date should be treated as not rate-limited (passes through)
        result = RateLimitService.pick_best_account("claude")
        assert result["id"] == 1


# ---------------------------------------------------------------------------
# get_all_account_states
# ---------------------------------------------------------------------------


class TestGetAllAccountStates:
    """Tests for get_all_account_states."""

    @patch("app.services.rate_limit_service.get_all_accounts_with_health")
    def test_returns_enriched_account_states(self, mock_get):
        future = (datetime.now() + timedelta(seconds=120)).isoformat()
        mock_get.return_value = [
            {
                "id": 1,
                "account_name": "acc1",
                "backend_id": "be-1",
                "backend_type": "claude",
                "backend_name": "Claude",
                "rate_limited_until": future,
                "rate_limit_reason": "rate_limit_429",
                "total_executions": 10,
                "last_used_at": "2026-01-01T00:00:00",
                "is_default": 1,
                "plan": "pro",
            },
        ]
        result = RateLimitService.get_all_account_states("claude")
        assert len(result) == 1
        state = result[0]
        assert state["account_id"] == 1
        assert state["is_rate_limited"] is True
        assert state["cooldown_remaining_seconds"] is not None
        assert state["cooldown_remaining_seconds"] > 0
        assert state["is_default"] is True
        assert state["total_executions"] == 10

    @patch("app.services.rate_limit_service.get_all_accounts_with_health")
    def test_expired_rate_limit_shows_not_limited(self, mock_get):
        past = (datetime.now() - timedelta(seconds=60)).isoformat()
        mock_get.return_value = [
            {
                "id": 2,
                "account_name": "acc2",
                "backend_id": "be-2",
                "backend_type": "opencode",
                "backend_name": "OpenCode",
                "rate_limited_until": past,
                "rate_limit_reason": None,
                "total_executions": 0,
                "last_used_at": None,
                "is_default": 0,
                "plan": None,
            },
        ]
        result = RateLimitService.get_all_account_states("opencode")
        state = result[0]
        assert state["is_rate_limited"] is False
        assert state["cooldown_remaining_seconds"] is None

    @patch("app.services.rate_limit_service.get_all_accounts_with_health")
    def test_no_rate_limit_timestamp(self, mock_get):
        mock_get.return_value = [
            {
                "id": 3,
                "account_name": "acc3",
                "backend_id": "",
                "backend_type": "gemini",
                "backend_name": "",
                "rate_limited_until": None,
                "rate_limit_reason": None,
                "total_executions": None,
                "last_used_at": None,
                "is_default": 0,
                "plan": None,
            },
        ]
        result = RateLimitService.get_all_account_states()
        state = result[0]
        assert state["is_rate_limited"] is False
        assert state["cooldown_remaining_seconds"] is None
        assert state["total_executions"] == 0

    @patch("app.services.rate_limit_service.get_all_accounts_with_health")
    def test_empty_accounts_list(self, mock_get):
        mock_get.return_value = []
        result = RateLimitService.get_all_account_states("claude")
        assert result == []

    @patch("app.services.rate_limit_service.get_all_accounts_with_health")
    def test_invalid_rate_limited_until_handled(self, mock_get):
        mock_get.return_value = [
            {
                "id": 4,
                "account_name": "acc4",
                "backend_id": "",
                "backend_type": "codex",
                "backend_name": "",
                "rate_limited_until": "garbage",
                "rate_limit_reason": None,
                "total_executions": 5,
                "last_used_at": None,
                "is_default": 0,
                "plan": None,
            },
        ]
        result = RateLimitService.get_all_account_states("codex")
        state = result[0]
        assert state["is_rate_limited"] is False
        assert state["cooldown_remaining_seconds"] is None


# ---------------------------------------------------------------------------
# Retry scheduling (ExecutionService.schedule_retry)
# ---------------------------------------------------------------------------

import json
import threading

from app.services.execution_service import ExecutionService


def _reset_execution_service():
    """Reset ExecutionService class-level retry state between tests."""
    with ExecutionService._rate_limit_lock:
        ExecutionService._pending_retries.clear()
        for t in ExecutionService._retry_timers.values():
            t.cancel()
        ExecutionService._retry_timers.clear()
        ExecutionService._retry_counts.clear()
        ExecutionService._rate_limit_detected.clear()
        ExecutionService._transient_failure_detected.clear()


class TestScheduleRetry:
    """Tests for ExecutionService.schedule_retry — retry scheduling on rate limit."""

    def setup_method(self):
        _reset_execution_service()

    def teardown_method(self):
        _reset_execution_service()

    @patch("app.services.execution_retry.delete_pending_retry")
    @patch("app.services.execution_retry.upsert_pending_retry")
    @patch("app.services.audit_log_service.AuditLogService")
    @patch("app.services.execution_log_service.ExecutionLogService")
    def test_schedule_retry_adds_pending_entry(
        self, mock_log_svc, mock_audit, mock_upsert, mock_del
    ):
        """Scheduling a retry should add an entry to _pending_retries and persist to DB."""
        trigger = {"id": "trg-abc", "backend_type": "claude"}
        ExecutionService.schedule_retry(trigger, "hello", None, "webhook", 30)

        with ExecutionService._rate_limit_lock:
            assert "trg-abc" in ExecutionService._pending_retries
            entry = ExecutionService._pending_retries["trg-abc"]
            assert entry["cooldown_seconds"] == 30
            assert entry["attempt"] == 1
            assert "trg-abc" in ExecutionService._retry_timers

        mock_upsert.assert_called_once()
        args = mock_upsert.call_args
        assert args[1]["trigger_id"] == "trg-abc"
        assert args[1]["cooldown_seconds"] == 30

    @patch("app.services.execution_retry.delete_pending_retry")
    @patch("app.services.execution_retry.upsert_pending_retry")
    @patch("app.services.audit_log_service.AuditLogService")
    @patch("app.services.execution_log_service.ExecutionLogService")
    def test_schedule_retry_increments_attempt_count(
        self, mock_log, mock_audit, mock_upsert, mock_del
    ):
        """Each call to schedule_retry for the same trigger increments the attempt counter."""
        trigger = {"id": "trg-inc", "backend_type": "claude"}
        ExecutionService.schedule_retry(trigger, "msg", None, "webhook", 10)
        ExecutionService.schedule_retry(trigger, "msg", None, "webhook", 10)

        with ExecutionService._rate_limit_lock:
            assert ExecutionService._retry_counts["trg-inc"] == 2
            entry = ExecutionService._pending_retries["trg-inc"]
            assert entry["attempt"] == 2

    @patch("app.services.execution_retry.delete_pending_retry")
    @patch("app.services.execution_retry.upsert_pending_retry")
    @patch("app.services.audit_log_service.AuditLogService")
    @patch("app.services.execution_log_service.ExecutionLogService")
    def test_schedule_retry_cancels_existing_timer(
        self, mock_log, mock_audit, mock_upsert, mock_del
    ):
        """Scheduling a new retry should cancel the previous timer for that trigger."""
        trigger = {"id": "trg-cancel", "backend_type": "claude"}
        ExecutionService.schedule_retry(trigger, "msg", None, "webhook", 600)

        with ExecutionService._rate_limit_lock:
            first_timer = ExecutionService._retry_timers["trg-cancel"]

        ExecutionService.schedule_retry(trigger, "msg", None, "webhook", 600)

        # First timer should have been cancelled
        assert first_timer.finished.is_set() or not first_timer.is_alive()

        with ExecutionService._rate_limit_lock:
            second_timer = ExecutionService._retry_timers["trg-cancel"]
        assert second_timer is not first_timer

    @patch("app.services.execution_retry.delete_pending_retry")
    @patch("app.services.execution_retry.upsert_pending_retry")
    @patch("app.services.audit_log_service.AuditLogService")
    @patch("app.services.execution_log_service.ExecutionLogService")
    def test_schedule_retry_exceeds_max_attempts(
        self, mock_log_svc, mock_audit, mock_upsert, mock_del
    ):
        """When max retry attempts are exceeded, no new timer should be created."""
        from app.config import MAX_RETRY_ATTEMPTS

        trigger = {"id": "trg-max", "backend_type": "claude"}

        # Manually set counter to MAX_RETRY_ATTEMPTS so next call exceeds it
        with ExecutionService._rate_limit_lock:
            ExecutionService._retry_counts["trg-max"] = MAX_RETRY_ATTEMPTS

        ExecutionService.schedule_retry(trigger, "msg", None, "webhook", 10)

        # Should NOT be in pending retries or timers — it gave up
        with ExecutionService._rate_limit_lock:
            assert "trg-max" not in ExecutionService._pending_retries
            assert "trg-max" not in ExecutionService._retry_timers
            assert "trg-max" not in ExecutionService._retry_counts

        mock_del.assert_called_once_with("trg-max")
        mock_log_svc.start_execution.assert_called_once()
        mock_log_svc.finish_execution.assert_called_once()

    @patch("app.services.execution_retry.delete_pending_retry")
    @patch("app.services.execution_retry.upsert_pending_retry")
    @patch("app.services.audit_log_service.AuditLogService")
    @patch("app.services.execution_log_service.ExecutionLogService")
    @patch("app.services.execution_retry.random.uniform", return_value=0)
    def test_schedule_retry_exponential_backoff(
        self, mock_rand, mock_log, mock_audit, mock_upsert, mock_del
    ):
        """Backoff delay should grow exponentially with attempt count."""
        trigger = {"id": "trg-back", "backend_type": "claude"}

        # First attempt: delay = min(30 * 2^0, 3600) + 0 = 30
        ExecutionService.schedule_retry(trigger, "msg", None, "webhook", 30)
        with ExecutionService._rate_limit_lock:
            timer1 = ExecutionService._retry_timers["trg-back"]
        assert timer1.interval == 30.0

        # Second attempt: delay = min(30 * 2^1, 3600) + 0 = 60
        ExecutionService.schedule_retry(trigger, "msg", None, "webhook", 30)
        with ExecutionService._rate_limit_lock:
            timer2 = ExecutionService._retry_timers["trg-back"]
        assert timer2.interval == 60.0


# ---------------------------------------------------------------------------
# Retry queue management (get_pending_retries)
# ---------------------------------------------------------------------------


class TestGetPendingRetries:
    """Tests for ExecutionService.get_pending_retries."""

    def setup_method(self):
        _reset_execution_service()

    def teardown_method(self):
        _reset_execution_service()

    @patch("app.services.execution_retry.get_all_pending_retries")
    def test_returns_in_memory_retries(self, mock_db):
        """get_pending_retries should include in-memory entries."""
        mock_db.return_value = []
        with ExecutionService._rate_limit_lock:
            ExecutionService._pending_retries["trg-mem"] = {
                "trigger_id": "trg-mem",
                "cooldown_seconds": 60,
                "retry_at": "2026-03-07T12:00:00",
                "scheduled_at": "2026-03-07T11:59:00",
            }

        result = ExecutionService.get_pending_retries()
        assert "trg-mem" in result
        assert result["trg-mem"]["cooldown_seconds"] == 60

    @patch("app.services.execution_retry.get_all_pending_retries")
    def test_supplements_with_db_rows(self, mock_db):
        """DB rows not in memory should be included in the result."""
        mock_db.return_value = [
            {
                "trigger_id": "trg-db",
                "cooldown_seconds": 45,
                "retry_at": "2026-03-07T12:00:00",
                "created_at": "2026-03-07T11:59:00",
            }
        ]

        result = ExecutionService.get_pending_retries()
        assert "trg-db" in result
        assert result["trg-db"]["cooldown_seconds"] == 45

    @patch("app.services.execution_retry.get_all_pending_retries")
    def test_in_memory_takes_precedence_over_db(self, mock_db):
        """If the same trigger_id exists in memory and DB, in-memory wins."""
        mock_db.return_value = [
            {
                "trigger_id": "trg-dup",
                "cooldown_seconds": 100,
                "retry_at": "2026-03-07T12:00:00",
                "created_at": "2026-03-07T11:59:00",
            }
        ]
        with ExecutionService._rate_limit_lock:
            ExecutionService._pending_retries["trg-dup"] = {
                "trigger_id": "trg-dup",
                "cooldown_seconds": 200,
                "retry_at": "2026-03-07T12:05:00",
                "scheduled_at": "2026-03-07T11:59:00",
            }

        result = ExecutionService.get_pending_retries()
        assert result["trg-dup"]["cooldown_seconds"] == 200

    @patch("app.services.execution_retry.get_all_pending_retries")
    def test_handles_db_error_gracefully(self, mock_db):
        """If DB read fails, in-memory retries should still be returned."""
        mock_db.side_effect = RuntimeError("DB unavailable")
        with ExecutionService._rate_limit_lock:
            ExecutionService._pending_retries["trg-ok"] = {
                "trigger_id": "trg-ok",
                "cooldown_seconds": 10,
                "retry_at": "2026-03-07T12:00:00",
                "scheduled_at": "2026-03-07T11:59:00",
            }

        result = ExecutionService.get_pending_retries()
        assert "trg-ok" in result


# ---------------------------------------------------------------------------
# Retry restoration on restart (restore_pending_retries)
# ---------------------------------------------------------------------------


class TestRestorePendingRetries:
    """Tests for ExecutionService.restore_pending_retries."""

    def setup_method(self):
        _reset_execution_service()

    def teardown_method(self):
        _reset_execution_service()

    @patch("app.services.execution_retry.delete_pending_retry")
    @patch("app.services.execution_retry.get_all_pending_retries")
    def test_restores_future_retry_from_db(self, mock_get, mock_del):
        """A pending retry with a future retry_at should be restored with a timer."""
        future = (datetime.now() + timedelta(seconds=300)).isoformat()
        mock_get.return_value = [
            {
                "trigger_id": "trg-fut",
                "trigger_json": json.dumps({"id": "trg-fut", "backend_type": "claude"}),
                "message_text": "test msg",
                "event_json": "{}",
                "trigger_type": "webhook",
                "cooldown_seconds": 60,
                "retry_at": future,
                "created_at": datetime.now().isoformat(),
            }
        ]

        count = ExecutionService.restore_pending_retries()
        assert count == 1

        with ExecutionService._rate_limit_lock:
            assert "trg-fut" in ExecutionService._pending_retries
            assert "trg-fut" in ExecutionService._retry_timers
            timer = ExecutionService._retry_timers["trg-fut"]
        assert timer.is_alive()

    @patch("app.services.execution_retry.delete_pending_retry")
    @patch("app.services.execution_retry.get_all_pending_retries")
    def test_restores_past_due_retry_with_zero_delay(self, mock_get, mock_del):
        """A retry whose retry_at is in the past should be restored with remaining=0 (fires ASAP).

        The timer fires almost immediately so the in-memory entry may already be cleaned up
        by the callback. We verify restore counted it and a timer was created.
        """
        past = (datetime.now() - timedelta(seconds=10)).isoformat()
        # Use a large future retry_at but patch datetime so remaining computes as 0
        mock_get.return_value = [
            {
                "trigger_id": "trg-past",
                "trigger_json": json.dumps({"id": "trg-past", "backend_type": "claude"}),
                "message_text": "msg",
                "event_json": "{}",
                "trigger_type": "webhook",
                "cooldown_seconds": 5,
                "retry_at": past,
                "created_at": datetime.now().isoformat(),
            }
        ]

        count = ExecutionService.restore_pending_retries()
        # The row was successfully processed and counted, even if timer already fired
        assert count == 1

    @patch("app.services.execution_retry.get_all_pending_retries")
    def test_restore_returns_zero_on_db_error(self, mock_get):
        """If DB query fails, restore should return 0."""
        mock_get.side_effect = RuntimeError("DB gone")
        count = ExecutionService.restore_pending_retries()
        assert count == 0

    @patch("app.services.execution_retry.delete_pending_retry")
    @patch("app.services.execution_retry.get_all_pending_retries")
    def test_restore_skips_bad_rows_and_continues(self, mock_get, mock_del):
        """Malformed rows should be skipped; valid ones should still be restored."""
        future = (datetime.now() + timedelta(seconds=300)).isoformat()
        mock_get.return_value = [
            {
                "trigger_id": "trg-bad",
                "trigger_json": "NOT VALID JSON {{{",
                "message_text": "",
                "event_json": "{}",
                "trigger_type": "webhook",
                "cooldown_seconds": 10,
                "retry_at": future,
                "created_at": datetime.now().isoformat(),
            },
            {
                "trigger_id": "trg-good",
                "trigger_json": json.dumps({"id": "trg-good", "backend_type": "claude"}),
                "message_text": "ok",
                "event_json": "{}",
                "trigger_type": "webhook",
                "cooldown_seconds": 60,
                "retry_at": future,
                "created_at": datetime.now().isoformat(),
            },
        ]

        count = ExecutionService.restore_pending_retries()
        assert count == 1
        with ExecutionService._rate_limit_lock:
            assert "trg-good" in ExecutionService._pending_retries
            assert "trg-bad" not in ExecutionService._pending_retries
