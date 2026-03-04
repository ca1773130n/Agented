# Phase 13: Execution Resilience & Infrastructure - Research

**Researched:** 2026-03-04
**Domain:** Distributed systems resilience patterns -- circuit breakers, retry mechanisms, execution queuing, persistent state, process lifecycle management, webhook security
**Confidence:** HIGH

## Summary

Phase 13 hardens the existing execution engine, which currently relies on in-memory state (class-level dicts guarded by `threading.Lock`) for execution tracking, retry scheduling (`threading.Timer`), and log streaming. The codebase already has partial implementations of several resilience features: DB-backed pending retries (`pending_retries` table), webhook deduplication (`webhook_dedup_keys` table), execution logs persisted to SQLite (`execution_logs` table), per-trigger HMAC validation (`webhook_secret` column on triggers), and workflow execution history (`workflow_executions` / `workflow_node_executions` tables). The work is therefore primarily about completing and hardening these mechanisms, not building from scratch.

The recommended approach uses well-established stability patterns from Michael T. Nygard's "Release It!" (2007, 2nd ed. 2018) -- circuit breaker, bulkhead (concurrency caps), retry with backoff -- implemented with lightweight custom code rather than external libraries, since the project's subprocess-based execution model does not map cleanly onto decorator-based circuit breaker libraries like pybreaker. For the execution queue, a custom SQLite-backed FIFO queue with `threading.Semaphore` per-bot concurrency caps is preferred over introducing a third-party task queue (Celery, Huey, etc.) which would add unnecessary infrastructure complexity for a single-process Flask application.

**Primary recommendation:** Build custom circuit breaker, retry, and queue services as new service modules (`circuit_breaker_service.py`, `execution_queue_service.py`) using the existing `threading.Lock` + SQLite persistence pattern already established in the codebase, and migrate remaining in-memory-only execution state to durable SQLite storage.

## Paper-Backed Recommendations

Every recommendation below cites specific evidence.

### Recommendation 1: Three-State Circuit Breaker with SQLite-Persisted State

**Recommendation:** Implement a per-backend circuit breaker following the three-state model (CLOSED -> OPEN -> HALF_OPEN -> CLOSED) from "Release It!" with failure counts and state transitions persisted to SQLite.

**Evidence:**
- Nygard, M.T. (2007, 2018) "Release It! Design and Deploy Production-Ready Software" -- Chapter 5 defines the circuit breaker pattern as the primary stability pattern for protecting integration points. The three-state machine (CLOSED/OPEN/HALF_OPEN) with configurable `fail_max` and `reset_timeout` is the canonical implementation.
- AWS Prescriptive Guidance (2024) "Circuit Breaker Pattern" -- Documents the pattern for cloud services with specific guidance on state transitions, failure thresholds, and health checks.
- pybreaker library (GitHub: danielfm/pybreaker, 1.2k stars) -- Reference Python implementation showing `fail_max=5, reset_timeout=60` as practical defaults.

**Confidence:** HIGH -- Pattern is well-established with 17+ years of production use across industries. Multiple independent implementations agree on the three-state model.

**Expected improvement:** Eliminates cascading failures when AI backends (Claude, Gemini, Codex) are unavailable. Currently, each execution attempt against a failing backend wastes the full timeout duration (up to 600s default) before failing. Circuit breaker fast-fails in < 1ms after threshold is reached.

**Caveats:** Circuit breakers are per-backend, not per-account. The existing `RateLimitService` handles per-account cooldowns via the `rate_limited_until` column in `backend_accounts`. The circuit breaker operates at a higher level, protecting against scenarios where the entire backend infrastructure is down (not just rate-limited).

### Recommendation 2: Configurable Retry with Exponential Backoff and Jitter

**Recommendation:** Extend the existing retry mechanism in `ExecutionService.schedule_retry()` to support pluggable backoff curves (exponential, linear, constant) with configurable max-retry caps, and replace `threading.Timer` with a SQLite-backed retry scheduler that survives restarts.

**Evidence:**
- AWS Architecture Blog (2015) "Exponential Backoff and Jitter" -- Demonstrates that "full jitter" (uniform random between 0 and exponential backoff cap) outperforms decorrelated jitter and equal jitter in reducing contention. Formula: `sleep = random_between(0, min(cap, base * 2^attempt))`.
- The existing codebase already implements exponential backoff with jitter in `ExecutionService.schedule_retry()` (line 244): `backoff_delay = min(cooldown * 2^(attempt-1), MAX_RETRY_DELAY) + jitter`. This is correct but uses `threading.Timer` which is lost on restart despite the `pending_retries` DB table.
- The frontend `apiFetch` client already implements retry with backoff for HTTP 429/502/503/504 (line 396-432 of `client.ts`), confirming the pattern is well-understood in this codebase.

**Confidence:** HIGH -- Exponential backoff with full jitter is the industry standard. The existing implementation is 80% correct; the gap is replacing threading.Timer with a durable scheduler.

