# Hardening Audit 06 — Orchestration, Message Bus & Scheduling

Scope: agent/team orchestration, message bus, schedulers, goal/ralph/workflow loops,
and process management under `backend/app/services/`. Concurrency, runaway-loop,
leak, deadlock, backpressure, and silent-failure focus.

Severity counts: **CRITICAL 2 · HIGH 6 · MEDIUM 7 · LOW 4**

---

## CRITICAL

### C1 — Message-bus subscriber queues are unbounded; no backpressure on slow/disconnected SSE clients
**File:** `agent_message_bus_service.py:171-189` (`_push_to_subscriber`), `:25` (`_subscribers`)

**Problem:** Each subscriber gets an unbounded `Queue()` (`:196`). `_push_to_subscriber`
does `q.put(event)` for every recipient queue with no `maxsize` and no drop policy. If an
SSE consumer stops draining (browser tab frozen, network stall) but the HTTP connection
stays half-open, the queue grows without bound for every broadcast — a single chatty
broadcaster can OOM the worker. Broadcast (`_send_broadcast`, `:120-159`) amplifies this:
one send fans out to every SuperAgent's queue. There is no per-queue size cap, no
oldest-drop, and no "subscriber too slow → disconnect" path.

**Fix:** Use `Queue(maxsize=N)` (e.g. 1000) and `put_nowait` inside a `try/except Full`:
on `Full`, drop the oldest (`get_nowait` then `put_nowait`) or evict the subscriber and
push a `stream_overflow` sentinel so the client reconnects and re-reads from DB. Persisted
messages already survive (status stays `pending`), so dropping the live event is safe.

### C2 — `_subscribers` map never evicts empty agent keys; grows monotonically
**File:** `agent_message_bus_service.py:199-201`, `:217-223`

**Problem:** `subscribe()` does `cls._subscribers[agent_id] = []` on first subscribe and
the `finally` block only `remove(queue)` — it never deletes the now-empty list nor the
`agent_id` key. Over a long-lived process every agent that ever connected leaves a
permanent empty-list entry. Combined with `_push_to_subscriber` iterating `.get(agent_id, [])`
this is a slow but unbounded memory leak keyed by distinct agent IDs.

**Fix:** In the `finally` cleanup, after `remove`, `if not cls._subscribers[agent_id]: del cls._subscribers[agent_id]`.
Same pattern applies to `AgentConversationService._subscribers` / `_conversations` /
`_start_times` (`agent_conversation_service.py:74-78`) — verify those have a sweeper; if
the documented cleanup-by-`_start_times` sweep is missing, they leak identically.

---

## HIGH

### H1 — Goal loop: no per-iteration token/cost budget guard; only iteration + wall caps
**File:** `goal_loop_runner.py:249-250`, `:275-460`

**Problem:** The loop terminates on `max_iterations` (default 20) and `max_wall_seconds`
(default 1800), but there is **no cost/token budget cap**. Each iteration calls
`GoalJudgeService.judge` (an LLM call recording `tokens_in/out/cost_usd` at `:355-358`)
plus the agent turn itself. A misconfigured large `max_iterations` × expensive model can
burn unbounded spend within the 30-min window with no abort. Unlike `OrchestrationService`,
the goal loop does not consult `BudgetService`.

**Fix:** Accumulate `verdict.cost_usd` into `state` and add a termination branch
(`reason="budget_cap"`) when a configured `max_cost_usd` is exceeded. Also wrap the loop
in a `BudgetService.check_budget` gate before each continue, mirroring orchestration.

### H2 — Ralph monitor: `git log` subprocess runs on a 30s timer with no overlap/runaway guard, and the poll thread is never joined
**File:** `ralph_monitor_service.py:98-165`, `:62-76`, `_get_latest_commit:188-208`

**Problem:** (a) The monitor thread is stored in `state["thread"]` but `stop_monitoring`
(`:167-176`) only sets `active=False` and pops the entry — it never `join()`s the thread,
so on rapid start/stop churn threads accumulate until their next 30s wake. (b) Each cycle
shells out to `git log` with a 5s timeout; under a slow/locked git repo the effective cycle
stretches and `no_progress_count` semantics drift (the "30s" assumption is violated).
(c) `while True: time.sleep(30)` means a fast stop still waits up to 30s — not interruptible.

