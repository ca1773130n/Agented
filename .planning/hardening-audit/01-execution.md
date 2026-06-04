# Hardening Audit — Subprocess / Execution Layer

Scope: `backend/app/services/` execution + process + PTY + CLI-runner + worktree
modules. Focus: command injection, process/FD leaks, missing timeouts, unbounded
growth, concurrency races, silent failures, path traversal, missing cleanup.

Verdict: No `shell=True` anywhere; all `subprocess` calls use list-argv form, so
classic shell command injection is largely absent. The real risks are **process /
file-descriptor / temp-dir leaks**, **unbounded in-memory buffers and SSE queues**,
one **shell-script-write injection** in the OAuth flow, and several **blocking reads
without hard wall-clock bounds**.

---

## CRITICAL

### C1. Unquoted path interpolated into a generated shell script (OAuth fake-browser)
**File:** `backend_cli_service.py:171-175`
```python
_fb.write(f'#!/bin/sh\necho "$1" >> {_url_file}\necho "$1"\nsleep 300 &\n')
```
`_url_file` is interpolated **unquoted** into a `/bin/sh` script that is later
`execvp`'d as `BROWSER`. Today `_url_file` comes from `tempfile.mkdtemp(prefix="agented-oauth-")`,
so it is currently safe — but the value is one refactor away from being attacker- or
config-influenced (e.g. a configurable temp root, `TMPDIR`, or a per-account path),
and a space or shell metachar in the path silently breaks the redirect or executes
arbitrary commands. This is a latent command-injection sink.
**Fix:** Do not template the path into shell. Either pass it via an env var the
script reads (`echo "$1" >> "$URL_FILE"` with `URL_FILE` exported), or `shlex.quote()`
the path. Prefer writing a tiny Python helper script instead of `/bin/sh`.

### C2. OAuth temp dir + fake-browser script are never cleaned up (disk + inode leak)
**File:** `backend_cli_service.py:166-175` (created) — no corresponding removal in
`_finish_session` (`:1031-1060`) or `_cleanup_completed` (`:1063-1067`).
Every login session `mkdtemp`s a directory containing `browser` + `url.txt` and
**never removes it**. Over time this is an unbounded accumulation of temp dirs (one
per login attempt) holding captured OAuth URLs (sensitive) on disk indefinitely.
**Fix:** Record `_url_dir` on the session dict and `shutil.rmtree(_url_dir,
ignore_errors=True)` in `_finish_session` and `cancel_session`. Register an
`atexit`/shutdown sweep for orphans.

---

## HIGH

### H1. `subscribe()` SSE queues are unbounded — slow client can OOM the worker
**Files:** `execution_log_service.py:202` (`queue: Queue = Queue()`) and
`_broadcast` `:270-276`; same pattern in `backend_cli_service.py:1249` + `_broadcast`
`:1418-1430`.
Subscriber queues are created with no `maxsize`. `_broadcast` does `q.put(message)`
for every log line / PTY chunk. A disconnected-but-not-yet-GC'd or slow SSE consumer
never drains its queue, so a verbose execution (claude `--verbose` can emit tens of
thousands of lines) grows the queue without bound → unbounded memory per stalled
subscriber. With `workers=1` this can take down the whole backend.
**Fix:** Use `Queue(maxsize=N)` and `put_nowait` with a drop-oldest / drop-newest
policy (or disconnect the subscriber) on `Full`. Emit a "[dropped N lines]" marker.

### H2. In-memory log buffer per execution is unbounded
**File:** `execution_log_service.py:40-41, 92-100` (`_log_buffers[execution_id].append(log_line)`).
Every stdout/stderr line for an active execution is appended to an in-RAM list with
no cap. A misbehaving or very chatty CLI (infinite loop printing) grows this list
until the buffer is popped at `finish_execution`. `cleanup_stale_buffers` exists but
is time-based, not size-based, so a runaway run within the staleness window can
exhaust memory. `stream_pipe` (`execution_runner.py:52`) reads lines with no
per-execution byte/line ceiling feeding this.
**Fix:** Cap the buffer with a `collections.deque(maxlen=…)` (ring buffer) — the same
ring-buffer pattern `ProjectSessionManager` already uses for `get_output`. Persist
overflow to DB and keep only the tail in RAM.