**Expected improvement:** Retries survive server restarts (current partial implementation via `restore_pending_retries()` re-creates timers from DB, but this races with the APScheduler startup). APScheduler-based retry scheduling eliminates this race.

**Caveats:** The current `MAX_RETRY_ATTEMPTS = 5` and `MAX_RETRY_DELAY = 3600` are reasonable defaults. Per-trigger overrides should be stored in the `triggers` table.

### Recommendation 3: SQLite-Backed Execution Queue with Semaphore Concurrency Caps

**Recommendation:** Implement a per-bot execution queue using a SQLite `execution_queue` table for persistence and `threading.Semaphore` per-bot for concurrency enforcement, dispatching queued executions FIFO as capacity frees.

**Evidence:**
- Nygard, M.T. (2018) "Release It! 2nd Edition" -- Chapter 5 "Bulkheads" pattern: isolate resources per integration point to prevent one busy integration from starving others. Per-bot concurrency caps are a bulkhead implementation.
- persist-queue library (GitHub: peter-wangxu/persist-queue, 600+ stars) -- Demonstrates SQLiteQueue with thread-safety for durable FIFO queues. However, adding a dependency for what is essentially one SQL table + a semaphore is not warranted.
- litequeue library (GitHub: litements/litequeue, 100+ stars) -- Even simpler reference: single Python file, uses SQLite table with status column (free/locked/done/failed) and `sqlite3` stdlib. This validates that a custom implementation is straightforward.
- Python `threading.Semaphore` documentation -- Standard primitive for limiting concurrent access. `Semaphore(N)` where N is the per-bot concurrency cap.

**Confidence:** HIGH -- The pattern (SQLite queue + semaphore) is well-established. Custom implementation is justified because the existing codebase uses raw SQLite throughout and already has the connection pattern.

**Expected improvement:** Prevents API rate limit exhaustion from concurrent executions of the same bot. Current behavior: webhook flood can spawn unlimited concurrent executions of the same trigger via `threading.Thread(target=..., daemon=True).start()` (line 1115 of execution_service.py).

### Recommendation 4: SIGSTOP/SIGCONT for Process Pause/Resume

**Recommendation:** Use POSIX `SIGSTOP`/`SIGCONT` signals to pause and resume running subprocess executions, with state tracking in the `execution_logs` table via a new `paused` status value.

**Evidence:**
- POSIX.1-2008 Standard -- `SIGSTOP` cannot be caught, blocked, or ignored; it unconditionally suspends the target process. `SIGCONT` resumes. This is the correct mechanism for pausing subprocesses.
- The existing codebase uses `signal.SIGKILL` and `signal.SIGTERM` via `os.killpg()` for cancellation (ProcessManager, lines 64, 83). Extending to `SIGSTOP`/`SIGCONT` follows the same pattern.
- Python `os.killpg(pgid, signal.SIGSTOP)` and `os.killpg(pgid, signal.SIGCONT)` -- Works on macOS and Linux. Not available on Windows (but the project targets macOS/Linux per platform: darwin).

**Confidence:** HIGH -- POSIX signals are the standard mechanism. The existing PGID-based process group management in `ProcessManager` already handles the process group correctly for this.

**Expected improvement:** Enables pausing executions for rate limit recovery or maintenance windows without losing progress or producing duplicate output.

**Caveats:** SIGSTOP pauses the entire process group. If the subprocess has spawned children (e.g., Claude CLI spawning git), all children are paused. This is generally the desired behavior. Log streaming threads (`_stream_pipe`) will block on `pipe.readline()` while the process is stopped, which is correct -- no output is produced while paused.

### Recommendation 5: Extend Existing HMAC Validation to All Webhook Triggers

**Recommendation:** The webhook HMAC validation infrastructure already exists in `ExecutionService._verify_webhook_hmac()` and `dispatch_webhook_event()`. Extend it to be more visible in the admin UI, support configurable algorithms (SHA-256 default, SHA-1 for legacy), and add per-trigger secret management.

**Evidence:**
- GitHub Webhook Documentation (2024) -- Standard `X-Hub-Signature-256` header with `sha256=` prefix. The existing `verify_github_signature()` in `github_webhook.py` implements this correctly.
- Hookdeck (2024) "How to Implement SHA256 Webhook Signature Verification" -- Confirms the pattern: use `hmac.new(secret, payload, hashlib.sha256).hexdigest()` with `hmac.compare_digest()` for constant-time comparison. The existing implementation already uses `hmac.compare_digest()` (line 1021).
- OWASP Webhook Security Cheat Sheet -- Recommends SHA-256 as minimum, constant-time comparison, and per-webhook secrets rather than a single global secret.

**Confidence:** HIGH -- The implementation already exists and is correct. This is a completion/extension task.