**Fix:** Replace `time.sleep(30)` with a per-monitor `threading.Event.wait(30)` set on stop
for prompt, interruptible exit; optionally `join(timeout=...)` in `stop_monitoring`. Document
that git latency can stretch the cycle and base progress on wall-clock deltas, not cycle count.

### H3 — `_run_strategy` / team execution: cleanup relies solely on a 5-min daemon `threading.Timer`; lost on restart → `_executions` entries leak
**File:** `team_execution_service.py:160-180`, `team_execution_tracker.py:14`

**Problem:** `TeamExecutionTracker._executions` entries are only removed by a
`threading.Timer(300, cleanup_execution)` scheduled in `_run_strategy`'s `finally`. If the
process restarts between finalize and timer fire, or if `_run_strategy` is killed before the
`finally` runs (daemon thread killed at shutdown), the in-memory entry leaks. There is no
startup sweep and no size cap on `_executions`. `pending_approval` entries whose approval
event never fires and never time out also persist indefinitely (no timeout enforcer is
visible in this service — it depends on `execute_human_in_loop` to call `set_approval_timeout`).

**Fix:** Prefer `SchedulerService` `date` jobs (as `workflow_execution_service._schedule_cleanup`
already does at `:613-636`) so cleanup survives daemon teardown; add a periodic sweep that
evicts terminal entries older than N minutes and caps map size.

### H4 — Workflow per-node timeout leaks the worker thread (no cancellation); thread keeps running after `RuntimeError`
**File:** `workflow_node_executor.py:57-86`, `workflow_execution_service.py:773-801`

**Problem:** `dispatch_node_with_timeout` runs the handler in a daemon thread and
`join(timeout=...)`. On timeout it raises `RuntimeError` but **the daemon thread is never
cancelled** — a node executing a long `subprocess.run` (command/script/agent node) keeps
running in the background, holding its subprocess, after the workflow has already recorded
the node as timed-out and moved on (or failed). Multiple timeouts → accumulating orphan
threads and orphan subprocesses. Python cannot force-kill threads, so the underlying
subprocess must be killed explicitly.

**Fix:** Pass a cancellation token / process handle into the node executor so on timeout the
executor can `proc.kill()` the subprocess group. At minimum, plumb `node_timeout_seconds`
into the `subprocess.run(timeout=...)` call itself (command/script nodes already accept a
`timeout` config but the *node-level* timeout is enforced only by the thread-join, not the
subprocess), so the subprocess dies with the node.

### H5 — Goal loop runner: silent crash kills the autonomous loop with no restart/alert
**File:** `goal_loop_runner.py:456-460`

**Problem:** The entire `_run` body is wrapped in `except Exception: logger.error(...)`. Any
unexpected error (e.g. a DB write in `record_goal_loop_iteration_complete`, a judge
exception not caught internally) terminates the loop silently — the session is left running
with no driver, no `goal_loop_ended` broadcast, and the operator sees a "stuck" session that
never progresses. Same shape in `ralph_monitor` cycle (`:217 except Exception`) where a
single bad cycle... is actually caught per-cycle there, but the goal loop catch is loop-fatal.

**Fix:** Move the `try/except` *inside* the `while` loop so a single bad iteration is logged
and the loop continues (or terminates cleanly with `reason="runner_error"` + broadcast),
rather than dying silently. Emit a `goal_loop_ended{reason:"error"}` in the outer `finally`
when no clean end was broadcast.

### H6 — `AgentSchedulerService._maybe_resume`: non-atomic read-modify-write across two lock acquisitions; lost update on concurrent eval
**File:** `agent_scheduler_service.py:294-345`

**Problem:** `_maybe_resume` mutates `_session_states[key]` under `_lock`, releases the lock,
then re-acquires it to read `current` for the DB persist (`:340-343`). Between release and
re-acquire, another `evaluate_all_accounts` call (or `_set_state` from a different thread)
can overwrite the same key. The persisted `upsert_agent_session` then writes a snapshot that
may not match the intended transition (e.g. a `stopped` re-stamp racing a `queued` resume),
yielding DB/cache divergence. `_set_state` (`:228-280`) has the same release-then-persist
gap. The whole evaluate loop assumes single-threaded poll invocation but nothing enforces it.

