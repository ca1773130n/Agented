"""Per-backend circuit breaker service with CLOSED/OPEN/HALF_OPEN states.

Implements the Nygard (2018) three-state circuit breaker pattern to prevent
cascading failures during AI backend outages. Each backend type (claude,
opencode, gemini, codex) has an independent breaker that:

- CLOSED: Normal operation. Failures increment fail_count.
- OPEN: Fast-fail all requests. Transitions to HALF_OPEN after reset_timeout.
- HALF_OPEN: Allow a trial request. Success -> CLOSED, failure -> OPEN.

State is persisted to SQLite so breakers survive server restarts.
Thread safety via per-backend locks.
"""

import logging
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import ClassVar, Dict, List, Optional

from ..db.circuit_breakers import (
    get_all_breaker_states,
    get_breaker_state,
    upsert_breaker_state,
)

logger = logging.getLogger(__name__)


class BreakerState(str, Enum):
    """Circuit breaker states following Nygard (2018) / Fowler (2014) model."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """In-memory state for a single backend's circuit breaker."""

    backend_type: str
    state: BreakerState = BreakerState.CLOSED
    fail_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[float] = None
    fail_max: int = 5
    reset_timeout: float = 60.0  # seconds before OPEN -> HALF_OPEN
    success_threshold: int = 1  # successes in HALF_OPEN before closing


# Compiled patterns for transient error detection in stderr output
_TRANSIENT_PATTERNS = [
    re.compile(r"connection\s+refused", re.IGNORECASE),
    re.compile(r"connection\s+reset", re.IGNORECASE),
    re.compile(r"connection\s+timed?\s*out", re.IGNORECASE),
    re.compile(r"timed?\s*out", re.IGNORECASE),
    re.compile(r"\b502\b", re.IGNORECASE),
    re.compile(r"\b503\b", re.IGNORECASE),
    re.compile(r"service\s+unavailable", re.IGNORECASE),
    re.compile(r"bad\s+gateway", re.IGNORECASE),
    re.compile(r"overloaded", re.IGNORECASE),
    re.compile(r"rate.limit", re.IGNORECASE),
    re.compile(r"ECONNREFUSED", re.IGNORECASE),
    re.compile(r"ETIMEDOUT", re.IGNORECASE),
    re.compile(r"ECONNRESET", re.IGNORECASE),
]

# Patterns that indicate non-transient errors (should NOT trip the breaker)
_NON_TRANSIENT_PATTERNS = [
    re.compile(r"FileNotFoundError", re.IGNORECASE),
    re.compile(r"command\s+not\s+found", re.IGNORECASE),
    re.compile(r"authentication\s+(failed|error|required)", re.IGNORECASE),
    re.compile(r"invalid\s+(api[_ ]?key|token|credential)", re.IGNORECASE),
    re.compile(r"permission\s+denied", re.IGNORECASE),
    re.compile(r"unauthorized", re.IGNORECASE),
    re.compile(r"bad\s+prompt", re.IGNORECASE),
    re.compile(r"invalid\s+prompt", re.IGNORECASE),
    re.compile(r"syntax\s+error", re.IGNORECASE),
    re.compile(r"No such file or directory", re.IGNORECASE),
]