**Expected improvement:** All webhook triggers can independently validate payload signatures, not just the GitHub webhook endpoint.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python `threading` | stdlib | Locks, Semaphores, Timers | Already used throughout the codebase; no external dependency |
| Python `sqlite3` | stdlib | Persistent state (queue, circuit breaker, retries) | Already the sole database layer; consistent with all other persistence |
| Python `signal` | stdlib | SIGSTOP/SIGCONT/SIGTERM/SIGKILL for process control | Already used in ProcessManager |
| Python `hmac` + `hashlib` | stdlib | Webhook signature validation | Already used in both webhook routes |
| APScheduler | >=3.10.0 | Durable retry scheduling (replace threading.Timer) | Already a dependency; used for scheduled triggers |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `threading.Semaphore` | stdlib | Per-bot concurrency caps | Execution queue concurrency enforcement |
| `collections.deque` | stdlib | Bounded in-memory queue | Circuit breaker sliding window failure counter |
| `dataclasses` | stdlib | State objects (CircuitBreakerState, QueueEntry) | Already used for LogLine, ProcessInfo |

### Alternatives Considered

| Instead of | Could Use | Tradeoff | Evidence |
|------------|-----------|----------|----------|
| Custom circuit breaker | pybreaker | pybreaker is decorator-based, designed for wrapping function calls. Our execution model (subprocess.Popen + thread streaming) does not fit the decorator pattern cleanly. Custom is < 100 lines. | pybreaker GitHub docs |
| Custom SQLite queue | persist-queue / litequeue | Adds a dependency for what is a single table + semaphore. The existing codebase has 50+ tables managed via raw SQLite; consistency favors custom. | persist-queue README |
| Custom retry scheduler | Celery / Huey | Massive dependency (Redis/RabbitMQ) for a single-process app. APScheduler is already present. | Full Stack Python task queues comparison |
| threading.Timer (current) | APScheduler one-shot jobs | APScheduler jobs persist via its jobstore configuration; threading.Timer is lost on restart. | APScheduler docs |

**Installation:**
```bash
# No new dependencies needed -- all functionality uses stdlib + existing APScheduler
```

## Architecture Patterns

### Recommended Project Structure

```
backend/app/services/
  circuit_breaker_service.py       # NEW: Per-backend circuit breaker (CLOSED/OPEN/HALF_OPEN)
  execution_queue_service.py       # NEW: Per-bot concurrency queue with SQLite persistence
  execution_service.py             # MODIFY: Integrate circuit breaker checks, queue dispatch
  execution_log_service.py         # MODIFY: Add 'paused' status, remove TTL-based cleanup
  process_manager.py               # MODIFY: Add pause/resume (SIGSTOP/SIGCONT), bulk cancel
  orchestration_service.py         # MODIFY: Wire circuit breaker into fallback chain
  rate_limit_service.py            # EXISTING: Already handles per-account cooldowns

backend/app/db/
  schema.py                        # MODIFY: Add circuit_breaker_state, execution_queue tables
  migrations.py                    # MODIFY: Add migration for new tables/columns
  executions.py                    # NEW: Extract execution DB functions from triggers.py

backend/app/routes/
  executions.py                    # MODIFY: Add pause/resume, bulk cancel, queue visibility
  webhook.py                       # MODIFY: Enhanced HMAC validation visibility
```

### Pattern 1: Circuit Breaker Service

**What:** Stateful service tracking per-backend failure counts with three-state transitions. Persists state to SQLite for restart survival. Integrates with `OrchestrationService.execute_with_fallback()` as a pre-check before attempting execution.

**When to use:** Before dispatching any execution to a backend. Check `CircuitBreakerService.is_available(backend_type)` -- if OPEN, fast-fail immediately.

**Paper reference:** Nygard (2007) "Release It!" Chapter 5; AWS Circuit Breaker Pattern.

**Example:**
```python
# Source: Nygard "Release It!" + pybreaker reference implementation
import threading
import time
from collections import deque
from enum import Enum

class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreakerService:
    """Per-backend circuit breaker with SQLite-persisted state."""

    # {backend_type: CircuitState}
    _states: dict = {}
    _failure_counts: dict = {}
    _last_failure_times: dict = {}
    _lock = threading.Lock()

    # Configurable thresholds
    FAIL_THRESHOLD = 5          # Consecutive failures before OPEN
    RESET_TIMEOUT = 60          # Seconds before OPEN -> HALF_OPEN
    HALF_OPEN_MAX_CALLS = 1     # Trial calls in HALF_OPEN before deciding

    @classmethod
    def is_available(cls, backend_type: str) -> bool:
        """Check if backend is available (CLOSED or HALF_OPEN trial)."""
        with cls._lock:
            state = cls._states.get(backend_type, CircuitState.CLOSED)
            if state == CircuitState.CLOSED:
                return True
            if state == CircuitState.OPEN:
                last_fail = cls._last_failure_times.get(backend_type, 0)
                if time.time() - last_fail >= cls.RESET_TIMEOUT:
                    cls._states[backend_type] = CircuitState.HALF_OPEN
                    return True  # Allow trial call
                return False  # Still in cooldown
            # HALF_OPEN: allow trial
            return True

    @classmethod
    def record_success(cls, backend_type: str) -> None:
        """Record successful execution -- reset to CLOSED."""
        with cls._lock:
            cls._states[backend_type] = CircuitState.CLOSED
            cls._failure_counts[backend_type] = 0
        # Persist to DB
        cls._persist_state(backend_type, CircuitState.CLOSED, 0)

    @classmethod
    def record_failure(cls, backend_type: str) -> None:
        """Record failed execution -- increment counter, possibly transition to OPEN."""
        with cls._lock:
            count = cls._failure_counts.get(backend_type, 0) + 1
            cls._failure_counts[backend_type] = count
            cls._last_failure_times[backend_type] = time.time()
            if count >= cls.FAIL_THRESHOLD:
                cls._states[backend_type] = CircuitState.OPEN
        cls._persist_state(backend_type, cls._states.get(backend_type), count)
```