**Fix:** Hold `_lock` across the mutate **and** capture the values to persist in the same
critical section (persist the captured snapshot outside the lock, but compute it inside).
Guard `evaluate_all_accounts` with a non-reentrant "evaluation in progress" flag so
overlapping poll callbacks cannot interleave.

---

## MEDIUM

### M1 — Scheduler `_execute_trigger` updates `last_run_at` BEFORE checking enabled/existence
**File:** `scheduler_service.py:213-225`

**Problem:** `update_trigger_last_run(...)` is called (`:217`) before the trigger is
re-fetched and the enabled/existence checks run (`:219-224`). A disabled or deleted trigger
still records a phantom "last run" each time its (still-registered) cron fires. Also, a
deleted trigger's job is not unscheduled here, so the cron keeps firing and stamping.

**Fix:** Move `update_trigger_last_run` after the existence + enabled checks. On
"trigger not found", call `unschedule_trigger` to remove the orphan job.

### M2 — Workflow `cleanup_stale_executions` only runs at startup; long-running daemon orphans not swept
**File:** `workflow_execution_service.py:330-372`

**Problem:** Stale `running`/`pending_approval` rows are only reconciled at server startup.
If `_run_workflow`'s daemon thread dies mid-run without hitting its `finally`-equivalent
finalize (it has no try/finally around the whole body — see M3), the DB row stays `running`
and the in-memory entry stays until the 5-min cleanup, but the DB is never corrected until
the next restart.

**Fix:** Wrap `_run_workflow` body in try/except that, on unexpected exception, marks the
execution `failed` in both memory and DB before returning.

### M3 — `_run_workflow` has no top-level exception guard; an unexpected error leaves status `running` forever
**File:** `workflow_execution_service.py:388-610`

**Problem:** The method handles `CycleError` and per-node errors, but an exception outside
those paths (e.g. a DB failure in `add_workflow_node_execution`, a `model_dump_json` error)
propagates out of the daemon thread → no `update_workflow_execution(..., failed)`, no
cleanup scheduled. The execution is permanently `running` in DB until restart.

**Fix:** Add an outer `try/except Exception` that finalizes the execution as `failed`,
emits completion, and schedules cleanup.

### M4 — `team_monitor` polling thread + watchdog observer both broadcast; no dedupe and observer not always joined
**File:** `team_monitor_service.py:148-260`

**Problem:** Both the watchdog handler and the 5s polling loop independently parse and
`_broadcast` config/task updates. They share `last_config_mtime`/`known_task_files` only
within the polling loop — the watchdog path (`TeamFileHandler._process_event`) does **not**
consult mtime state, so a single file change can broadcast twice (once per path) and the two
paths can race to double-emit. Polling loop uses `while True: time.sleep(5)` (non-interruptible
stop, up to 5s lag). Observer is joined on stop, but the poll thread is never joined.

**Fix:** Gate watchdog broadcasts through the same mtime-tracking helper used by polling so
duplicates are suppressed; use `Event.wait(5)` for prompt stop.

### M5 — `ProcessManager._cancelled` set grows unbounded
**File:** `process_manager.py:31`, `:62`, `:108`

**Problem:** `_cancelled` is a module-level `set` that `cancel`/`cancel_graceful`/
`_auto_cancel_paused` add to. `cleanup` does `_cancelled.discard(execution_id)`, but if
`cleanup` is never called for a cancelled execution (e.g. the runner thread died), the entry
leaks. Over a long uptime with many cancellations this set grows slowly without bound.

**Fix:** Bound it (e.g. evict on cleanup is already there — ensure cleanup is always called),
or use a TTL-bounded structure. Confirm every cancel path is paired with a guaranteed cleanup.

### M6 — `ProcessManager.register` pgid-fallback can send kill signals to the wrong/own process group
**File:** `process_manager.py:35-58`

**Problem:** If the child exits between `Popen` and `register`, `os.getpgid` raises
`ProcessLookupError` and the code falls back to `pgid = process.pid`. If that pid has since
been recycled, or if the child was not started with `start_new_session=True`, `killpg(pgid)`
later could signal an unrelated group — or the server's own group. The warning is logged but
the unsafe pgid is still stored and later used by `cancel`/`pause`/`resume`.

**Fix:** On `ProcessLookupError`, mark the ProcessInfo as "untracked-pgid" and refuse to
`killpg` it (only `process.kill()` the specific pid, or skip). Verify children are spawned
with `start_new_session=True` so `pid == pgid` holds.

