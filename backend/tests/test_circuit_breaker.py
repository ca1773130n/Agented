"""Tests for CircuitBreakerService state transitions, persistence, and error classification."""

import subprocess
import threading
import time
from unittest.mock import patch

import pytest

from app.db.circuit_breakers import get_breaker_state, upsert_breaker_state
from app.db.migrations import init_db
from app.services.circuit_breaker_service import (
    BreakerState,
    CircuitBreakerService,
)


@pytest.fixture(autouse=True)
def _init_db_and_reset():
    """Initialize DB and reset in-memory circuit breaker state for each test."""
    init_db()
    CircuitBreakerService.reset()
    yield
    CircuitBreakerService.reset()


class TestCircuitBreakerTransitions:
    """Test circuit breaker state machine transitions."""

    def test_initial_state_is_closed(self):
        """New breaker starts in CLOSED state."""
        breaker = CircuitBreakerService.get_breaker("claude")
        assert breaker.state == BreakerState.CLOSED
        assert breaker.fail_count == 0

    def test_closed_to_open_after_fail_max(self):
        """CLOSED -> OPEN after fail_max consecutive failures."""
        for i in range(5):
            CircuitBreakerService.record_failure("claude", "connection refused")

        breaker = CircuitBreakerService.get_breaker("claude")
        assert breaker.state == BreakerState.OPEN
        assert breaker.fail_count == 5

    def test_open_fast_fail(self):
        """OPEN state fast-fails (can_execute returns False)."""
        for i in range(5):
            CircuitBreakerService.record_failure("claude", "timeout")

        assert CircuitBreakerService.can_execute("claude") is False

    def test_open_to_half_open_after_timeout(self):
        """OPEN -> HALF_OPEN after reset_timeout elapses."""
        # Use a short timeout for testing
        breaker = CircuitBreakerService.get_breaker("claude", reset_timeout=0.1)
        for i in range(5):
            CircuitBreakerService.record_failure("claude", "502")

        assert breaker.state == BreakerState.OPEN
        assert CircuitBreakerService.can_execute("claude") is False

        # Wait for timeout
        time.sleep(0.15)

        assert CircuitBreakerService.can_execute("claude") is True
        breaker = CircuitBreakerService.get_breaker("claude")
        assert breaker.state == BreakerState.HALF_OPEN

    def test_half_open_to_closed_on_success(self):
        """HALF_OPEN -> CLOSED on success."""
        breaker = CircuitBreakerService.get_breaker("claude", reset_timeout=0.1)
        for i in range(5):
            CircuitBreakerService.record_failure("claude", "503")

        time.sleep(0.15)
        CircuitBreakerService.can_execute("claude")  # trigger HALF_OPEN

        CircuitBreakerService.record_success("claude")

        breaker = CircuitBreakerService.get_breaker("claude")
        assert breaker.state == BreakerState.CLOSED
        assert breaker.fail_count == 0

    def test_half_open_to_open_on_failure(self):
        """HALF_OPEN -> OPEN immediately on failure."""
        breaker = CircuitBreakerService.get_breaker("claude", reset_timeout=0.1)
        for i in range(5):
            CircuitBreakerService.record_failure("claude", "timeout")

        time.sleep(0.15)
        CircuitBreakerService.can_execute("claude")  # trigger HALF_OPEN

        CircuitBreakerService.record_failure("claude", "timeout again")

        breaker = CircuitBreakerService.get_breaker("claude")
        assert breaker.state == BreakerState.OPEN

    def test_success_resets_fail_count_in_closed(self):
        """Success in CLOSED state resets fail_count to 0."""
        CircuitBreakerService.record_failure("claude", "timeout")
        CircuitBreakerService.record_failure("claude", "timeout")

        breaker = CircuitBreakerService.get_breaker("claude")
        assert breaker.fail_count == 2

        CircuitBreakerService.record_success("claude")

        breaker = CircuitBreakerService.get_breaker("claude")
        assert breaker.fail_count == 0

    def test_can_execute_closed_returns_true(self):
        """CLOSED state always allows execution."""
        assert CircuitBreakerService.can_execute("claude") is True

    def test_per_backend_independence(self):
        """Each backend has its own independent breaker."""
        for i in range(5):
            CircuitBreakerService.record_failure("claude", "timeout")

        assert CircuitBreakerService.can_execute("claude") is False
        assert CircuitBreakerService.can_execute("opencode") is True
        assert CircuitBreakerService.can_execute("gemini") is True