### Pattern 2: Execution Queue with Concurrency Caps

**What:** SQLite-backed FIFO queue with `threading.Semaphore(N)` per-bot. New executions are enqueued; a dispatcher thread dequeues and dispatches as capacity frees. Queue depth is queryable for admin UI.

**When to use:** When `trigger.max_concurrent_executions` is set (default: 1 for safety). The queue wraps the existing `OrchestrationService.execute_with_fallback()` call.

**Paper reference:** Nygard (2018) "Release It! 2nd Edition" Chapter 5 "Bulkheads".

**Example:**
```python
# Source: Nygard "Bulkheads" + Python threading.Semaphore docs
import threading
from ..database import get_connection

class ExecutionQueueService:
    """Per-bot execution queue with SQLite persistence and concurrency caps."""

    _semaphores: dict = {}  # {trigger_id: threading.Semaphore}
    _lock = threading.Lock()

    DEFAULT_CONCURRENCY = 1  # Default max concurrent executions per bot

    @classmethod
    def get_semaphore(cls, trigger_id: str, max_concurrent: int = None) -> threading.Semaphore:
        with cls._lock:
            if trigger_id not in cls._semaphores:
                cap = max_concurrent or cls.DEFAULT_CONCURRENCY
                cls._semaphores[trigger_id] = threading.Semaphore(cap)
            return cls._semaphores[trigger_id]

    @classmethod
    def enqueue(cls, trigger_id: str, trigger: dict, message_text: str,
                event: dict, trigger_type: str) -> str:
        """Enqueue an execution. Returns queue entry ID."""
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO execution_queue (trigger_id, trigger_json, message_text, "
                "event_json, trigger_type, status) VALUES (?, ?, ?, ?, ?, 'pending')",
                (trigger_id, json.dumps(trigger), message_text,
                 json.dumps(event), trigger_type)
            )
            conn.commit()
        # Signal dispatcher
        cls._dispatch_next(trigger_id)

    @classmethod
    def _dispatch_next(cls, trigger_id: str):
        """Try to dispatch the next queued execution if capacity is available."""
        sem = cls.get_semaphore(trigger_id)
        if sem.acquire(blocking=False):
            # Capacity available -- dequeue and execute
            entry = cls._dequeue(trigger_id)
            if entry:
                thread = threading.Thread(
                    target=cls._execute_and_release,
                    args=(trigger_id, entry, sem),
                    daemon=True,
                )
                thread.start()
            else:
                sem.release()  # Nothing to dispatch
```

### Pattern 3: Pause/Resume via SIGSTOP/SIGCONT

**What:** Extend ProcessManager with `pause()` and `resume()` methods that send POSIX signals to the process group. Track paused state in both `ProcessManager._processes` and the `execution_logs` DB table.

**When to use:** User-initiated pause (admin UI button) or automatic pause on rate limit detection before retry scheduling.

**Example:**
```python
# Source: POSIX.1-2008 signal handling + existing ProcessManager pattern
@classmethod
def pause(cls, execution_id: str) -> bool:
    """Pause a running execution via SIGSTOP."""
    with cls._lock:
        info = cls._processes.get(execution_id)
    if not info or info.process.poll() is not None:
        return False
    try:
        os.killpg(info.pgid, signal.SIGSTOP)
        return True
    except (ProcessLookupError, OSError):
        return False

@classmethod
def resume(cls, execution_id: str) -> bool:
    """Resume a paused execution via SIGCONT."""
    with cls._lock:
        info = cls._processes.get(execution_id)
    if not info:
        return False
    try:
        os.killpg(info.pgid, signal.SIGCONT)
        return True
    except (ProcessLookupError, OSError):
        return False
```

### Anti-Patterns to Avoid

