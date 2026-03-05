# Phase 13: Execution Resilience & Infrastructure - Research

**Researched:** 2026-03-04
**Domain:** Execution engine hardening -- circuit breakers, retry mechanisms, queuing, persistent state, pause/resume, cancellation, webhook validation
**Confidence:** HIGH

## Summary

This phase hardens the existing execution engine, which already has substantial infrastructure: SQLite-backed execution logs, a `ProcessManager` for subprocess lifecycle, an `OrchestrationService` for fallback chain execution with account rotation, rate limit detection and retry scheduling (with DB persistence via `pending_retries` table), webhook deduplication, and per-trigger timeout and cancellation support.

The primary gaps are: (1) no formal circuit breaker state machine -- the current approach retries up to 5 times with exponential backoff but lacks the OPEN/HALF-OPEN/CLOSED state transitions that fast-fail new requests during outages; (2) no execution queue with per-bot concurrency caps -- dispatches fire immediately on background threads without queuing; (3) no pause/resume for running executions -- only cancel exists; (4) webhook HMAC validation exists per-trigger but has no global enforcement or configurable algorithm; (5) execution state is already persisted to SQLite (no TTL limitation), but workflow execution history lacks per-node status analytics queries.

**Primary recommendation:** Build the circuit breaker and execution queue as native Python modules (no external library dependencies) using SQLite for state persistence, extending the existing `ExecutionService` / `OrchestrationService` architecture. Use SIGSTOP/SIGCONT signals for pause/resume. Extend the existing HMAC validation to support configurable algorithms and global enforcement.

## Paper-Backed Recommendations

Every recommendation below cites specific evidence.

### Recommendation 1: Three-State Circuit Breaker with Configurable Thresholds

**Recommendation:** Implement a per-backend circuit breaker with CLOSED/OPEN/HALF-OPEN states, configurable failure threshold (default 5), recovery timeout (default 60s), and success threshold for HALF-OPEN to CLOSED transition.

**Evidence:**
- Nygard, M.T. (2018) "Release It! 2nd Edition" (Pragmatic Bookshelf) -- Chapter 5: Stability Patterns. Describes the circuit breaker as "the most effective pattern to combat cascading failures" alongside timeouts. The pattern prevents a failing integration point from cascading into system-wide collapse by fast-failing requests during the OPEN state.
- Fowler, M. (2014) "Circuit Breaker" (martinfowler.com) -- Describes the three-state model: CLOSED (normal), OPEN (fast-fail), HALF-OPEN (trial). Notes that the breaker should be "observable" so operators can monitor state transitions.
- PyBreaker library (v1.4.1, 2025) -- Production implementation of Nygard's pattern. Default: fail_max=5, reset_timeout=60. Supports excluded exceptions (business logic errors should not trip the breaker).

**Confidence:** HIGH -- Established pattern with multiple production implementations and authoritative references.
**Expected improvement:** Eliminates cascading failure during AI backend outages; reduces wasted subprocess spawns from N (all queued executions) to 0 during outage.
**Caveats:** Circuit breaker should be per-backend-type (claude, opencode, gemini, codex), not global. Each backend can fail independently. Excluded exceptions must include non-transient errors (bad prompt, missing CLI).

### Recommendation 2: Exponential Backoff Retry with Jitter and SQLite-Backed Queue

**Recommendation:** Extend the existing `schedule_retry` mechanism to handle all transient failures (not just rate limits), with configurable max retries, backoff curve, and jitter. Persist retry queue to SQLite (extending existing `pending_retries` table).

**Evidence:**
- AWS Architecture Blog (2024) "Exponential Backoff And Jitter" -- Full jitter produces the best results in reducing contention and total completion time compared to equal jitter or decorrelated jitter. Formula: `sleep = random_between(0, base * 2^attempt)`, capped at MAX_DELAY.
- Nygard (2018) -- Retries without backoff create "thundering herd" effects. Jitter decorrelates retry timing across independent callers.
- Current codebase already implements: `backoff_delay = min(cooldown * 2^(attempt-1), MAX_RETRY_DELAY) + jitter` in `ExecutionService.schedule_retry()`. The existing implementation handles rate-limit retries well but does not cover HTTP 502/503/timeout transient errors from the subprocess execution itself.