### H3. `os.waitpid(pid, os.WNOHANG)` after SIGTERM leaves zombies
**Files:** `pty_service.py:235-241` (`_cleanup_child`); same anti-pattern at
`backend_cli_service.py:432-437` and `:700-705`.
`_cleanup_child` sends `SIGTERM` then immediately calls `waitpid(pid, WNOHANG)`. The
non-blocking reap almost always returns `(0,0)` because the child has not died yet,
so the child is **never reaped → zombie process** accumulating one PID per PTY run
(`run_command`/`run_interactive` are called repeatedly for usage/status polling).
There is also no `SIGKILL` escalation if `SIGTERM` is ignored.
**Fix:** After `SIGTERM`, do a short bounded blocking wait (loop `waitpid(pid, WNOHANG)`
with small sleeps up to a deadline), escalate to `SIGKILL`, then a final blocking
`waitpid(pid, 0)`. Confirm the child is reaped.

### H4. PTY reader threads have no overall wall-clock timeout — orphaned PTY + thread leak
**Files:** `backend_cli_service.py:286-808` (`_pty_reader` `while True`), `pty_service.py`
`run_interactive`/`_read_until_done`.
`_pty_reader` loops until EOF/EIO on the master fd. If the child CLI hangs in a state
that keeps the PTY open but produces no completion signal (e.g. waiting forever on a
prompt we never answer, or a wedged OAuth flow past `INPUT_TIMEOUT_SECONDS` but still
alive), the reader thread and the child process live indefinitely — there is no
session-level deadline. `ExecutionService.run_trigger` has a hard `process.wait(timeout=…)`
(`execution_service.py:577`) and `cli_agent_runner_service` has a `Timer` kill
(`:120`), but the **PTY login/usage path has only per-read 1s selects and a 5-min
input timeout, never a total session cap**.
**Fix:** Add an absolute session deadline (e.g. `LOGIN_SESSION_MAX_SECONDS`) checked
each loop iteration; on expiry `killpg` + reap + `_finish_session("timeout")`.

### H5. `cli_agent_runner._run_subprocess` never reaps on the EOF-break path / leaks stderr pipe
**File:** `cli_agent_runner_service.py:123-160`.
The generator breaks out of the read loop on empty `readline` then calls `proc.wait()`
— good — but if the **consumer abandons the generator** (client disconnects mid-stream,
common for SSE chat), the `finally` only does `timer.cancel()`; `proc.wait()` is never
reached, the child keeps running for up to 15 min, and `proc.stdout`/`proc.stderr`
pipes are never closed → FD leak + orphaned `claude/codex/gemini` process. The
`Timer` only fires `proc.kill()` at the 15-min ceiling, not on early abandonment.
**Fix:** Wrap the streaming loop in `try/finally` that, on any exit, kills the process
group (use `start_new_session=True` so a group exists), drains/closes both pipes, and
`proc.wait()`s. `Popen` here also omits `start_new_session=True`, so child grandchildren
(tool subprocesses claude spawns) escape `proc.kill()`.

### H6. `_dispatch_batch` spawns unbounded dispatcher threads (global concurrency uncapped)
**File:** `execution_queue_service.py:144-192`.
Per-trigger concurrency is capped (`get_concurrency_cap`, default 1), but there is **no
global cap** across triggers. With many distinct triggers each at cap=1, a single poll
cycle (`get_pending_entries(limit=10)`, every 1s) keeps spawning `_dispatch_entry`
threads, each of which can `subprocess.Popen` a heavy CLI. Hundreds of triggers →
hundreds of concurrent agent subprocesses → host CPU/RAM/FD exhaustion. No semaphore /
worker pool bounds total in-flight executions.
**Fix:** Add a global `threading.Semaphore(MAX_GLOBAL_CONCURRENT)` (or a bounded
`ThreadPoolExecutor`) gating `_dispatch_entry`; skip dispatch when saturated.