- **Unbounded retry loops:** The existing `MAX_RETRY_ATTEMPTS = 5` prevents this. Never remove the cap. Evidence: Nygard "Release It!" warns about "cascading failures" from unbounded retries.
- **Circuit breaker per-request instead of per-backend:** Circuit breakers protect integration points (backends), not individual requests. A per-execution circuit breaker would defeat the purpose.
- **In-memory-only queue state:** If the queue is only in memory, server restart drops all queued executions. The existing `pending_retries` table demonstrates the correct pattern: persist to SQLite, restore on startup.
- **Polling-based queue dispatch:** Do not poll the queue table periodically. Use event-driven dispatch: enqueue signals the dispatcher immediately. Only use polling as a startup recovery mechanism.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Backoff calculation | Custom math | `min(base * 2^attempt, cap) + uniform_random(0, jitter)` formula from AWS blog | Well-studied formula; the existing implementation already uses this correctly |
| HMAC comparison | `==` operator | `hmac.compare_digest()` | Prevents timing attacks; already used in existing code |
| Process group management | Manual PID tracking | `start_new_session=True` + `os.getpgid()` + `os.killpg()` | Already implemented correctly in ProcessManager |
| Scheduled job persistence | Custom timer persistence | APScheduler with SQLiteJobStore | APScheduler is already a dependency; its jobstore handles persistence natively |
| Webhook signature format | Custom header parsing | Follow provider conventions (`sha256=<hex>` prefix) | Already correctly implemented for GitHub; extend to generic webhooks |

**Key insight:** Most resilience mechanisms in this phase are about completing partially-implemented patterns (DB-backed retries, HMAC validation, execution history) rather than building from scratch. The codebase has the right patterns; it needs durable persistence and admin visibility.

## Common Pitfalls

### Pitfall 1: Race Between Timer Restore and New Execution

**What goes wrong:** On server restart, `restore_pending_retries()` re-creates `threading.Timer` objects for DB-persisted retries. If a webhook arrives during restore, both the timer and the new webhook can trigger execution for the same trigger simultaneously.

**Why it happens:** The current implementation (lines 290-376 of execution_service.py) restores timers in sequence during `create_app()`. Webhook routes are registered afterward, but the server starts accepting requests before all timers are restored.

**How to avoid:** Use APScheduler one-shot jobs instead of `threading.Timer`. APScheduler's internal locking prevents duplicate execution. Alternatively, use the execution queue's concurrency cap to serialize.

**Warning signs:** Duplicate executions for the same trigger after server restart.

### Pitfall 2: SQLite Write Contention Under Load

**What goes wrong:** Multiple threads writing to the execution queue, circuit breaker state, and execution logs simultaneously hit SQLite's single-writer constraint. With `busy_timeout=5000`, writers queue up but can still timeout under sustained load.

**Why it happens:** SQLite serializes all writes through a single lock. The existing `get_connection()` opens a new connection per call with no pooling.

**How to avoid:** Keep DB writes minimal and fast. Batch log writes (the existing pattern of buffering in memory and flushing on completion is correct). For the queue table, use INSERT/UPDATE only (no complex transactions). WAL mode (already enabled) helps by allowing concurrent reads during writes.

**Warning signs:** `sqlite3.OperationalError: database is locked` errors in logs.

### Pitfall 3: SIGSTOP on macOS vs Linux Behavior Differences

**What goes wrong:** On macOS, `SIGSTOP` to a process group works correctly but the process may not resume cleanly if the terminal session changes. On Linux in containers, SIGSTOP may be blocked by the container runtime's seccomp profile.

**Why it happens:** Container runtimes (Docker) often restrict signal handling. macOS has slightly different process group semantics than Linux.

**How to avoid:** Always check `process.poll()` after SIGCONT to verify the process actually resumed. Add a timeout to the resume operation. Document that pause/resume requires native process support (not Docker without `--init`).

**Warning signs:** Process appears paused but `poll()` returns non-None after resume.

### Pitfall 4: Circuit Breaker Flapping

**What goes wrong:** Backend has intermittent failures (e.g., 50% success rate). Circuit breaker oscillates rapidly between OPEN and HALF_OPEN/CLOSED, causing unpredictable behavior.

**Why it happens:** The `HALF_OPEN_MAX_CALLS = 1` setting means a single success resets the circuit, but the next failure immediately starts counting toward OPEN again.

**How to avoid:** Use a sliding window for failure rate calculation instead of consecutive failure count. Require N consecutive successes in HALF_OPEN before transitioning to CLOSED. Nygard recommends a "slow ramp" in HALF_OPEN.

**Warning signs:** Rapid state transitions visible in audit logs.

### Pitfall 5: Queue Starvation from Long-Running Executions

**What goes wrong:** With concurrency cap of 1, a long-running execution (up to 3600s timeout) blocks all queued executions for that bot. Queue grows unboundedly.

**Why it happens:** The semaphore is held for the entire execution duration.

**How to avoid:** Set maximum queue depth per bot (e.g., 50). Reject new enqueue requests with 429 when queue is full. Display queue depth prominently in admin UI so operators can intervene.

**Warning signs:** Queue depth growing continuously without dispatch.