**Confidence:** HIGH -- Existing implementation validated; extension is incremental.
**Expected improvement:** Transient AI backend failures (502, 503, connection timeout) automatically recover without user intervention.
**Caveats:** Must distinguish transient errors (retryable) from permanent errors (bad prompt, missing CLI). The existing `pending_retries` table schema (keyed by `trigger_id`) allows only one pending retry per trigger -- this is acceptable for rate-limit retries but may need relaxation for general transient failure retries.

### Recommendation 3: SQLite-Backed Execution Queue with Per-Bot Concurrency Caps

**Recommendation:** Implement an execution queue backed by SQLite with per-trigger concurrency limits. Use a dispatcher thread that polls the queue and starts executions up to the concurrency cap, dispatching FIFO as capacity frees.

**Evidence:**
- persist-queue library (v1.1.0, 2025) -- Demonstrates SQLite-backed queue with WAL mode, thread-safe access, and crash recovery. Architecture: dedicated writer thread, items persisted before acknowledgment.
- The current codebase dispatches executions on fire-and-forget daemon threads (`threading.Thread(target=..., daemon=True); thread.start()`). This means there is no concurrency control -- if 10 webhooks arrive simultaneously for the same trigger, 10 subprocess.Popen calls fire concurrently.

**Confidence:** HIGH -- Pattern well-established; SQLite WAL mode provides the needed concurrency characteristics.
**Expected improvement:** Prevents resource exhaustion from concurrent bot executions; enables predictable system load.
**Caveats:** Queue depth visibility requires an admin API endpoint and frontend UI component. Polling interval introduces latency (recommend 1-second poll). Consider `PRAGMA journal_mode=WAL` for the queue table.

### Recommendation 4: SIGSTOP/SIGCONT for Subprocess Pause/Resume

**Recommendation:** Use Unix signals SIGSTOP (pause) and SIGCONT (resume) to implement pause/resume for running executions, leveraging the existing `ProcessManager` which already tracks process groups via `os.getpgid()`.

**Evidence:**
- Python subprocess documentation (3.14) -- `Popen.send_signal(signal)` sends a signal to the child process. SIGSTOP suspends execution; SIGCONT resumes it. Process group signals via `os.killpg(pgid, signal)` affect the entire process tree.
- Kizirian, K. (2019) "Time-slicing applications with SIGCONT and SIGSTOP" -- Demonstrates reliable pause/resume using these signals for long-running CLI processes. Process state is preserved by the kernel; no data loss occurs.

**Confidence:** HIGH -- SIGSTOP/SIGCONT are POSIX standards. The codebase already uses `os.killpg()` for cancellation via SIGTERM/SIGKILL.
**Expected improvement:** Operators can pause long-running executions to free resources or debug, then resume without losing progress.
**Caveats:** SIGSTOP is not available on Windows. The platform is macOS/Linux (Darwin 25.3.0), so this is not a concern. Paused state must be tracked in the database (new status value). SSE streaming should continue heartbeats during pause but indicate paused state. Log buffering continues to accumulate lines from before the pause.

### Recommendation 5: HMAC-SHA256 Webhook Validation with Replay Protection

**Recommendation:** Extend the existing per-trigger HMAC validation (`_verify_webhook_hmac` in `ExecutionService` and `verify_github_signature` in `github_webhook.py`) to a unified webhook signature validation service with configurable algorithm, timestamp-based replay protection, and 403 response for invalid signatures.

**Evidence:**
- webhooks.fyi "HMAC Security" -- Industry standard for webhook security. Recommends SHA-256 minimum, timing-safe comparison (Python `hmac.compare_digest`), and replay protection via timestamp validation.
- GitHub webhook documentation -- Uses `sha256=<hex>` format in `X-Hub-Signature-256` header. The codebase already implements this correctly.
- Current codebase has two separate HMAC implementations: one in `github_webhook.py` (GitHub-specific) and one in `ExecutionService._verify_webhook_hmac()` (general webhooks). Both use SHA-256 and `hmac.compare_digest`. The gap is: no replay protection, no configurable algorithm selection, no centralized validation service.