---

## MEDIUM

### M1. `run_trigger` does not reap the child on success/failure paths (relies on GC)
**File:** `execution_service.py:530-771`.
On the normal path `process.wait(timeout=…)` reaps the child. But the reader-thread
join warnings (`:610-629`) and the budget-monitor thread are best-effort; if the
process exits but a reader thread is wedged, the threads are daemon and abandoned.
More importantly, on the **timeout branch** (`:578-607`) the code `killpg(SIGKILL)`
then joins reader threads but **never calls `process.wait()`** to reap the killed
child → transient zombie until interpreter exit. `ProcessManager.cleanup` (`:737`)
removes tracking but also does not `wait()`.
**Fix:** Add `process.wait(timeout=5)` after `killpg` in the timeout branch and in
`ProcessManager.cancel`/`cancel_graceful`.

### M2. `budget_monitor` thread can outlive the process / busy-spin window
**File:** `execution_runner.py:111-217`.
The loop is `while process.poll() is None: sleep(interval)`. If the budget check or
`killpg` path throws, the broad `except Exception` (`:215`) only `logger.debug`s and
the loop continues — acceptable — but on time-limit breach it calls
`ProcessManager.cancel_graceful` and `break`s **without confirming death**, so a
process ignoring SIGTERM runs until the run-level timeout. Also the monitor holds a
reference to `process` for the whole run (fine) but there is no upper bound on
`interval` drift.
**Fix:** After `cancel_graceful`, verify termination; rely on run-level
`process.wait(timeout)` as backstop (already present).

### M3. `pty.openpty()` slave_fd / master_fd leak on fork failure
**Files:** `pty_service.py:73-94` and `:122-140`; `backend_cli_service.py:179-218`.
`master_fd, slave_fd = pty.openpty()` then `os.fork()`. If `os.fork()` raises (EAGAIN
under load / RLIMIT_NPROC), both fds leak — the `except Exception` at
`pty_service.py:96` / the outer handler logs and returns `None` but never closes the
fds. Repeated failures under load exhaust the FD table.
**Fix:** Wrap openpty+fork in `try/except` that closes both fds on failure before
returning.

### M4. Broad `except Exception: pass`-style swallowing hides spawn/IO failures
**Files:** `backend_cli_service.py:248-249, 305-336, 776`, `pty_service.py:96-98`,
`execution_service.py:523-527, 765-769`.
Several handlers catch bare `Exception` and only `logger.debug` (or `pass`). Notably
`_pty_reader`'s outer `except Exception as e` at `:776` logs at warning but the reader
thread then exits, potentially leaving the child running and the session stuck in
`running` with no completion event broadcast (subscribers hang until keepalive→client
gives up). Harness-snapshot and session-complete emit failures at
`execution_service.py:523/765` are debug-only — acceptable as best-effort, but the
PTY-reader one is load-bearing.
**Fix:** In `_pty_reader`'s outer handler, always call `_finish_session(session_id,
"error", error_message=…)` so subscribers get a terminal event and the child is reaped.

### M5. `worktree_service` writes `.gitignore` and computes paths from caller-supplied names
**File:** `worktree_service.py:80, 224-239, 260-261`.
`worktree_name` is `os.path.join(project_path, ".worktrees", worktree_name)` and
`branch_name` flows into `git worktree add -b <branch>`. Callers in
`get_worktree_for_plan` build these from `phase_number`/`plan_number`/`phase_slug`. If
`phase_slug` (or a future caller's `worktree_name`) contains `../`, the worktree path
escapes `.worktrees/`. Argv form prevents shell injection, but **path traversal** on
`worktree_name` is unguarded, and `branch_name` is not validated against git refname
rules.
**Fix:** Validate `worktree_name` has no path separators / `..` (reject or
`os.path.basename`); validate branch names against `git check-ref-format` rules.

### M6. Per-project lock dict grows unbounded
**File:** `worktree_service.py:20, 24-30`.
`_locks` accumulates a `threading.Lock` per distinct `project_path` and is never
pruned. Long-lived process with many projects slowly leaks lock objects. Low impact
but unbounded.
**Fix:** Acceptable for small N; document, or use a `WeakValueDictionary` keyed by path.

### M7. `fetch_pr_diff` fetches an attacker-influenced URL with a 15s timeout but no size cap
**File:** `execution_runner.py:261-283`.
`pr_url` comes from the webhook event; `{pr_url}.diff` is fetched via
`urllib.request.urlopen(..., timeout=15)` and `response.read()` reads the **entire
body into memory** with no `Content-Length`/byte cap. A hostile or huge PR diff can
balloon memory, and the URL is not validated to be an `https://github.com` host (SSRF:
an attacker controlling the event payload could point `pr_url` at internal services).
**Fix:** Allowlist the host (github.com / configured GHE host), enforce `https`, and
cap `response.read(MAX_DIFF_BYTES)`.