## Experiment Design

### Recommended Experimental Setup

**Independent variables:**
- Circuit breaker threshold (fail_max): 3, 5, 10
- Retry backoff curve: exponential, linear, constant
- Queue concurrency cap per bot: 1, 2, 5
- Backoff jitter strategy: full jitter, equal jitter, no jitter

**Dependent variables:**
- Time-to-recovery after backend outage (circuit breaker)
- Retry success rate under transient failures
- Queue throughput (executions/minute) at concurrency caps
- Maximum queue depth before rejection under load

**Controlled variables:**
- Backend response time (mocked)
- Failure rate (mocked)
- Server restart timing

**Baseline comparison:**
- Method: Current implementation with no circuit breaker, in-memory-only retries, unbounded concurrent executions
- Expected performance: Under sustained 50% failure rate, current system wastes 50% of execution attempts with full timeout waits
- Our target: Circuit breaker fast-fails within 1ms after threshold; retries converge within 3 attempts for transient failures

**Ablation plan:**
1. Circuit breaker only vs. full resilience stack -- tests whether circuit breaker alone reduces wasted execution attempts
2. SQLite queue vs. in-memory-only queue -- tests restart durability (kill server mid-queue, verify recovery)
3. Exponential vs. linear backoff -- tests convergence speed under different failure patterns

**Statistical rigor:**
- Number of runs: 5 per configuration (execution is deterministic given mocked backend responses)
- Confidence intervals: Mean +/- 2 standard deviations
- Significance testing: Not applicable (deterministic system behavior given fixed inputs)

### Recommended Metrics

| Metric | Why | How to Compute | Baseline |
|--------|-----|----------------|----------|
| Fast-fail rate | Circuit breaker effectiveness | `(fast_failed_requests / total_requests_during_outage) * 100` | 0% (no circuit breaker) |
| Retry convergence | Backoff effectiveness | Attempts until first success after transient failure | N/A (retries exist but incomplete) |
| Queue depth at steady state | Concurrency cap effectiveness | `SELECT COUNT(*) FROM execution_queue WHERE status = 'pending'` | N/A (no queue exists) |
| Restart recovery time | Persistence effectiveness | Time from server start to first queued execution dispatched | 0 (no queue; retries lost without DB) |
| HMAC rejection rate | Webhook security | `(rejected_webhooks / total_webhooks) * 100` | Partial (GitHub only) |

## Verification Strategy

### Recommended Verification Tiers for This Phase

| Item | Recommended Tier | Rationale |
|------|-----------------|-----------|
| Circuit breaker transitions (CLOSED->OPEN->HALF_OPEN->CLOSED) | Level 1 (Sanity) | Unit test with mocked failures; deterministic |
| Retry mechanism retries and succeeds on transient failure | Level 1 (Sanity) | Unit test with mocked backend; inject failure then success |
| Execution queue enforces concurrency cap | Level 1 (Sanity) | Unit test with threading; verify semaphore blocks |
| Queue persists across restart | Level 2 (Proxy) | Integration test: enqueue, kill process, restart, verify queue intact |
| Pause/resume preserves execution state | Level 2 (Proxy) | Integration test with real subprocess; SIGSTOP then SIGCONT |
| Cancellation terminates within 5 seconds | Level 2 (Proxy) | Integration test with real subprocess; measure time from cancel to status change |
| HMAC rejects invalid signatures | Level 1 (Sanity) | Unit test; send payload with wrong signature |
| Execution history survives restart | Level 2 (Proxy) | Integration test: create execution, restart, query history |
| Admin UI shows queue depth | Level 3 (Deferred) | Manual or E2E test; requires running frontend |

**Level 1 checks to always include:**
- Circuit breaker state transitions are correct under all failure/success sequences
- Retry count increments and caps at MAX_RETRY_ATTEMPTS
- HMAC validation accepts valid signatures and rejects invalid ones
- Queue entry is created in DB on enqueue
- Execution status persists to DB on finish

**Level 2 proxy metrics:**
- Server restart recovery: kill server with queued items, restart, verify all items dispatched
- Concurrent execution limit: fire 10 webhooks simultaneously, verify only N execute concurrently
- Pause/resume: start execution, pause, wait 5s, resume, verify output is complete and correct

**Level 3 deferred items:**
- Admin UI queue depth visualization
- Admin UI retry queue browser
- Full load test with sustained webhook flood
- Cross-platform pause/resume verification (macOS + Linux)

## Production Considerations (from KNOWHOW.md)

The KNOWHOW.md file is empty (initialized but not populated). The following considerations are derived from the CONCERNS.md codebase analysis.

### Known Failure Modes

- **In-memory state lost on restart (CONCERNS.md 7.2):** 10+ services use class-level dicts for state. This phase directly addresses this for execution tracking, retry scheduling, and queue state by moving to SQLite persistence.
  - Prevention: Every new stateful service must have a SQLite persistence layer with `restore_on_startup()` method.
  - Detection: Health endpoint should report unrecovered in-memory state.