**Confidence:** HIGH -- Existing implementations are correct; consolidation and enhancement are straightforward.
**Expected improvement:** Eliminates replay attacks; provides consistent security posture across all webhook endpoints.
**Caveats:** Replay protection requires a timestamp header and configurable tolerance window (recommend 5 minutes). Not all webhook providers include timestamps -- make this optional and per-trigger configurable.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `threading` | 3.10+ | Thread-safe circuit breaker, queue dispatcher | Already used extensively in codebase |
| Python stdlib `signal` | 3.10+ | SIGSTOP/SIGCONT for pause/resume | POSIX standard; already used for SIGTERM/SIGKILL |
| Python stdlib `hmac` + `hashlib` | 3.10+ | HMAC-SHA256 webhook validation | Already used in two places in codebase |
| SQLite3 (via `app.db.connection`) | 3.39+ | Persistent queue, execution state, retry queue | Already the sole database; WAL mode available |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pybreaker` | 1.4.1 | Third-party circuit breaker | Only if custom implementation proves insufficient; adds Redis support for distributed deployments |
| `persist-queue` | 1.1.0 | Third-party SQLite queue | Only if custom queue has bugs; reference implementation for API design |

### Alternatives Considered

| Instead of | Could Use | Tradeoff | Evidence |
|------------|-----------|----------|----------|
| Custom circuit breaker | `pybreaker` 1.4.1 | Adds dependency but provides Redis backing, listeners, excluded exceptions out-of-box | PyBreaker well-maintained (1.4K GitHub stars), but custom is simpler for single-process Flask app |
| Custom SQLite queue | `persist-queue` 1.1.0 | Production-tested SQLite queue, but adds dependency and may not fit custom concurrency cap logic | persist-queue designed for generic FIFO, not per-trigger concurrency caps |
| SIGSTOP/SIGCONT | Checkpoint/restart | Full state serialization vs. kernel-level pause | SIGSTOP is simpler, zero-overhead, but no cross-machine migration |

**Installation:**
```bash
# No new dependencies needed -- all stdlib + existing SQLite
# Optional (only if custom implementation proves insufficient):
# cd backend && uv add pybreaker persist-queue
```

## Architecture Patterns

### Recommended Project Structure
```
backend/app/
  services/
    circuit_breaker_service.py    # Circuit breaker state machine per backend
    execution_queue_service.py    # SQLite-backed queue with per-trigger concurrency
    webhook_validation_service.py # Unified HMAC validation with replay protection
    execution_service.py          # Extended: integrates circuit breaker and queue
    process_manager.py            # Extended: pause/resume via SIGSTOP/SIGCONT
    execution_log_service.py      # Extended: paused state support
  db/
    circuit_breakers.py           # Circuit breaker state persistence
    execution_queue.py            # Queue table CRUD
    schema.py                     # Extended: new tables
  routes/
    executions.py                 # Extended: pause/resume/bulk-cancel endpoints
```

### Pattern 1: Circuit Breaker State Machine

**What:** A per-backend circuit breaker that wraps `OrchestrationService.execute_with_fallback()`. The breaker tracks consecutive failures per backend type and fast-fails new requests when OPEN.

**When to use:** Before dispatching any execution to a backend.

**Reference:** Nygard (2018), Chapter 5; Fowler "Circuit Breaker" (2014).

**Example:**
```python
# Source: Nygard (2018) + pybreaker API design
class CircuitBreakerState:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    def __init__(self, backend_type: str, fail_max: int = 5,
                 reset_timeout: int = 60, success_threshold: int = 1):
        self.backend_type = backend_type
        self.fail_max = fail_max
        self.reset_timeout = reset_timeout
        self.success_threshold = success_threshold
        self._state = CircuitBreakerState.CLOSED
        self._fail_count = 0
        self._success_count = 0
        self._last_failure_time = None
        self._lock = threading.Lock()

    def can_execute(self) -> bool:
        with self._lock:
            if self._state == CircuitBreakerState.CLOSED:
                return True
            if self._state == CircuitBreakerState.OPEN:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.reset_timeout:
                    self._state = CircuitBreakerState.HALF_OPEN
                    self._success_count = 0
                    return True  # Allow trial request
                return False  # Fast-fail
            if self._state == CircuitBreakerState.HALF_OPEN:
                return True  # Allow trial requests

    def record_success(self):
        with self._lock:
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = CircuitBreakerState.CLOSED
                    self._fail_count = 0
            else:
                self._fail_count = 0  # Reset on success in CLOSED

    def record_failure(self):
        with self._lock:
            self._fail_count += 1
            self._last_failure_time = time.time()
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._state = CircuitBreakerState.OPEN
            elif self._fail_count >= self.fail_max:
                self._state = CircuitBreakerState.OPEN
