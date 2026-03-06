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