- **SQLite write contention (CONCERNS.md 2.1):** Concurrent writes from multiple execution threads can timeout. WAL mode + `busy_timeout=5000` mitigates but does not eliminate.
  - Prevention: Keep DB transactions short. Batch log writes. Use INSERT-only for queue/retry tables (no UPDATE transactions spanning multiple rows).
  - Detection: Monitor `sqlite3.OperationalError` rate in logs.

- **Thread proliferation (CONCERNS.md 2.4):** Each execution spawns 3-4 threads (stdout reader, stderr reader, budget monitor, optional kill timer). Adding queue dispatcher and retry scheduler threads increases this further.
  - Prevention: Queue dispatcher is a single long-lived thread per bot, not per-execution. Retry scheduler uses APScheduler (already one thread).
  - Detection: Monitor `threading.active_count()` in health endpoint.

### Scaling Concerns

- **At current scale (single user, few bots):** SQLite persistence is sufficient. Threading.Semaphore provides correct concurrency control. Circuit breaker with defaults (fail_max=5, reset_timeout=60) works well.

- **At production scale (multi-user, many bots):** SQLite becomes a bottleneck. The queue and circuit breaker tables would need to move to PostgreSQL or Redis. The per-bot semaphore pattern scales to hundreds of bots (each semaphore is lightweight -- just a counter + condition variable).

### Common Implementation Traps

- **Forgetting to release semaphore on exception:** The queue dispatch method must release the semaphore in a `finally` block, not just on success. The existing `try/finally` pattern in `OrchestrationService` (lines 185-206) is the correct reference.
  - Correct approach: `try: execute() finally: semaphore.release()`

- **Circuit breaker not distinguishing failure types:** A 404 (not found) is not a backend failure. Only 5xx errors and timeouts should trip the circuit breaker. Rate limits (429) are handled by `RateLimitService` separately.
  - Correct approach: Circuit breaker watches for exit codes indicating backend unavailability, not application-level errors.

- **HMAC validation before JSON parsing:** The raw payload bytes must be captured before Flask parses JSON. The existing `request.get_data()` call in `webhook.py` (line 45) correctly captures raw bytes. Do not change this order.

## Code Examples

Verified patterns from official sources and existing codebase:

### Webhook HMAC Validation (Existing Pattern)
```python
# Source: backend/app/services/execution_service.py lines 1013-1021
# Already correctly implemented -- extend to support configurable algorithms
@staticmethod
def _verify_webhook_hmac(raw_payload: bytes, signature_header: str, secret: str) -> bool:
    if not signature_header.startswith("sha256="):
        return False
    expected = signature_header[7:]
    computed = hmac.new(secret.encode("utf-8"), raw_payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, expected)
```

### Retry with Exponential Backoff (Existing Pattern)
```python
# Source: backend/app/services/execution_service.py lines 241-246
# Already correctly implemented -- migrate from threading.Timer to APScheduler
jitter = random.uniform(0, min(10, cooldown_seconds))
backoff_delay = (
    min(cooldown_seconds * (2 ** (attempt_count - 1)), cls.MAX_RETRY_DELAY) + jitter
)
```

### DB Persistence Pattern (Existing Pattern)
```python
# Source: backend/app/db/connection.py -- standard get_connection() usage
from ..database import get_connection

def persist_circuit_state(backend_type: str, state: str, failure_count: int):
    with get_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO circuit_breaker_state
               (backend_type, state, failure_count, last_updated)
               VALUES (?, ?, ?, datetime('now'))""",
            (backend_type, state, failure_count)
        )
        conn.commit()
```