### M7 — Goal loop `recent_iteration_verdicts` convergence read is a check-then-act over DB without the runner's own lock
**File:** `goal_loop_runner.py:428-452`

**Problem:** Convergence termination reads `recent_iteration_verdicts(session_id, ...)` from
DB and decides to stop. This is benign for a single-runner-per-session model (enforced by
`start_runner` idempotency at `:181-191`), but the idempotency guard and the DB read are not
coordinated — a `stop_runner` racing the convergence branch could double-broadcast
`goal_loop_ended`. Low blast radius but worth a guard.

**Fix:** Check `state.stop_event.is_set()` immediately before each `_broadcast_end` /
`stop_session` (already done before the judge record at `:333`, but not before the cap /
convergence ends).

---

## LOW

### L1 — `agent_service.run_agent` joins background thread for 2s then returns possibly-None execution_id
**File:** `agent_service.py:183-204`

**Problem:** Uses a shared dict + `thread.join(timeout=2.0)` to grab `execution_id`. If
`run_trigger` takes >2s to allocate the id, the API returns `execution_id: None` while the
agent actually runs — the caller cannot track or cancel it. Mild correctness/observability
gap, not a leak (daemon thread completes on its own).

**Fix:** Have `run_trigger` allocate the id synchronously before forking the background work,
or return a tracking handle rather than racing on a join timeout.

### L2 — `scheduler_service` relies on APScheduler `coalesce=True`/`max_instances=1` but team/workflow strategies fan out their own threads
**File:** `scheduler_service.py:99-105`, `_execute_team:278-300`

**Problem:** `max_instances=1` prevents overlapping *scheduler* invocations, but
`_execute_team` returns immediately after spawning `TeamExecutionService.execute_team`
(which forks a daemon thread). So `max_instances=1` does not prevent two overlapping *team
runs* if the previous run's daemon thread is still executing when the next cron fires. The
missed-run coalescing also silently swallows skipped runs with no audit row.

**Fix:** Track in-flight team/workflow runs and skip-or-log when a prior run is still active;
emit an audit row on coalesced/skipped scheduled runs.

### L3 — `workflow_node_executor._execute_command_node` truncates stderr to 200 chars in the error but the thread/subprocess timeout is the only guard against hangs
**File:** `workflow_node_executor.py:128-170`

**Problem:** Minor — relies entirely on `subprocess.run(timeout=...)`; a command that ignores
SIGTERM and spawns its own children (no process-group kill here, unlike ProcessManager) can
leave orphan grandchildren after `TimeoutExpired`. `subprocess.run` kills only the direct
child.

**Fix:** Use `start_new_session=True` + `os.killpg` on timeout, or `Popen` with explicit
process-group teardown for command/script nodes.

### L4 — `team_monitor` / `ralph_monitor` swallow all polling-loop exceptions with bare `pass`
**File:** `team_monitor_service.py:206-207, 226-227, 230-231`

**Problem:** Three `except Exception: pass` blocks in the polling loop hide real errors
(permission changes, corrupt JSON beyond the parser's own catch, broadcast failures). The
loop keeps running but operators get no signal that monitoring degraded.

**Fix:** Replace bare `pass` with `logger.debug(..., exc_info=True)` (rate-limited) so
persistent failures are observable without flooding logs.

---

## Notes / non-issues verified

- `ProcessManager` pause/resume correctly use DB CAS (`update_execution_status_cas`) to avoid
  pause/complete races — good pattern.
- `goal_loop_runner` and `workflow` both correctly check `_cancelled`/`stop_event` inside the
  loop and have iteration + wall-time/timeout caps (the gap is *budget*, not loop-bound — H1).
- `agent_message_bus._background_worker` correctly uses `_shutdown_event.wait(60)` for an
  interruptible sweep and catches per-cycle exceptions — good.
- `TeamExecutionTracker.approve_execution` correctly sets the event outside the lock to avoid
  the waiter-wakes-and-needs-lock deadlock — good pattern, replicated correctly in
  `workflow_execution_service.approve_node`.
- `scheduler_service` uses `pytz.UTC` for the scheduler and resolves per-trigger tz — no naive
  clock assumption beyond DST-edge cron semantics (acceptable).