class CircuitBreakerService:
    """Per-backend circuit breaker state machine with SQLite persistence.

    Uses @classmethod methods following existing service patterns. Thread-safe
    via per-backend threading.Lock instances.
    """

    # In-memory state keyed by backend_type
    _breakers: ClassVar[Dict[str, CircuitBreaker]] = {}
    # Per-backend locks for thread safety
    _locks: ClassVar[Dict[str, threading.Lock]] = {}
    # Global lock for dict-level operations (adding new breakers)
    _global_lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def _get_lock(cls, backend_type: str) -> threading.Lock:
        """Get or create a lock for a specific backend type."""
        if backend_type not in cls._locks:
            with cls._global_lock:
                if backend_type not in cls._locks:
                    cls._locks[backend_type] = threading.Lock()
        return cls._locks[backend_type]

    @classmethod
    def _ensure_breaker(
        cls,
        backend_type: str,
        fail_max: int = 5,
        reset_timeout: float = 60.0,
        success_threshold: int = 1,
    ) -> CircuitBreaker:
        """Get or create a breaker WITHOUT acquiring the lock.

        Callers MUST hold the per-backend lock before calling this method.
        """
        if backend_type in cls._breakers:
            return cls._breakers[backend_type]

        breaker = CircuitBreaker(
            backend_type=backend_type,
            fail_max=fail_max,
            reset_timeout=reset_timeout,
            success_threshold=success_threshold,
        )

        try:
            db_state = get_breaker_state(backend_type)
            if db_state:
                breaker.state = BreakerState(db_state["state"])
                breaker.fail_count = db_state["fail_count"]
                breaker.success_count = db_state["success_count"]
                breaker.last_failure_time = db_state["last_failure_time"]

                # Handle stale OPEN state: if recovery timeout has elapsed,
                # reset to CLOSED (anti-pattern: stale OPEN on restart)
                if breaker.state == BreakerState.OPEN and breaker.last_failure_time:
                    elapsed = time.time() - breaker.last_failure_time
                    if elapsed >= breaker.reset_timeout:
                        logger.info(
                            "Circuit breaker for %s was OPEN but reset_timeout "
                            "elapsed (%.1fs ago). Resetting to CLOSED.",
                            backend_type,
                            elapsed,
                        )
                        breaker.state = BreakerState.CLOSED
                        breaker.fail_count = 0
                        breaker.success_count = 0
                        cls._persist_state(breaker)
        except Exception:
            logger.exception(
                "Failed to restore circuit breaker state for %s, using defaults",
                backend_type,
            )

        cls._breakers[backend_type] = breaker
        return breaker

    @classmethod
    def get_breaker(
        cls,
        backend_type: str,
        fail_max: int = 5,
        reset_timeout: float = 60.0,
        success_threshold: int = 1,
    ) -> CircuitBreaker:
        """Get or lazy-initialize a circuit breaker for a backend type.

        On first access, attempts to restore state from SQLite. If no persisted
        state exists, creates a new breaker in CLOSED state.
        """
        lock = cls._get_lock(backend_type)
        with lock:
            return cls._ensure_breaker(backend_type, fail_max, reset_timeout, success_threshold)

    @classmethod
    def can_execute(cls, backend_type: str) -> bool:
        """Check if a backend is available for execution.

        - CLOSED: Always True
        - OPEN: False, unless reset_timeout has elapsed -> transitions to HALF_OPEN, returns True
        - HALF_OPEN: True (allow trial request)
        """
        lock = cls._get_lock(backend_type)
        with lock:
            breaker = cls._ensure_breaker(backend_type)

            if breaker.state == BreakerState.CLOSED:
                return True

            if breaker.state == BreakerState.HALF_OPEN:
                return True

            # OPEN state: check if reset_timeout has elapsed
            if breaker.state == BreakerState.OPEN:
                if breaker.last_failure_time is None:
                    breaker.state = BreakerState.HALF_OPEN
                    breaker.success_count = 0
                    cls._persist_state(breaker)
                    logger.info(
                        "Circuit breaker for %s transitioned OPEN -> HALF_OPEN "
                        "(no last_failure_time)",
                        backend_type,
                    )
                    return True

                elapsed = time.time() - breaker.last_failure_time
                if elapsed >= breaker.reset_timeout:
                    breaker.state = BreakerState.HALF_OPEN
                    breaker.success_count = 0
                    cls._persist_state(breaker)
                    logger.info(
                        "Circuit breaker for %s transitioned OPEN -> HALF_OPEN "
                        "after %.1fs (timeout=%.1fs)",
                        backend_type,
                        elapsed,
                        breaker.reset_timeout,
                    )
                    return True

                return False

            return False  # pragma: no cover

    @classmethod
    def record_success(cls, backend_type: str) -> None:
        """Record a successful execution for a backend.

        - HALF_OPEN: Increment success_count. If >= success_threshold, transition to CLOSED.
        - CLOSED: Reset fail_count to 0.
        """
        lock = cls._get_lock(backend_type)
        with lock:
            breaker = cls._ensure_breaker(backend_type)

            if breaker.state == BreakerState.HALF_OPEN:
                breaker.success_count += 1
                if breaker.success_count >= breaker.success_threshold:
                    breaker.state = BreakerState.CLOSED
                    breaker.fail_count = 0
                    breaker.success_count = 0
                    logger.info(
                        "Circuit breaker for %s transitioned HALF_OPEN -> CLOSED "
                        "after %d successes",
                        backend_type,
                        breaker.success_threshold,
                    )
                cls._persist_state(breaker)

            elif breaker.state == BreakerState.CLOSED:
                if breaker.fail_count > 0:
                    breaker.fail_count = 0
                    cls._persist_state(breaker)

    @classmethod
    def record_failure(cls, backend_type: str, error: Optional[str] = None) -> None:
        """Record a failed execution for a backend (transient errors only).

        - CLOSED: Increment fail_count. If >= fail_max, transition to OPEN.
        - HALF_OPEN: Transition immediately back to OPEN.

        Only call this for transient errors. Use is_transient_error() to classify first.
        """
        lock = cls._get_lock(backend_type)
        with lock:
            breaker = cls._ensure_breaker(backend_type)
            breaker.last_failure_time = time.time()

            if breaker.state == BreakerState.HALF_OPEN:
                breaker.state = BreakerState.OPEN
                logger.warning(
                    "Circuit breaker for %s transitioned HALF_OPEN -> OPEN on failure",
                    backend_type,
                )
                cls._persist_state(breaker)

            elif breaker.state == BreakerState.CLOSED:
                breaker.fail_count += 1
                if breaker.fail_count >= breaker.fail_max:
                    breaker.state = BreakerState.OPEN
                    logger.warning(
                        "Circuit breaker for %s transitioned CLOSED -> OPEN "
                        "after %d consecutive failures (max=%d)",
                        backend_type,
                        breaker.fail_count,
                        breaker.fail_max,
                    )
                cls._persist_state(breaker)

            elif breaker.state == BreakerState.OPEN:
                # Already open, just update failure time
                cls._persist_state(breaker)

    @classmethod
    def is_transient_error(
        cls,
        error: Optional[str] = None,
        exit_code: Optional[int] = None,
        exception: Optional[Exception] = None,
    ) -> bool:
        """Classify whether an error is transient (retryable) or permanent.

        Transient errors: connection refused, timeout, 502/503, rate limit,
        subprocess.TimeoutExpired.

        Non-transient errors: FileNotFoundError, auth errors, bad prompt,
        command not found.

        Returns True if the error is transient and should trip the breaker / trigger retry.
        """
        # Check exception type first
        if exception is not None:
            if isinstance(exception, subprocess.TimeoutExpired):
                return True
            if isinstance(exception, (FileNotFoundError, PermissionError)):
                return False

        # Check stderr/error text
        if error:
            # Check non-transient patterns first (higher specificity)
            for pattern in _NON_TRANSIENT_PATTERNS:
                if pattern.search(error):
                    return False

            # Check transient patterns
            for pattern in _TRANSIENT_PATTERNS:
                if pattern.search(error):
                    return True

        # Exit code heuristics
        if exit_code is not None:
            # Exit code 127 = command not found (non-transient)
            if exit_code == 127:
                return False
            # Exit code 126 = permission denied (non-transient)
            if exit_code == 126:
                return False

        return False

    @classmethod
    def get_all_states(cls) -> List[dict]:
        """Get all circuit breaker states for admin visibility.

        Returns both in-memory and persisted states merged.
        """
        result = []
        # Include in-memory breakers
        with cls._global_lock:
            for backend_type, breaker in cls._breakers.items():
                result.append({
                    "backend_type": breaker.backend_type,
                    "state": breaker.state.value,
                    "fail_count": breaker.fail_count,
                    "success_count": breaker.success_count,
                    "last_failure_time": breaker.last_failure_time,
                })

        # Also include any persisted states not in memory
        try:
            db_states = get_all_breaker_states()
            in_memory_types = {r["backend_type"] for r in result}
            for db_state in db_states:
                if db_state["backend_type"] not in in_memory_types:
                    result.append({
                        "backend_type": db_state["backend_type"],
                        "state": db_state["state"],
                        "fail_count": db_state["fail_count"],
                        "success_count": db_state["success_count"],
                        "last_failure_time": db_state["last_failure_time"],
                    })
        except Exception:
            logger.exception("Failed to read persisted breaker states")

        return result

    @classmethod
    def restore_from_db(cls) -> None:
        """Restore all circuit breaker states from SQLite on server startup.

        If a breaker was OPEN and the reset_timeout has elapsed since
        last_failure_time, it is transitioned to CLOSED (handles stale OPEN state).
        """
        try:
            db_states = get_all_breaker_states()
            for db_state in db_states:
                backend_type = db_state["backend_type"]
                # get_breaker handles stale OPEN -> CLOSED transition
                cls.get_breaker(backend_type)
                logger.info(
                    "Restored circuit breaker for %s: state=%s, fail_count=%d",
                    backend_type,
                    cls._breakers[backend_type].state.value,
                    cls._breakers[backend_type].fail_count,
                )
        except Exception:
            logger.exception("Failed to restore circuit breaker states from DB")

    @classmethod
    def _persist_state(cls, breaker: CircuitBreaker) -> None:
        """Write current in-memory state to SQLite.

        Called after every state transition. Errors are logged but do not
        prevent in-memory state from being used.
        """
        try:
            upsert_breaker_state(
                backend_type=breaker.backend_type,
                state=breaker.state.value,
                fail_count=breaker.fail_count,
                success_count=breaker.success_count,
                last_failure_time=breaker.last_failure_time,
            )
        except Exception:
            logger.exception(
                "Failed to persist circuit breaker state for %s",
                breaker.backend_type,
            )

    @classmethod
    def reset(cls) -> None:
        """Reset all in-memory state. Used for testing."""
        with cls._global_lock:
            cls._breakers.clear()
            cls._locks.clear()