### Process Cancellation (Existing Pattern)
```python
# Source: backend/app/services/process_manager.py lines 75-116
# Graceful cancel: SIGTERM -> wait -> SIGKILL. Extend with SIGSTOP/SIGCONT.
@classmethod
def cancel_graceful(cls, execution_id: str, sigterm_timeout: float = 10.0) -> bool:
    with cls._lock:
        info = cls._processes.get(execution_id)
        cls._cancelled.add(execution_id)
    if not info:
        return False
    try:
        os.killpg(info.pgid, signal.SIGTERM)
        # Schedule SIGKILL fallback
        timer = threading.Timer(sigterm_timeout, lambda: _force_kill(info))
        timer.daemon = True
        timer.start()
        return True
    except ProcessLookupError:
        return True
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact | Reference |
|--------------|------------------|--------------|--------|-----------|
| In-memory retry timers | DB-persisted retry queue with scheduler | Phase 13 | Retries survive restarts | Nygard "Release It!" |
| Unbounded concurrent execution | Per-bot semaphore concurrency caps | Phase 13 | Prevents rate limit exhaustion | Nygard "Bulkheads" |
| No circuit breaker | Three-state circuit breaker per backend | Phase 13 | Fast-fail on backend outage | Nygard "Circuit Breaker" |
| In-memory execution status | SQLite-persisted execution state | Phase 13 | History survives restart, no TTL | CONCERNS.md 7.2 |
| threading.Timer (fragile) | APScheduler one-shot jobs (durable) | Phase 13 | Restart-safe scheduling | APScheduler docs |

**Deprecated/outdated:**
- `ExecutionLogService._start_times` + `STALE_EXECUTION_THRESHOLD`: This cleanup mechanism becomes unnecessary once execution state is fully DB-persisted. The `cleanup_stale_executions()` method can be simplified to query DB for `status='running'` records older than threshold and mark them as failed.

## Open Questions

1. **Should the circuit breaker be per-backend-type or per-account?**
   - What we know: `RateLimitService` already handles per-account rate limiting. Circuit breakers traditionally protect integration points (i.e., backend types like "claude", "gemini").
   - What's unclear: If one Claude account is broken but another is fine, should the circuit breaker trip? The fallback chain already handles account rotation.
   - Recommendation: Per-backend-type is correct. Per-account rate limiting is already handled. The circuit breaker is for infrastructure-level outages (e.g., Anthropic API is down for all accounts).

2. **What is the maximum queue depth before rejection?**
   - What we know: Unbounded queues are an anti-pattern (Nygard "Steady State"). But too small a cap drops legitimate work.
   - What's unclear: Expected webhook volume per bot in production usage.
   - Recommendation: Default to 50 per bot, configurable via `triggers.max_queue_depth`. Return 429 with queue depth in response when full.

3. **Should pause/resume persist across server restart?**
   - What we know: SIGSTOP pauses the process. If the server restarts, the process is orphaned (it was started with `start_new_session=True` so it survives parent death).
   - What's unclear: Should the server attempt to re-attach to orphaned paused processes on restart?
   - Recommendation: No. Orphaned processes should be killed on restart (the existing `ProcessManager.cancel_all()` in shutdown handles this). Pause/resume is a session-scoped operation.

4. **Should workflow execution history enhancement be part of this phase or deferred?**
   - What we know: `workflow_executions` and `workflow_node_executions` tables already exist with status tracking. The `WorkflowExecutionService` already persists node-level status via `update_workflow_node_execution()`.
   - What's unclear: The requirement (RES-09) asks for "history views, failure debugging, and execution pattern analytics" which may require additional frontend work beyond this phase's scope.
   - Recommendation: Backend persistence is already largely complete (tables exist, writes happen). This phase should add any missing columns (e.g., `duration_ms`, `retry_count` on node executions) and ensure the admin UI route exposes queryable history. Frontend analytics visualization can be a separate concern.

## Sources

### Primary (HIGH confidence)
- Nygard, M.T. (2007, 2nd ed. 2018) "Release It! Design and Deploy Production-Ready Software" -- Pragmatic Bookshelf. Chapters 4-5: Stability Anti-patterns and Stability Patterns (Circuit Breaker, Bulkheads, Timeouts, Steady State).
- AWS Prescriptive Guidance "Circuit Breaker Pattern" (2024) -- https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/circuit-breaker.html
- AWS Architecture Blog "Exponential Backoff and Jitter" (2015) -- Full jitter formula and comparative analysis.
- Python `signal` module documentation -- POSIX signal handling for SIGSTOP/SIGCONT/SIGTERM/SIGKILL.
- POSIX.1-2008 Standard -- Signal semantics for process group management.
- Existing codebase (`backend/app/services/`) -- Current implementation patterns verified by reading source code directly.

### Secondary (MEDIUM confidence)
- pybreaker library (GitHub: danielfm/pybreaker, 1.2k stars) -- Reference Python circuit breaker implementation. Used for API validation, not direct dependency.
- persist-queue library (GitHub: peter-wangxu/persist-queue, 600+ stars) -- Reference SQLite-backed queue implementation. Used for pattern validation.
- litequeue library (GitHub: litements/litequeue, 100+ stars) -- Minimal SQLite queue. Validates that custom implementation is straightforward.
- Hookdeck "SHA256 Webhook Signature Verification" (2024) -- https://hookdeck.com/webhooks/guides/how-to-implement-sha256-webhook-signature-verification

### Tertiary (LOW confidence)
- Blog posts on circuit breaker implementations in Python (Medium, Substack) -- Conceptual alignment only, not used for specific recommendations.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All recommendations use stdlib or existing dependencies (APScheduler). No new dependencies needed.
- Architecture: HIGH - Patterns follow existing codebase conventions (class-level state + threading.Lock + SQLite persistence). No architectural changes required.
- Paper recommendations: HIGH - Circuit breaker and bulkhead patterns are 17+ years old with extensive production validation. Backoff with jitter has formal analysis from AWS.
- Pitfalls: HIGH - Derived from direct codebase analysis (CONCERNS.md) and established literature. Race conditions between timer restore and request handling observed in current code.

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (stable domain; resilience patterns do not change rapidly)
