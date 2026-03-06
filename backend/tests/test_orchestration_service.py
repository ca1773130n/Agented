"""Tests for OrchestrationService — fallback chain execution and account rotation."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.orchestration_service import (
    ExecutionResult,
    ExecutionStatus,
    OrchestrationService,
)


@pytest.fixture
def trigger():
    return {"id": "trig-test01", "name": "Test Trigger", "backend_type": "claude"}


class TestCheckBudget:
    def test_budget_allowed(self, isolated_db, trigger):
        with patch("app.services.orchestration_service.BudgetService") as mock_bs:
            mock_bs.check_budget.return_value = {"allowed": True, "reason": "within_budget"}
            result = OrchestrationService._check_budget(trigger)
            assert result is None

    def test_budget_blocked(self, isolated_db, trigger):
        with patch("app.services.orchestration_service.BudgetService") as mock_bs:
            mock_bs.check_budget.return_value = {
                "allowed": False,
                "reason": "hard_limit_reached",
                "current_spend": 50.0,
                "limit": {"hard_limit_usd": 50, "period": "monthly"},
            }
            result = OrchestrationService._check_budget(trigger)
            assert result is not None
            assert "hard_limit_reached" in result

    def test_budget_soft_limit_warning(self, isolated_db, trigger):
        with patch("app.services.orchestration_service.BudgetService") as mock_bs:
            mock_bs.check_budget.return_value = {
                "allowed": True,
                "reason": "soft_limit_warning",
                "current_spend": 40.0,
                "remaining_usd": 10.0,
            }
            result = OrchestrationService._check_budget(trigger)
            assert result is None  # Allowed despite warning


class TestSelectAccount:
    def test_auto_select_account(self, isolated_db):
        chain_entry = {"backend_type": "claude"}
        mock_account = {"id": 1, "account_name": "default"}

        with patch("app.services.orchestration_service.RateLimitService") as mock_rls:
            mock_rls.pick_best_account.return_value = mock_account
            result = OrchestrationService._select_account(chain_entry)
            assert result == mock_account

    def test_auto_select_no_accounts(self, isolated_db):
        chain_entry = {"backend_type": "claude"}

        with patch("app.services.orchestration_service.RateLimitService") as mock_rls:
            mock_rls.pick_best_account.return_value = None
            result = OrchestrationService._select_account(chain_entry)
            assert result is None

    def test_specific_account_rate_limited(self, isolated_db):
        chain_entry = {"backend_type": "claude", "account_id": 42}

        with (
            patch("app.services.orchestration_service.RateLimitService") as mock_rls,
            patch("app.services.orchestration_service.OrchestrationService._select_account.__wrapped__", side_effect=None) if False else patch(
                "app.services.agent_scheduler_service.AgentSchedulerService.check_eligibility",
                return_value={"eligible": True},
            ),
        ):
            mock_rls.is_rate_limited.return_value = True
            result = OrchestrationService._select_account(chain_entry)
            assert result is None


class TestBuildAccountEnv:
    def test_empty_account(self):
        env = OrchestrationService._build_account_env({})
        assert env == {}

    def test_api_key_env(self, monkeypatch):
        monkeypatch.setenv("MY_API_KEY", "sk-test-123")
        account = {"api_key_env": "MY_API_KEY"}
        env = OrchestrationService._build_account_env(account)
        assert env["ANTHROPIC_API_KEY"] == "sk-test-123"

    def test_api_key_env_missing(self, monkeypatch):
        monkeypatch.delenv("NONEXISTENT_KEY", raising=False)
        account = {"api_key_env": "NONEXISTENT_KEY"}
        env = OrchestrationService._build_account_env(account)
        assert "ANTHROPIC_API_KEY" not in env

    def test_config_path_claude(self):
        account = {"config_path": "/home/user/.config/claude", "backend_type": "claude"}
        env = OrchestrationService._build_account_env(account)
        assert env["CLAUDE_CONFIG_DIR"] == "/home/user/.config/claude"

    def test_config_path_gemini(self):
        account = {"config_path": "/home/user/.gemini", "backend_type": "gemini"}
        env = OrchestrationService._build_account_env(account)
        assert env["GEMINI_CLI_HOME"] == "/home/user/.gemini"

    def test_config_path_unknown_backend(self):
        account = {"config_path": "/some/path", "backend_type": "unknown"}
        env = OrchestrationService._build_account_env(account)
        assert "CLAUDE_CONFIG_DIR" not in env
        assert "GEMINI_CLI_HOME" not in env


class TestExecuteWithFallback:
    def test_no_chain_direct_execution(self, isolated_db, trigger):
        with (
            patch("app.services.orchestration_service.get_fallback_chain", return_value=[]),
            patch(
                "app.services.execution_service.ExecutionService.run_trigger",
                return_value="exec-123",
            ),
        ):
            result = OrchestrationService.execute_with_fallback(trigger, "test message")
            assert result.status == ExecutionStatus.DISPATCHED
            assert result.execution_id == "exec-123"

    def test_no_chain_launch_failed(self, isolated_db, trigger):
        with (
            patch("app.services.orchestration_service.get_fallback_chain", return_value=[]),
            patch(
                "app.services.execution_service.ExecutionService.run_trigger",
                return_value=None,
            ),
        ):
            result = OrchestrationService.execute_with_fallback(trigger, "test message")
            assert result.status == ExecutionStatus.LAUNCH_FAILED

    def test_budget_blocked(self, isolated_db, trigger):
        chain = [{"backend_type": "claude", "account_id": None}]
        with (
            patch("app.services.orchestration_service.get_fallback_chain", return_value=chain),
            patch("app.services.orchestration_service.BudgetService") as mock_bs,
        ):
            mock_bs.check_budget.return_value = {
                "allowed": False,
                "reason": "hard_limit_reached",
                "current_spend": 100.0,
                "limit": {"hard_limit_usd": 100, "period": "monthly"},
            }
            result = OrchestrationService.execute_with_fallback(trigger, "test message")
            assert result.status == ExecutionStatus.BUDGET_BLOCKED


class TestExecutionResult:
    def test_dispatched(self):
        r = ExecutionResult(status=ExecutionStatus.DISPATCHED, execution_id="exec-1")
        assert r.status == ExecutionStatus.DISPATCHED
        assert r.execution_id == "exec-1"

    def test_budget_blocked(self):
        r = ExecutionResult(status=ExecutionStatus.BUDGET_BLOCKED, detail="over budget")
        assert r.detail == "over budget"
        assert r.execution_id is None


class TestExecutionStatus:
    def test_enum_values(self):
        assert ExecutionStatus.DISPATCHED == "dispatched"
        assert ExecutionStatus.BUDGET_BLOCKED == "budget_blocked"
        assert ExecutionStatus.CHAIN_EXHAUSTED == "chain_exhausted"
        assert ExecutionStatus.LAUNCH_FAILED == "launch_failed"
        assert ExecutionStatus.CIRCUIT_BREAKER_OPEN == "circuit_breaker_open"


class TestValidateFallbackChainEntries:
    def test_valid_entries(self, isolated_db):
        from app.database import get_connection

        # Create a backend for testing
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO ai_backends (id, name, type) VALUES (?, ?, ?)",
                ("be-test01", "Test Backend", "claude"),
            )

        class Entry:
            backend_type = "claude"
            account_id = None

        result = OrchestrationService.validate_fallback_chain_entries([Entry()])
        assert result is None  # No error

    def test_invalid_backend_type(self, isolated_db):
        class Entry:
            backend_type = "nonexistent"
            account_id = None

        result = OrchestrationService.validate_fallback_chain_entries([Entry()])
        assert result is not None
        assert "nonexistent" in result