```

### Pattern 2: SQLite-Backed Execution Queue with Dispatcher

**What:** Incoming execution requests are inserted into a SQLite queue table. A background dispatcher thread polls the queue and starts executions up to the per-trigger concurrency cap.

**When to use:** Replaces the current fire-and-forget `threading.Thread(target=..., daemon=True)` dispatch.

**Reference:** persist-queue (2025) architecture; SQLite WAL mode for concurrent access.

**Example:**
```python
# Source: persist-queue architecture + Agented conventions
class ExecutionQueueService:
    """SQLite-backed execution queue with per-trigger concurrency control."""

    _dispatcher_thread: threading.Thread = None
    _stop_event = threading.Event()

    @classmethod
    def enqueue(cls, trigger: dict, message_text: str,
                event: dict = None, trigger_type: str = "webhook") -> str:
        """Add execution to queue. Returns queue_entry_id."""
        # Insert into execution_queue table
        # Returns immediately -- dispatcher handles actual execution
        pass

    @classmethod
    def _dispatcher_loop(cls):
        """Background thread: poll queue, respect concurrency caps, dispatch."""
        while not cls._stop_event.is_set():
            pending = get_pending_queue_entries()
            for entry in pending:
                trigger_id = entry["trigger_id"]
                # Check concurrency cap for this trigger
                running = count_running_for_trigger(trigger_id)
                cap = get_concurrency_cap(trigger_id)  # default: 1
                if running < cap:
                    cls._dispatch(entry)
            cls._stop_event.wait(timeout=1.0)  # 1-second poll
```

### Pattern 3: Process Pause/Resume via SIGSTOP/SIGCONT

**What:** Extend `ProcessManager` with `pause()` and `resume()` methods that send SIGSTOP/SIGCONT to the process group.

**When to use:** When an operator wants to temporarily halt a long-running execution.

**Reference:** Python subprocess docs; POSIX signal specification.

**Example:**
```python
# Source: Python subprocess docs + existing ProcessManager pattern
@classmethod
def pause(cls, execution_id: str) -> bool:
    """Pause a running execution by sending SIGSTOP to process group."""
    with cls._lock:
        info = cls._processes.get(execution_id)
    if not info:
        return False
    try:
        os.killpg(info.pgid, signal.SIGSTOP)
        return True
    except ProcessLookupError:
        return False

@classmethod
def resume(cls, execution_id: str) -> bool:
    """Resume a paused execution by sending SIGCONT to process group."""
    with cls._lock:
        info = cls._processes.get(execution_id)
    if not info:
        return False
    try:
        os.killpg(info.pgid, signal.SIGCONT)
        return True
    except ProcessLookupError:
        return False
