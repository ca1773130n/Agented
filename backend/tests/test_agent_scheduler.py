"""Tests for AgentSchedulerService: DB helpers, eligibility, evaluation, hysteresis,
execution lifecycle hooks, most-conservative ETA, API endpoints, and integration tests
for the scheduler-monitoring-orchestration pipeline."""

import threading
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_scheduler_tables(conn):
    """Ensure agent_sessions and settings tables exist for testing."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            state TEXT NOT NULL DEFAULT 'queued',
            stop_reason TEXT,
            stop_window_type TEXT,
            stop_eta_minutes REAL,
            resume_estimate TEXT,
            consecutive_safe_polls INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(account_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_sessions_state ON agent_sessions(state)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def _mock_monitoring_status(windows_data):
    """Create a mock return for MonitoringService.get_monitoring_status().

    windows_data: list of dicts, each with:
        account_id, window_type, eta_status, minutes_remaining (optional), resets_at (optional)
    """
    windows = []
    for w in windows_data:
        eta = {"status": w["eta_status"]}
        if w.get("minutes_remaining") is not None:
            eta["minutes_remaining"] = w["minutes_remaining"]
        if w.get("message"):
            eta["message"] = w["message"]
        windows.append(
            {
                "account_id": w["account_id"],
                "window_type": w.get("window_type", "5h_sliding"),
                "resets_at": w.get("resets_at"),
                "eta": eta,
            }
        )
    return {
        "enabled": True,
        "polling_minutes": 5,
        "windows": windows,
        "threshold_alerts": [],
    }


@pytest.fixture(autouse=True)
def reset_scheduler_state():
    """Reset AgentSchedulerService class-level state before each test."""
    from app.services.agent_scheduler_service import AgentSchedulerService

    AgentSchedulerService._session_states = {}
    AgentSchedulerService._lock = threading.Lock()
    yield
    AgentSchedulerService._session_states = {}


# ===========================================================================
# DB Helper Tests
# ===========================================================================


class TestDBHelpers:
    """Tests for agent_sessions DB helper functions."""

    def test_upsert_and_get_agent_session(self, isolated_db):
        """Insert, read back, verify all fields."""
        from app.database import get_agent_session, get_connection, upsert_agent_session

        with get_connection() as conn:
            _ensure_scheduler_tables(conn)

        upsert_agent_session(
            account_id=1,
            state="stopped",
            stop_reason="at_limit",
            stop_window_type="5h_sliding",
            stop_eta_minutes=0.0,
            resume_estimate="2026-01-01T00:00:00Z",
            consecutive_safe_polls=0,
        )

        session = get_agent_session(1)
        assert session is not None
        assert session["account_id"] == 1
        assert session["state"] == "stopped"
        assert session["stop_reason"] == "at_limit"
        assert session["stop_window_type"] == "5h_sliding"
        assert session["stop_eta_minutes"] == 0.0
        assert session["resume_estimate"] == "2026-01-01T00:00:00Z"
        assert session["consecutive_safe_polls"] == 0

    def test_get_all_agent_sessions(self, isolated_db):
        """Insert multiple, verify list."""
        from app.database import get_all_agent_sessions, get_connection, upsert_agent_session

        with get_connection() as conn:
            _ensure_scheduler_tables(conn)

        upsert_agent_session(account_id=1, state="queued")
        upsert_agent_session(account_id=2, state="running")
        upsert_agent_session(account_id=3, state="stopped", stop_reason="at_limit")

        sessions = get_all_agent_sessions()
        assert len(sessions) == 3
        states = {s["account_id"]: s["state"] for s in sessions}
        assert states[1] == "queued"
        assert states[2] == "running"
        assert states[3] == "stopped"

    def test_upsert_overwrites_existing(self, isolated_db):
        """Insert same account_id twice, verify update."""
        from app.database import get_agent_session, get_connection, upsert_agent_session

        with get_connection() as conn:
            _ensure_scheduler_tables(conn)

        upsert_agent_session(account_id=1, state="queued")
        upsert_agent_session(account_id=1, state="stopped", stop_reason="approaching_limit")

        session = get_agent_session(1)
        assert session["state"] == "stopped"
        assert session["stop_reason"] == "approaching_limit"

    def test_delete_agent_session(self, isolated_db):
        """Insert, delete, verify gone."""
        from app.database import (
            delete_agent_session,
            get_agent_session,
            get_connection,
            upsert_agent_session,
        )

        with get_connection() as conn:
            _ensure_scheduler_tables(conn)

        upsert_agent_session(account_id=1, state="queued")
        assert get_agent_session(1) is not None

        result = delete_agent_session(1)
        assert result is True
        assert get_agent_session(1) is None


# ===========================================================================
# Eligibility Check Tests
# ===========================================================================


class TestEligibilityCheck:
    """Tests for check_eligibility admission control."""

    def test_check_eligibility_no_session_returns_eligible(self, isolated_db):
        """Default (no session) is eligible."""
        from app.services.agent_scheduler_service import AgentSchedulerService

        result = AgentSchedulerService.check_eligibility(999)
        assert result["eligible"] is True
        assert result["reason"] == "ok"

    def test_check_eligibility_stopped_returns_ineligible(self, isolated_db):
        """Stopped account returns eligible=False."""
        from app.services.agent_scheduler_service import AgentSchedulerService

        AgentSchedulerService._session_states["1"] = {
            "state": "stopped",
            "stop_reason": "at_limit",
            "stop_window_type": "5h_sliding",
            "stop_eta_minutes": 0,
            "resume_estimate": "2026-01-01T00:00:00Z",
            "consecutive_safe_polls": 0,
            "updated_at": None,
        }

        result = AgentSchedulerService.check_eligibility(1)
        assert result["eligible"] is False
        assert result["reason"] == "scheduler_paused"
        assert result["resume_estimate"] == "2026-01-01T00:00:00Z"

    def test_check_eligibility_queued_returns_eligible(self, isolated_db):
        """Queued account returns eligible=True."""
        from app.services.agent_scheduler_service import AgentSchedulerService

        AgentSchedulerService._session_states["1"] = {
            "state": "queued",
            "stop_reason": None,
            "stop_window_type": None,
            "stop_eta_minutes": None,
            "resume_estimate": None,
            "consecutive_safe_polls": 0,
            "updated_at": None,
        }

        result = AgentSchedulerService.check_eligibility(1)
        assert result["eligible"] is True
        assert result["reason"] == "ok"


# ===========================================================================
# Evaluation Loop Tests
# ===========================================================================


class TestEvaluationLoop:
    """Tests for evaluate_all_accounts with mocked monitoring data."""

    def _patch_evaluate(self, mock_status):
        """Helper: patch both monitoring status and config for evaluate tests."""
        default_config = {
            "enabled": True,
            "polling_minutes": 5,
            "accounts": {},
            "safety_margin_minutes": 5,
            "resume_hysteresis_polls": 2,
        }
        return (
            patch(
                "app.services.monitoring_service.MonitoringService.get_monitoring_status",
                return_value=mock_status,
            ),
            patch(
                "app.database.get_monitoring_config",
                return_value=default_config,
            ),
        )

    def test_evaluate_stops_account_at_limit(self, isolated_db):
        """Mock at_limit status -> account stopped."""
        from app.services.agent_scheduler_service import AgentSchedulerService

        now = datetime.now(timezone.utc)
        mock_status = _mock_monitoring_status(
            [
                {"account_id": 1, "eta_status": "at_limit", "minutes_remaining": None},
            ]
        )

        p1, p2 = self._patch_evaluate(mock_status)
        with p1, p2:
            AgentSchedulerService.evaluate_all_accounts(now=now)

        session = AgentSchedulerService._session_states.get("1")
        assert session is not None
        assert session["state"] == "stopped"
        assert session["stop_reason"] == "at_limit"

    def test_evaluate_stops_account_approaching_limit(self, isolated_db):
        """Mock projected status with minutes_remaining < safety_margin -> stopped."""
        from app.services.agent_scheduler_service import AgentSchedulerService

        now = datetime.now(timezone.utc)
        mock_status = _mock_monitoring_status(
            [
                {"account_id": 1, "eta_status": "projected", "minutes_remaining": 3},
            ]
        )

        p1, p2 = self._patch_evaluate(mock_status)
        with p1, p2:
            AgentSchedulerService.evaluate_all_accounts(now=now)

        session = AgentSchedulerService._session_states.get("1")
        assert session is not None
        assert session["state"] == "stopped"
        assert session["stop_reason"] == "approaching_limit"

    def test_evaluate_keeps_account_eligible_when_safe(self, isolated_db):
        """Mock safe status -> account stays queued (or not stopped)."""
        from app.services.agent_scheduler_service import AgentSchedulerService

        now = datetime.now(timezone.utc)
        mock_status = _mock_monitoring_status(
            [
                {"account_id": 1, "eta_status": "safe", "minutes_remaining": None},
            ]
        )

        p1, p2 = self._patch_evaluate(mock_status)
        with p1, p2:
            AgentSchedulerService.evaluate_all_accounts(now=now)

        session = AgentSchedulerService._session_states.get("1")
        # No session created for safe accounts (or if created, not stopped)
        if session:
            assert session["state"] != "stopped"

    def test_evaluate_no_data_treated_as_eligible(self, isolated_db):
        """Mock no_data status -> account stays eligible (fail-open)."""
        from app.services.agent_scheduler_service import AgentSchedulerService

        now = datetime.now(timezone.utc)
        mock_status = _mock_monitoring_status(
            [
                {"account_id": 1, "eta_status": "no_data", "minutes_remaining": None},
            ]
        )

        p1, p2 = self._patch_evaluate(mock_status)
        with p1, p2:
            AgentSchedulerService.evaluate_all_accounts(now=now)

        session = AgentSchedulerService._session_states.get("1")
        # Should not be stopped
        if session:
            assert session["state"] != "stopped"


# ===========================================================================
# Hysteresis Tests
# ===========================================================================


class TestHysteresis:
    """Tests for hysteresis-damped resume logic."""

    _default_config = {
        "enabled": True,
        "polling_minutes": 5,
        "accounts": {},
        "safety_margin_minutes": 5,
        "resume_hysteresis_polls": 2,
    }

    def _patch_evaluate(self, mock_status):
        """Helper: patch both monitoring status and config for evaluate tests."""
        return (
            patch(
                "app.services.monitoring_service.MonitoringService.get_monitoring_status",
                return_value=mock_status,
            ),
            patch(
                "app.database.get_monitoring_config",
                return_value=self._default_config,
            ),
        )

    def test_hysteresis_prevents_immediate_resume(self, isolated_db):
        """Set stopped, evaluate with safe status once -> still stopped."""
        from app.services.agent_scheduler_service import AgentSchedulerService

        now = datetime.now(timezone.utc)

        # Pre-set account as stopped
        AgentSchedulerService._set_state(1, "stopped", stop_reason="at_limit", now=now)

        # Evaluate with safe status (1 poll)
        mock_status = _mock_monitoring_status(
            [
                {"account_id": 1, "eta_status": "safe", "minutes_remaining": None},
            ]
        )
        p1, p2 = self._patch_evaluate(mock_status)
        with p1, p2:
            AgentSchedulerService.evaluate_all_accounts(now=now)

        session = AgentSchedulerService._session_states.get("1")
        assert session["state"] == "stopped"
        assert session["consecutive_safe_polls"] == 1

    def test_hysteresis_resumes_after_n_safe_polls(self, isolated_db):
        """Set stopped, evaluate with safe status N=2 times -> transitions to queued."""
        from app.services.agent_scheduler_service import AgentSchedulerService

        now = datetime.now(timezone.utc)

        # Pre-set account as stopped
        AgentSchedulerService._set_state(1, "stopped", stop_reason="approaching_limit", now=now)

        mock_status = _mock_monitoring_status(
            [
                {"account_id": 1, "eta_status": "safe", "minutes_remaining": None},
            ]
        )

        # Poll 1: still stopped
        p1, p2 = self._patch_evaluate(mock_status)
        with p1, p2:
            AgentSchedulerService.evaluate_all_accounts(now=now)

        assert AgentSchedulerService._session_states["1"]["state"] == "stopped"

        # Poll 2: should resume (default hysteresis = 2)
        p1, p2 = self._patch_evaluate(mock_status)
        with p1, p2:
            AgentSchedulerService.evaluate_all_accounts(now=now)

        assert AgentSchedulerService._session_states["1"]["state"] == "queued"

    def test_hysteresis_resets_on_new_stop(self, isolated_db):
        """Partially through resume (1 safe poll), then unsafe -> counter resets to 0."""
        from app.services.agent_scheduler_service import AgentSchedulerService

        now = datetime.now(timezone.utc)

        # Pre-set account as stopped
        AgentSchedulerService._set_state(1, "stopped", stop_reason="at_limit", now=now)

        # 1 safe poll
        safe_status = _mock_monitoring_status(
            [
                {"account_id": 1, "eta_status": "safe", "minutes_remaining": None},
            ]
        )
        p1, p2 = self._patch_evaluate(safe_status)
        with p1, p2:
            AgentSchedulerService.evaluate_all_accounts(now=now)

        assert AgentSchedulerService._session_states["1"]["consecutive_safe_polls"] == 1

        # Unsafe poll -> should reset counter
        unsafe_status = _mock_monitoring_status(
            [
                {"account_id": 1, "eta_status": "projected", "minutes_remaining": 2},
            ]
        )
        p1, p2 = self._patch_evaluate(unsafe_status)
        with p1, p2:
            AgentSchedulerService.evaluate_all_accounts(now=now)

        session = AgentSchedulerService._session_states["1"]
        assert session["state"] == "stopped"
        assert session["consecutive_safe_polls"] == 0


# ===========================================================================
# Execution Lifecycle Tests
# ===========================================================================


class TestExecutionLifecycle:
    """Tests for mark_running and mark_completed lifecycle hooks."""

    def test_mark_running_transitions_queued_to_running(self, isolated_db):
        """Account in queued state -> mark_running -> state is running."""
        from app.services.agent_scheduler_service import AgentSchedulerService

        AgentSchedulerService._set_state(1, "queued")

        AgentSchedulerService.mark_running(1)

        session = AgentSchedulerService._session_states.get("1")
        assert session is not None
        assert session["state"] == "running"

    def test_mark_running_creates_session_if_none(self, isolated_db):
        """Account with no session -> mark_running -> session created with running state."""
        from app.services.agent_scheduler_service import AgentSchedulerService

        AgentSchedulerService.mark_running(42)

        session = AgentSchedulerService._session_states.get("42")
        assert session is not None
        assert session["state"] == "running"

    def test_mark_completed_transitions_running_to_queued(self, isolated_db):
        """Account in running state -> mark_completed -> state is queued."""
        from app.services.agent_scheduler_service import AgentSchedulerService

        AgentSchedulerService._set_state(1, "running")

        AgentSchedulerService.mark_completed(1)

        session = AgentSchedulerService._session_states.get("1")
        assert session is not None
        assert session["state"] == "queued"

    def test_mark_completed_preserves_stopped_state(self, isolated_db):
        """Account in stopped state -> mark_completed -> state remains stopped."""
        from app.services.agent_scheduler_service import AgentSchedulerService

        now = datetime.now(timezone.utc)
        AgentSchedulerService._set_state(1, "stopped", stop_reason="at_limit", now=now)

        AgentSchedulerService.mark_completed(1)

        session = AgentSchedulerService._session_states.get("1")
        assert session is not None
        assert session["state"] == "stopped"
        assert session["stop_reason"] == "at_limit"


# ===========================================================================
# Most-Conservative ETA Tests
# ===========================================================================


class TestConservativeETA:
    """Tests for most-conservative ETA selection across multiple windows per account."""

    _default_config = {
        "enabled": True,
        "polling_minutes": 5,
        "accounts": {},
        "safety_margin_minutes": 5,
        "resume_hysteresis_polls": 2,
    }

    def _patch_evaluate(self, mock_status):
        """Helper: patch both monitoring status and config for evaluate tests."""
        return (
            patch(
                "app.services.monitoring_service.MonitoringService.get_monitoring_status",
                return_value=mock_status,
            ),
            patch(
                "app.database.get_monitoring_config",
                return_value=self._default_config,
            ),
        )

    def test_evaluate_uses_min_eta_across_windows(self, isolated_db):
        """Account with two windows (5h safe, weekly approaching) -> stops based on weekly."""
        from app.services.agent_scheduler_service import AgentSchedulerService

        now = datetime.now(timezone.utc)
        mock_status = _mock_monitoring_status(
            [
                {
                    "account_id": 1,
                    "window_type": "5h_sliding",
                    "eta_status": "safe",
                    "minutes_remaining": None,
                },
                {
                    "account_id": 1,
                    "window_type": "weekly",
                    "eta_status": "projected",
                    "minutes_remaining": 3,
                },
            ]
        )

        p1, p2 = self._patch_evaluate(mock_status)
        with p1, p2:
            AgentSchedulerService.evaluate_all_accounts(now=now)

        session = AgentSchedulerService._session_states.get("1")
        assert session is not None
        assert session["state"] == "stopped"
        assert session["stop_reason"] == "approaching_limit"

    def test_evaluate_handles_multiple_accounts(self, isolated_db):
        """Two accounts: one approaching, one safe -> only approaching one stopped."""
        from app.services.agent_scheduler_service import AgentSchedulerService

        now = datetime.now(timezone.utc)
        mock_status = _mock_monitoring_status(
            [
                {
                    "account_id": 1,
                    "window_type": "5h_sliding",
                    "eta_status": "projected",
                    "minutes_remaining": 2,
                },
                {
                    "account_id": 2,
                    "window_type": "5h_sliding",
                    "eta_status": "safe",
                    "minutes_remaining": None,
                },
            ]
        )

        p1, p2 = self._patch_evaluate(mock_status)
        with p1, p2:
            AgentSchedulerService.evaluate_all_accounts(now=now)

        session1 = AgentSchedulerService._session_states.get("1")
        assert session1 is not None
        assert session1["state"] == "stopped"

        session2 = AgentSchedulerService._session_states.get("2")
        # Account 2 either has no session or is not stopped
        if session2:
            assert session2["state"] != "stopped"


# ===========================================================================
# API Endpoint Tests
# ===========================================================================


class TestSchedulerAPI:
    """Tests for scheduler REST API endpoints."""

    def test_get_scheduler_status(self, client):
        """GET /admin/scheduler/status returns 200 and correct shape."""
        response = client.get("/admin/scheduler/status")
        assert response.status_code == 200
        data = response.get_json()
        assert "enabled" in data
        assert "safety_margin_minutes" in data
        assert "resume_hysteresis_polls" in data
        assert "sessions" in data
        assert isinstance(data["sessions"], list)
        assert "global_summary" in data
        assert "total" in data["global_summary"]

    def test_get_scheduler_sessions(self, client):
        """GET /admin/scheduler/sessions returns 200 and list shape."""
        response = client.get("/admin/scheduler/sessions")
        assert response.status_code == 200
        data = response.get_json()
        assert "sessions" in data
        assert isinstance(data["sessions"], list)

    def test_get_eligibility(self, client):
        """GET /admin/scheduler/eligibility/1 returns 200 and correct shape."""
        response = client.get("/admin/scheduler/eligibility/1")
        assert response.status_code == 200
        data = response.get_json()
        assert "eligible" in data
        assert "reason" in data
        assert data["eligible"] is True
        assert data["reason"] == "ok"


# ===========================================================================
# Integration Tests: Scheduler-Monitoring-Orchestration Pipeline
# ===========================================================================


class TestMonitoringSchedulerIntegration:
    """Integration tests verifying MonitoringService triggers scheduler evaluation."""

    def test_poll_usage_triggers_scheduler_evaluation(self, isolated_db):
        """MonitoringService._poll_usage() calls AgentSchedulerService.evaluate_all_accounts."""
        from app.services.monitoring_service import MonitoringService

        # Set up monitoring config with one account enabled
        mock_config = {
            "enabled": True,
            "polling_minutes": 5,
            "accounts": {"1": {"enabled": True}},
        }
        mock_accounts = [
            {"id": 1, "account_name": "test-acct", "backend_type": "claude"},
        ]

        with (
            patch("app.database.get_monitoring_config", return_value=mock_config),
            patch(
                "app.database.get_all_accounts_with_health",
                return_value=mock_accounts,
            ),
            patch("app.database.insert_rate_limit_snapshot"),
            patch(
                "app.services.provider_usage_client.ProviderUsageClient.fetch_usage",
                return_value=[
                    {
                        "tokens_used": 100,
                        "tokens_limit": 300000,
                        "percentage": 0.03,
                        "resets_at": None,
                        "window_type": "five_hour",
                    }
                ],
            ),
            patch(
                "app.services.agent_scheduler_service.AgentSchedulerService.evaluate_all_accounts"
            ) as mock_evaluate,
        ):
            MonitoringService._poll_usage()

        mock_evaluate.assert_called_once()
        # Verify the 'now' argument was passed
        args = mock_evaluate.call_args
        assert args[0][0] is not None  # now datetime was passed


class TestOrchestrationSchedulerIntegration:
    """Integration tests verifying OrchestrationService respects scheduler decisions."""

    def _make_bot(self, bot_id="bot-test1"):
        """Create a minimal bot dict for testing."""
        return {
            "id": bot_id,
            "name": "Test Bot",
            "backend_type": "claude",
            "prompt_template": "test",
        }

    def _make_chain(self, entries):
        """Create a fallback chain list from simplified entries.

        Each entry: (backend_type, account_id_or_None)
        """
        return [
            {"backend_type": bt, "account_id": aid, "priority": i}
            for i, (bt, aid) in enumerate(entries)
        ]

    def _make_account(self, account_id, backend_type="claude"):
        """Create a minimal account dict."""
        return {
            "id": account_id,
            "account_name": f"account-{account_id}",
            "backend_type": backend_type,
            "api_key_env": None,
        }

    def _base_patches(self, chain, accounts_by_type=None):
        """Return common patches for orchestration tests.

        Returns a dict of patch context managers keyed by name.
        The database functions (get_account_rate_limit_state, get_accounts_for_backend_type)
        are patched at app.database because they are imported locally inside the
        orchestration method via 'from ..database import ...'.
        """
        if accounts_by_type is None:
            accounts_by_type = {}

        def mock_get_accounts(bt):
            return accounts_by_type.get(bt, [])

        return {
            "chain": patch(
                "app.services.orchestration_service.get_fallback_chain",
                return_value=chain,
            ),
            "budget": patch(
                "app.services.orchestration_service.BudgetService.check_budget",
                return_value={"allowed": True, "reason": "ok"},
            ),
            "rate_limited": patch(
                "app.services.orchestration_service.RateLimitService.is_rate_limited",
                return_value=False,
            ),
            "account_state": patch(
                "app.database.get_account_rate_limit_state",
                return_value={"id": 1, "state": "ok"},
            ),
            "accounts_for_type": patch(
                "app.database.get_accounts_for_backend_type",
                side_effect=mock_get_accounts,
            ),
            "increment": patch(
                "app.services.orchestration_service.increment_account_executions",
            ),
        }

    def test_orchestration_skips_stopped_account(self, isolated_db):
        """Stopped account 1 is skipped; fallback to account 2 succeeds."""
        from app.services.agent_scheduler_service import AgentSchedulerService
        from app.services.orchestration_service import OrchestrationService

        now = datetime.now(timezone.utc)

        # Mark account 1 as stopped
        AgentSchedulerService._set_state(1, "stopped", stop_reason="at_limit", now=now)

        bot = self._make_bot()
        chain = self._make_chain([("claude", 1), ("claude", 2)])
        acct1 = self._make_account(1)
        acct2 = self._make_account(2)

        patches = self._base_patches(chain, accounts_by_type={"claude": [acct1, acct2]})
        # Track which account_id was used in run_bot
        used_accounts = []

        def mock_run_bot(bot, msg, event, trigger, env_overrides=None, account_id=None):
            used_accounts.append(account_id)
            return "exec-001"

        with (
            patches["chain"],
            patches["budget"],
            patches["rate_limited"],
            patches["increment"],
            patch(
                "app.database.get_account_rate_limit_state",
                return_value={"id": 2, "state": "ok"},
            ),
            patch(
                "app.database.get_accounts_for_backend_type",
                return_value=[acct1, acct2],
            ),
            patch(
                "app.services.execution_service.ExecutionService.run_trigger",
                side_effect=mock_run_bot,
            ),
            patch(
                "app.services.execution_service.ExecutionService.was_rate_limited",
                return_value=None,
            ),
        ):
            result = OrchestrationService.execute_with_fallback(bot, "test msg")

        assert result == "exec-001"
        assert used_accounts == [2], f"Expected account 2, got {used_accounts}"

    def test_orchestration_proceeds_when_eligible(self, isolated_db):
        """Eligible account proceeds normally (run_bot called)."""
        from app.services.orchestration_service import OrchestrationService

        bot = self._make_bot()
        chain = self._make_chain([("claude", 1)])
        acct1 = self._make_account(1)

        run_bot_called = []

        def mock_run_bot(bot, msg, event, trigger, env_overrides=None, account_id=None):
            run_bot_called.append(account_id)
            return "exec-002"

        patches = self._base_patches(chain, accounts_by_type={"claude": [acct1]})

        with (
            patches["chain"],
            patches["budget"],
            patches["rate_limited"],
            patches["account_state"],
            patches["increment"],
            patch(
                "app.database.get_accounts_for_backend_type",
                return_value=[acct1],
            ),
            patch(
                "app.services.execution_service.ExecutionService.run_trigger",
                side_effect=mock_run_bot,
            ),
            patch(
                "app.services.execution_service.ExecutionService.was_rate_limited",
                return_value=None,
            ),
        ):
            result = OrchestrationService.execute_with_fallback(bot, "test msg")

        assert result == "exec-002"
        assert run_bot_called == [1]

    def test_orchestration_marks_running_before_execution(self, isolated_db):
        """Account is in 'running' state when run_bot is called, 'queued' after."""
        from app.services.agent_scheduler_service import AgentSchedulerService
        from app.services.orchestration_service import OrchestrationService

        bot = self._make_bot()
        chain = self._make_chain([("claude", 1)])
        acct1 = self._make_account(1)

        state_during_execution = []

        def mock_run_bot(bot, msg, event, trigger, env_overrides=None, account_id=None):
            # Capture scheduler state at the moment of execution
            session = AgentSchedulerService._session_states.get("1")
            state_during_execution.append(session["state"] if session else "no_session")
            return "exec-003"

        patches = self._base_patches(chain, accounts_by_type={"claude": [acct1]})

        with (
            patches["chain"],
            patches["budget"],
            patches["rate_limited"],
            patches["account_state"],
            patches["increment"],
            patch(
                "app.database.get_accounts_for_backend_type",
                return_value=[acct1],
            ),
            patch(
                "app.services.execution_service.ExecutionService.run_trigger",
                side_effect=mock_run_bot,
            ),
            patch(
                "app.services.execution_service.ExecutionService.was_rate_limited",
                return_value=None,
            ),
        ):
            OrchestrationService.execute_with_fallback(bot, "test msg")

        # During execution, account should have been "running"
        assert state_during_execution == ["running"]

        # After execution, account should be "queued" (mark_completed was called)
        session = AgentSchedulerService._session_states.get("1")
        assert session is not None
        assert session["state"] == "queued"

    def test_orchestration_marks_completed_on_failure(self, isolated_db):
        """mark_completed called in finally block even when run_bot raises."""
        from app.services.agent_scheduler_service import AgentSchedulerService
        from app.services.orchestration_service import OrchestrationService

        bot = self._make_bot()
        chain = self._make_chain([("claude", 1)])
        acct1 = self._make_account(1)

        def mock_run_bot_raises(bot, msg, event, trigger, env_overrides=None, account_id=None):
            raise RuntimeError("Execution failed!")

        patches = self._base_patches(chain, accounts_by_type={"claude": [acct1]})

        with pytest.raises(RuntimeError, match="Execution failed!"):
            with (
                patches["chain"],
                patches["budget"],
                patches["rate_limited"],
                patches["account_state"],
                patches["increment"],
                patch(
                    "app.database.get_accounts_for_backend_type",
                    return_value=[acct1],
                ),
                patch(
                    "app.services.execution_service.ExecutionService.run_trigger",
                    side_effect=mock_run_bot_raises,
                ),
                patch(
                    "app.services.execution_service.ExecutionService.was_rate_limited",
                    return_value=None,
                ),
            ):
                OrchestrationService.execute_with_fallback(bot, "test msg")

        # Even after exception, account should be "queued" (mark_completed called in finally)
        session = AgentSchedulerService._session_states.get("1")
        assert session is not None
        assert session["state"] == "queued"


class TestSchedulerInitIntegration:
    """Integration tests for scheduler initialization from DB."""

    def test_scheduler_init_loads_from_db(self, isolated_db):
        """AgentSchedulerService.init() loads persisted sessions from DB."""
        from app.database import get_connection, upsert_agent_session
        from app.services.agent_scheduler_service import AgentSchedulerService

        with get_connection() as conn:
            _ensure_scheduler_tables(conn)

        # Insert a stopped session directly via DB helper
        upsert_agent_session(
            account_id=42,
            state="stopped",
            stop_reason="at_limit",
            stop_window_type="5h_sliding",
            stop_eta_minutes=0.0,
            resume_estimate="2026-06-01T00:00:00Z",
            consecutive_safe_polls=0,
        )

        # Clear in-memory state
        AgentSchedulerService._session_states = {}

        # Re-initialize from DB
        AgentSchedulerService.init()

        # Verify in-memory cache reflects DB state
        session = AgentSchedulerService._session_states.get("42")
        assert session is not None
        assert session["state"] == "stopped"
        assert session["stop_reason"] == "at_limit"

        # Verify check_eligibility returns ineligible for this account
        result = AgentSchedulerService.check_eligibility(42)
        assert result["eligible"] is False
        assert result["reason"] == "scheduler_paused"


class TestMonitoringConfigSchedulerFields:
    """Integration tests for monitoring_config scheduler fields."""

    def test_monitoring_config_supports_scheduler_fields(self, isolated_db):
        """monitoring_config JSON supports safety_margin_minutes and resume_hysteresis_polls."""
        from app.database import get_connection, get_monitoring_config, save_monitoring_config

        with get_connection() as conn:
            _ensure_scheduler_tables(conn)

        config = {
            "enabled": True,
            "polling_minutes": 5,
            "accounts": {},
            "safety_margin_minutes": 10,
            "resume_hysteresis_polls": 3,
        }
        save_monitoring_config(config)

        loaded = get_monitoring_config()
        assert loaded["safety_margin_minutes"] == 10
        assert loaded["resume_hysteresis_polls"] == 3
        assert loaded["enabled"] is True
        assert loaded["polling_minutes"] == 5