---

## LOW

### L1. `_recent_broadcasts` dedup dict in `_pty_reader` grows for the session lifetime
**File:** `backend_cli_service.py:302`.
`_recent_broadcasts: dict[str, float]` keyed by line text is never trimmed; a long
login with many distinct lines grows it. Bounded by session duration but unbounded in
line count.
**Fix:** Periodically evict entries older than the dedup window.

### L2. `save_threat_report` / legacy trigger-event file use timestamp-based filenames
**File:** `execution_service.py:238-250, 218-236`.
Filenames include `trigger_id` and a second-granularity timestamp under a fixed dir.
`trigger_id` is a server-generated prefixed id (not attacker-controlled), so path
traversal is not currently reachable, but the message body is written verbatim with no
size cap. Low risk; note for defense-in-depth (validate `trigger_id` charset, cap size).

### L3. `run_resolve_command` / `auto_resolve_and_pr` interpolate scan output into a prompt
**Files:** `execution_service.py:812`, `execution_runner.py:300-312`.
`audit_summary` / `scan_output` are embedded into the CLI prompt argument (argv, not
shell — safe from shell injection) but represent untrusted scan output handed to a
`--dangerously-skip-permissions`-class agent with `Bash,Edit,Write`. This is prompt
injection surface into a high-privilege agent, not a subprocess bug per se.
**Fix:** Out of scope for this layer, but flag: treat scan output as untrusted in the
resolve-agent prompt; constrain tools / sandbox the resolve run.

### L4. `_handle_interaction` leaves `_current_question` set if reader thread dies mid-wait
**File:** `backend_cli_service.py:827-853`.
If the process exits while `event.wait()` is blocked and another path pops the session,
`_current_question[session_id]` cleanup is only in the timeout / success branches.
Minor stale-state leak cleaned at `_finish_session:1034`.

---

## Notes / non-issues verified

- **No `shell=True`** in any audited file; all `subprocess.run/Popen` use list argv.
- `ProcessManager` correctly uses `start_new_session=True` + `killpg`, holds a lock for
  shared-state mutation, and escalates SIGTERM→SIGKILL via a timer (`:81-124`).
- `execution_retry` carefully cancels timers inside the lock to avoid double-execution
  (`:253-260`) — good.
- `execution_queue_service` uses CAS status updates to avoid double-dispatch (`:181`).
- Run-level execution (`run_trigger`) has a hard `process.wait(timeout)` and SIGKILL on
  timeout — the main trigger path is well-bounded; the gaps are in the PTY login/usage
  and chat-agent paths.