class TestTransientErrorClassification:
    """Test error classification for transient vs non-transient errors."""

    @pytest.mark.parametrize(
        "error",
        [
            "connection refused",
            "Connection timed out",
            "502 Bad Gateway",
            "503 Service Unavailable",
            "service unavailable",
            "bad gateway",
            "server overloaded",
            "rate limit exceeded",
            "ECONNREFUSED",
            "ETIMEDOUT",
            "ECONNRESET",
            "connection reset by peer",
        ],
    )
    def test_transient_errors(self, error):
        """Transient errors are correctly classified."""
        assert CircuitBreakerService.is_transient_error(error=error) is True

    @pytest.mark.parametrize(
        "error",
        [
            "FileNotFoundError: /usr/bin/claude",
            "command not found",
            "authentication failed",
            "invalid api key",
            "permission denied",
            "unauthorized",
            "bad prompt syntax",
            "invalid prompt template",
            "syntax error in config",
            "No such file or directory",
        ],
    )
    def test_non_transient_errors(self, error):
        """Non-transient errors are correctly classified."""
        assert CircuitBreakerService.is_transient_error(error=error) is False

    def test_timeout_expired_exception(self):
        """subprocess.TimeoutExpired is classified as transient."""
        exc = subprocess.TimeoutExpired(cmd="claude", timeout=30)
        assert CircuitBreakerService.is_transient_error(exception=exc) is True

    def test_file_not_found_exception(self):
        """FileNotFoundError is classified as non-transient."""
        exc = FileNotFoundError("No such file")
        assert CircuitBreakerService.is_transient_error(exception=exc) is False

    def test_exit_code_127_non_transient(self):
        """Exit code 127 (command not found) is non-transient."""
        assert CircuitBreakerService.is_transient_error(exit_code=127) is False

    def test_exit_code_126_non_transient(self):
        """Exit code 126 (permission denied) is non-transient."""
        assert CircuitBreakerService.is_transient_error(exit_code=126) is False

    def test_non_transient_errors_do_not_trip_breaker(self):
        """Non-transient errors should not be passed to record_failure."""
        for i in range(10):
            error = "FileNotFoundError: /usr/bin/claude"
            if not CircuitBreakerService.is_transient_error(error=error):
                pass  # Don't record failure for non-transient
            else:
                CircuitBreakerService.record_failure("claude", error)

        breaker = CircuitBreakerService.get_breaker("claude")
        assert breaker.state == BreakerState.CLOSED
        assert breaker.fail_count == 0

    def test_unknown_error_not_transient(self):
        """Unknown errors without matching patterns are not transient."""
        assert CircuitBreakerService.is_transient_error(error="some random error") is False

    def test_no_error_info_not_transient(self):
        """No error information at all is not transient."""
        assert CircuitBreakerService.is_transient_error() is False


class TestSQLitePersistence:
    """Test circuit breaker state persistence and restoration."""

    def test_state_persisted_on_failure(self):
        """State is written to SQLite after recording failures."""
        CircuitBreakerService.record_failure("claude", "timeout")

        db_state = get_breaker_state("claude")
        assert db_state is not None
        assert db_state["state"] == "closed"
        assert db_state["fail_count"] == 1

    def test_state_persisted_on_open_transition(self):
        """OPEN state is persisted to SQLite."""
        for i in range(5):
            CircuitBreakerService.record_failure("claude", "timeout")

        db_state = get_breaker_state("claude")
        assert db_state is not None
        assert db_state["state"] == "open"
        assert db_state["fail_count"] == 5

    def test_persistence_round_trip(self):
        """Save state, reset in-memory, reload, verify restored."""
        for i in range(3):
            CircuitBreakerService.record_failure("claude", "timeout")

        # Reset in-memory state
        CircuitBreakerService.reset()

        # Reload from DB
        breaker = CircuitBreakerService.get_breaker("claude")
        assert breaker.state == BreakerState.CLOSED
        assert breaker.fail_count == 3

    def test_stale_open_reset_on_restart(self):
        """OPEN breaker with elapsed timeout resets to CLOSED on restart."""
        breaker = CircuitBreakerService.get_breaker("claude", reset_timeout=0.1)
        for i in range(5):
            CircuitBreakerService.record_failure("claude", "timeout")

        assert breaker.state == BreakerState.OPEN

        time.sleep(0.15)

        # Simulate restart
        CircuitBreakerService.reset()
        restored = CircuitBreakerService.get_breaker("claude", reset_timeout=0.1)

        assert restored.state == BreakerState.CLOSED
        assert restored.fail_count == 0

    def test_restore_from_db(self):
        """restore_from_db loads all persisted breakers."""
        # Persist states for multiple backends
        upsert_breaker_state("claude", "closed", 2, 0, None)
        upsert_breaker_state("opencode", "closed", 1, 0, None)

        CircuitBreakerService.reset()
        CircuitBreakerService.restore_from_db()

        states = CircuitBreakerService.get_all_states()
        backend_types = {s["backend_type"] for s in states}
        assert "claude" in backend_types
        assert "opencode" in backend_types


class TestConcurrency:
    """Test thread safety of circuit breaker operations."""

    def test_concurrent_failures(self):
        """Multiple threads calling record_failure concurrently."""
        errors = []

        def record_failures():
            try:
                for _ in range(10):
                    CircuitBreakerService.record_failure("claude", "timeout")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_failures) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        breaker = CircuitBreakerService.get_breaker("claude")
        # Should be OPEN (at least 5 failures recorded)
        assert breaker.state == BreakerState.OPEN

    def test_concurrent_mixed_operations(self):
        """Multiple threads doing mixed operations don't deadlock or crash."""
        errors = []

        def mixed_ops(backend):
            try:
                for _ in range(5):
                    CircuitBreakerService.can_execute(backend)
                    CircuitBreakerService.record_failure(backend, "timeout")
                    CircuitBreakerService.record_success(backend)
                    CircuitBreakerService.get_all_states()
            except Exception as e:
                errors.append(e)

        backends = ["claude", "opencode", "gemini", "codex"]
        threads = [threading.Thread(target=mixed_ops, args=(b,)) for b in backends]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


class TestGetAllStates:
    """Test admin visibility of circuit breaker states."""

    def test_get_all_states_empty(self):
        """Returns empty list when no breakers exist."""
        assert CircuitBreakerService.get_all_states() == []

    def test_get_all_states_returns_all(self):
        """Returns states for all initialized breakers."""
        CircuitBreakerService.get_breaker("claude")
        CircuitBreakerService.get_breaker("opencode")

        states = CircuitBreakerService.get_all_states()
        types = {s["backend_type"] for s in states}
        assert types == {"claude", "opencode"}

    def test_get_all_states_includes_db_only(self):
        """Includes persisted states not in memory."""
        upsert_breaker_state("gemini", "open", 5, 0, time.time())

        states = CircuitBreakerService.get_all_states()
        types = {s["backend_type"] for s in states}
        assert "gemini" in types