```

### Anti-Patterns to Avoid

- **Global circuit breaker:** Each backend type must have its own breaker. A single global breaker would cause all backends to fail when only one is down.
- **Retry without backoff:** Always use exponential backoff with jitter. Linear or fixed-interval retries create thundering herd effects (Nygard 2018).
- **Unbounded queue depth:** Always set a maximum queue depth per trigger. Without it, a burst of webhooks can exhaust memory and disk.
- **Pause without timeout:** A paused execution that is never resumed will hold resources indefinitely. Implement an auto-resume timeout (e.g., 30 minutes).
- **HMAC validation after JSON parsing:** Always validate HMAC against raw bytes before parsing JSON. The current codebase does this correctly (`request.get_data()` before `request.get_json()`).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Timing-safe string comparison | Custom byte-by-byte compare | `hmac.compare_digest()` | Constant-time comparison prevents timing attacks; stdlib implementation is audited |
| Cryptographic hashing | Custom hash functions | `hashlib.sha256` | Cryptographic primitives must not be hand-rolled; SHA-256 is unbroken as of 2025 |
| Process group management | Manual PID tracking | `os.getpgid()` + `start_new_session=True` | Already used in codebase; kernel handles child processes correctly |
| Thread-safe locking | Custom spinlocks | `threading.Lock()` / `threading.RLock()` | GIL + Lock provides sufficient safety for SQLite access patterns |

**Key insight:** This phase builds infrastructure patterns (circuit breaker, queue, retry), not algorithms. The patterns are well-established and should follow canonical designs (Nygard 2018, Fowler 2014) rather than novel approaches. The value is in correct integration with the existing codebase, not in innovation.

## Common Pitfalls

### Pitfall 1: Circuit Breaker Trips on Non-Transient Errors

**What goes wrong:** The circuit breaker counts a "bad prompt" error (permanent failure) as a backend failure and trips, blocking all legitimate executions.
**Why it happens:** Not distinguishing transient errors (502, 503, timeout, rate limit) from permanent errors (invalid command, missing CLI, bad prompt).
**How to avoid:** Define an explicit list of "excluded exceptions" that do NOT increment the failure counter. For this codebase: `FileNotFoundError` (CLI not installed), exit codes that indicate prompt/auth errors (non-zero but not 502/503/timeout patterns).
**Warning signs:** Circuit breaker stays OPEN even though the backend is healthy. Check `fail_count` source -- if it includes non-transient errors, the classification is wrong.
**Reference:** PyBreaker `excluded_exceptions` parameter; Nygard (2018) Chapter 5.

### Pitfall 2: Retry Queue Grows Unbounded on Sustained Outage

**What goes wrong:** During a prolonged backend outage, every webhook creates a retry entry. When the backend recovers, all retries fire simultaneously (thundering herd).
**Why it happens:** No cap on total retry queue depth, and retries are scheduled with absolute timestamps rather than relative delays.
**How to avoid:** (1) Cap total retry queue depth per trigger (e.g., 10 pending retries). (2) Use the circuit breaker to reject new dispatches before they enter the retry queue. (3) On recovery, stagger retry execution with additional jitter.
**Warning signs:** `pending_retries` table has hundreds of rows for one trigger. Memory usage climbs from Timer objects.
**Reference:** AWS "Exponential Backoff And Jitter" (2024).

### Pitfall 3: Paused Execution Holds Resources Forever

**What goes wrong:** An operator pauses an execution but forgets to resume it. The subprocess is stopped (SIGSTOP) but still holds memory, file handles, and network connections.
**Why it happens:** No timeout on paused state.
**How to avoid:** Implement a configurable auto-resume timeout (default 30 minutes). After timeout, either auto-resume or auto-cancel with appropriate status.
**Warning signs:** Multiple executions in "paused" status for extended periods. Monitor via admin UI.

### Pitfall 4: Queue Dispatcher Stalls on Database Lock

**What goes wrong:** The queue dispatcher thread holds a SQLite write lock while dispatching, blocking webhook handlers from inserting new queue entries.
**Why it happens:** Long-running transactions or forgetting to commit.
**How to avoid:** Keep dispatcher transactions short: read pending entries (SELECT), release connection, then dispatch. Use WAL mode for concurrent read/write.
**Warning signs:** Webhook latency spikes when queue is being processed. 5xx errors on webhook endpoint.

### Pitfall 5: Bulk Cancellation Race with Normal Completion

**What goes wrong:** A bulk cancel request races with an execution that is completing normally. The execution finishes with "success" but the cancel also marks it as "cancelled".
**Why it happens:** Status update is not atomic (no compare-and-swap).
**How to avoid:** The codebase already has `update_execution_status_cas()` (compare-and-swap) in `triggers.py`. Use this for all status transitions: `UPDATE ... WHERE status = 'running'`.
**Warning signs:** Execution appears as both "success" and "cancelled" in logs. Check for non-CAS status updates.

## Experiment Design

### Recommended Experimental Setup

**Independent variables:**
- Circuit breaker failure threshold (3, 5, 10)
- Circuit breaker recovery timeout (30s, 60s, 120s)
- Queue concurrency cap per trigger (1, 2, 5)
- Retry backoff base (30s, 60s, 120s)

**Dependent variables:**
- Time to detect backend failure (circuit opens)
- Time to recover after backend restored (circuit closes)
- Queue throughput under load (executions/minute)
- Retry success rate for transient failures
- System resource usage during queue buildup

**Controlled variables:**
- Backend type (test with claude backend)
- Webhook payload size
- Trigger configuration

**Baseline comparison:**
- Current behavior: no circuit breaker, no queue, fire-and-forget threads, rate-limit-only retries
- Target: zero cascading failures during backend outage, 100% transient failure recovery, bounded resource usage

**Statistical rigor:**
- Number of runs: 3 per configuration
- Measure: mean and p95 for time-to-detect, time-to-recover
- No formal significance testing needed -- this is infrastructure, not ML

### Recommended Metrics

| Metric | Why | How to Compute | Baseline |
|--------|-----|----------------|----------|
| Circuit breaker trip latency | Time from first failure to OPEN state | `time(state=OPEN) - time(first_failure)` | N/A (no breaker currently) |
| Retry success rate | % of transient failures recovered by retry | `successful_retries / total_retries * 100` | Current rate-limit retry: unknown |
| Queue wait time (p95) | Latency from enqueue to dispatch | `dispatch_time - enqueue_time` at 95th percentile | N/A (no queue currently) |
| Concurrent execution count | Active subprocesses per trigger | `ProcessManager.get_active_count()` | Unbounded |
| Webhook rejection rate | % of webhooks with invalid HMAC | `rejected / total * 100` | Per-trigger only |

## Verification Strategy

### Recommended Verification Tiers for This Phase

| Item | Recommended Tier | Rationale |
|------|-----------------|-----------|
| Circuit breaker transitions CLOSED->OPEN after N failures | Level 1 (Sanity) | Unit test with mock failures |
| Circuit breaker auto-recovers to CLOSED after timeout | Level 1 (Sanity) | Unit test with time.sleep or mocked clock |
| Retry mechanism retries transient 502/503/timeout | Level 2 (Proxy) | Integration test with mock subprocess |
| Retry queue survives server restart | Level 2 (Proxy) | Test: insert retry, restart app, verify retry fires |
| Execution queue enforces concurrency cap | Level 2 (Proxy) | Fire N concurrent webhooks, verify only cap executions run |
| Pause/resume preserves execution state | Level 2 (Proxy) | Start execution, SIGSTOP, SIGCONT, verify output continues |
| Cancellation marks status within 5 seconds | Level 1 (Sanity) | Existing test pattern; add timing assertion |
| Webhook HMAC rejects invalid signatures with 403 | Level 1 (Sanity) | Unit test: send bad HMAC, assert 403 |
| Execution history persists to SQLite, no TTL | Level 1 (Sanity) | Already true -- verify no cleanup job truncates recent history |
| Workflow node execution history queryable | Level 2 (Proxy) | Run workflow, query node statuses, verify completeness |
| Queue depth visible in admin API | Level 1 (Sanity) | GET endpoint returns queue depth |
| Bulk cancel by filter | Level 2 (Proxy) | Start 3 executions, bulk cancel, verify all cancelled within 5s |

**Level 1 checks to always include:**
- Circuit breaker state transitions (CLOSED/OPEN/HALF-OPEN) with assertions on failure count
- HMAC validation with valid/invalid/missing signature
- Execution status persisted to SQLite (no in-memory-only state)
- Queue entry insertion and retrieval

**Level 2 proxy metrics:**
- End-to-end retry: mock subprocess that fails once then succeeds -- verify final status is "success"
- Concurrency cap: enqueue 5 executions for trigger with cap=2, verify only 2 run concurrently
- Pause/resume: start subprocess, pause, wait 5s, resume, verify output after resume

**Level 3 deferred items:**
- Load testing with sustained webhook bursts (hundreds of concurrent webhooks)
- Circuit breaker behavior under real AI backend failures (requires production-like environment)
- Queue performance at scale (thousands of pending entries)

## Production Considerations (from KNOWHOW.md)

KNOWHOW.md is currently empty (initialized but not populated). The following considerations are derived from codebase analysis.

### Known Failure Modes

- **Stale "running" executions after server restart:** The codebase already handles this in `mark_stale_executions_interrupted()` called from `init_db()`. Circuit breaker state must also be reset on server restart (persist last known state to SQLite, but reset to CLOSED).
  - Prevention: Persist circuit breaker state to SQLite; on startup, check if recovery timeout has elapsed.
  - Detection: Admin UI shows circuit breaker states per backend.

- **Thread leak from retry timers:** Each `schedule_retry()` call creates a `threading.Timer` with `daemon=True`. If many retries are scheduled concurrently, timer threads accumulate.
  - Prevention: Cap total pending retries per trigger (existing `MAX_RETRY_ATTEMPTS=5`). Queue replaces ad-hoc timer creation.
  - Detection: Monitor active thread count via `/health/readiness`.

- **SQLite write contention under high webhook volume:** The execution queue dispatcher and webhook handlers both write to the same SQLite database.
  - Prevention: Use WAL mode (already configured in connection module). Keep write transactions short. Queue reads should be separate from queue writes.
  - Detection: Monitor 5xx error rate on webhook endpoint. Log SQLite `OperationalError: database is locked`.

### Scaling Concerns

- **At current scale (low webhook volume):** Single-threaded dispatcher with 1-second poll is sufficient. SQLite WAL handles concurrent access.
- **At production scale (high webhook volume):** Consider switching queue storage to a dedicated SQLite database file (separate from main DB) to reduce lock contention. If volume exceeds SQLite capabilities (~100 writes/second), migrate to a message broker (Redis, PostgreSQL LISTEN/NOTIFY).

### Common Implementation Traps

- **Mixing circuit breaker and retry logic:** The circuit breaker should gate entry to the execution pipeline. Retries happen after the circuit breaker check. If the breaker is OPEN, the execution should be queued for later (not retried immediately).
  - Correct approach: Check circuit breaker -> if OPEN, enqueue with delay -> if CLOSED/HALF-OPEN, dispatch -> on failure, record in breaker and optionally retry.

- **Race between pause and completion:** If an execution completes in the milliseconds between the pause signal and the status update, the execution ends up in an inconsistent state.
  - Correct approach: Use compare-and-swap (`update_execution_status_cas`) for all status transitions. Only pause if current status is "running".

## Code Examples

Verified patterns from official sources and the existing codebase:

### HMAC Validation (Already in Codebase)
```python
# Source: backend/app/services/execution_service.py lines 1011-1021
@staticmethod
def _verify_webhook_hmac(raw_payload: bytes, signature_header: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature for a webhook payload."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = signature_header[7:]
    computed = hmac.new(secret.encode("utf-8"), raw_payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, expected)
```

### Compare-and-Swap Status Update (Already in Codebase)
```python
# Source: backend/app/db/triggers.py lines 786-821
def update_execution_status_cas(
    execution_id: str,
    new_status: str,
    expected_status: str = "running",
    **kwargs,
) -> bool:
    """Update execution status only if current status matches expected."""
    # ... atomic UPDATE WHERE status = expected_status
```

### Process Group Signal (Already in Codebase)
```python
# Source: backend/app/services/process_manager.py lines 82-83
os.killpg(info.pgid, signal.SIGTERM)  # Existing: graceful cancel
# Extension for pause/resume:
os.killpg(info.pgid, signal.SIGSTOP)  # Pause
os.killpg(info.pgid, signal.SIGCONT)  # Resume
```

### Circuit Breaker Integration Point
```python
# Source: Pattern from Nygard (2018) + existing OrchestrationService
# In orchestration_service.py execute_with_fallback():
breaker = CircuitBreakerService.get_breaker(backend_type)
if not breaker.can_execute():
    # Fast-fail: enqueue for later instead of blocking
    ExecutionQueueService.enqueue(trigger, message_text, event, trigger_type)
    return ExecutionResult(
        status=ExecutionStatus.CIRCUIT_OPEN,
        detail=f"Circuit breaker OPEN for {backend_type}"
    )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact | Reference |
|--------------|------------------|--------------|--------|-----------|
| In-memory execution tracking with TTL | SQLite-persisted execution logs | Already implemented in codebase | Execution history survives restart | Codebase: `execution_logs` table |
| No rate limit handling | Rate limit detection + retry with backoff | Already implemented | Rate-limited executions auto-retry | Codebase: `schedule_retry()` + `pending_retries` table |
| Manual webhook secret checking | Per-trigger HMAC validation | Already implemented | Each trigger can have its own webhook secret | Codebase: `webhook_secret` column + `_verify_webhook_hmac()` |
| No cancellation | SIGTERM + SIGKILL graceful cancel | Already implemented | Users can cancel running executions | Codebase: `ProcessManager.cancel_graceful()` |

**What this phase adds:**
- Circuit breaker state machine (NEW)
- Execution queue with concurrency caps (NEW)
- General transient failure retry (EXTENDS existing rate-limit retry)
- Pause/resume (NEW -- extends existing signal infrastructure)
- Bulk cancellation (EXTENDS existing single cancel)
- Unified webhook validation service (CONSOLIDATES two existing implementations)
- Workflow node execution analytics queries (EXTENDS existing tables)

## Open Questions

1. **Concurrency cap default value**
   - What we know: Current system has no concurrency limit. Some triggers (security audit) are resource-intensive.
   - What's unclear: What is the appropriate default concurrency cap per trigger? Should it be 1 (serial execution) or higher?
   - Recommendation: Default to 1 (serial). Users can increase via admin UI. This is the safest default -- prevents resource exhaustion.

2. **Circuit breaker granularity**
   - What we know: Breaker should be per-backend-type. But accounts within a backend can have different health states.
   - What's unclear: Should circuit breakers be per-backend-type or per-account?
   - Recommendation: Per-backend-type initially. The existing `RateLimitService` already handles per-account health. Combining both provides defense in depth without excessive complexity.

3. **Queue persistence scope**
   - What we know: The existing `pending_retries` table stores retry state for rate-limit failures. A new queue table is needed for general execution queuing.
   - What's unclear: Should the execution queue and retry queue be unified into one table or kept separate?
   - Recommendation: Keep separate. The execution queue is FIFO with concurrency control. The retry queue has backoff delays and attempt counting. Different access patterns warrant different tables.

4. **Pause timeout default**
   - What we know: Paused processes hold resources. Need an auto-resume/cancel timeout.
   - What's unclear: What is a reasonable default timeout for paused executions?
   - Recommendation: 30 minutes default, configurable per trigger via `timeout_seconds` (or a new `pause_timeout_seconds` column). After timeout, auto-cancel with status "pause_timeout".

## Sources

### Primary (HIGH confidence)
- Nygard, M.T. (2018) "Release It! 2nd Edition" Pragmatic Bookshelf -- Circuit breaker pattern, stability patterns, retry with backoff
- Fowler, M. (2014) "Circuit Breaker" martinfowler.com -- Three-state model, observability
- Python 3.14 subprocess documentation -- SIGSTOP/SIGCONT signal handling, process groups
- Python 3.14 hmac/hashlib documentation -- HMAC-SHA256, compare_digest
- webhooks.fyi "HMAC Security" -- Webhook signature validation best practices

### Secondary (MEDIUM confidence)
- PyBreaker v1.4.1 (PyPI, Sep 2025) -- Production circuit breaker API design reference
- circuitbreaker v2.1.3 (PyPI, Mar 2025) -- Alternative circuit breaker with monitoring
- persist-queue v1.1.0 (PyPI, Oct 2025) -- SQLite-backed queue reference implementation
- AWS "Exponential Backoff And Jitter" (2024) -- Full jitter backoff strategy
- Kizirian (2019) "Time-slicing applications with SIGCONT and SIGSTOP" -- Pause/resume demonstration

### Tertiary (LOW confidence)
- None -- all findings verified with primary or secondary sources.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all stdlib, no new dependencies required
- Architecture: HIGH -- extends existing patterns; circuit breaker and queue are well-established
- Paper recommendations: HIGH -- Nygard (2018) is the canonical reference; implementations validated via PyPI packages
- Pitfalls: HIGH -- derived from codebase analysis and established literature
- Experiment design: MEDIUM -- metrics are sound but baselines are theoretical (no current measurements)

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (stable domain -- infrastructure patterns change slowly)
