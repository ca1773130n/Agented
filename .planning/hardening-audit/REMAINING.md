# Hardening Audit — REMAINING (unfixed) worklist

Verified against current `main` on disk (2026-06-03), after PRs #190/#191/#192.
Every item below was re-checked at its cited file:line and confirmed STILL
UNFIXED. Items already landed (per the fixed-list) are omitted. Severity is the
audit's original rating. Each entry: `[id] SEV — description · file:line · fix`.

Counts: HIGH 7 · MEDIUM 28 · LOW 18.

---

## 01 — Execution / subprocess

- [01.H6] HIGH — No global concurrency cap across triggers; per-poll dispatcher
  threads spawn unbounded heavy CLI subprocesses · `app/services/execution_queue_service.py:144-192`
  · Gate `_dispatch_entry` behind a module `threading.Semaphore(MAX_GLOBAL_CONCURRENT)` (or bounded ThreadPoolExecutor); skip dispatch when saturated.
- [01.M1] MEDIUM — Timeout branch `killpg(SIGKILL)`s but never `process.wait()`s →
  transient zombie; `ProcessManager.cancel`/`cancel_graceful` also never reap ·
  `app/services/execution_service.py:578-607`, `app/services/process_manager.py:62-110`
  · Add `process.wait(timeout=5)` after killpg in the timeout branch and in cancel paths (and in `_force_kill`).
- [01.M3] MEDIUM — `pty.openpty()`+`os.fork()` leak both fds on fork failure; the
  except just returns None · `app/services/pty_service.py:73-98` and `:122-140` ·
  Wrap openpty+fork so the except `os.close(master_fd)`/`os.close(slave_fd)` before returning.
- [01.M5] MEDIUM — Worktree path traversal: `worktree_name` joined raw under
  `.worktrees/`; `branch_name` not validated against git refname rules ·
  `app/services/worktree_service.py:80,260-264` · Reject `..`/sep in worktree_name (or `os.path.basename`); validate branch via `git check-ref-format` rules; add `--` before positionals.
- [01.M7] MEDIUM — `fetch_pr_diff` fetches `{pr_url}.diff` with no host allowlist
  and `response.read()` with no byte cap (SSRF + memory blowup) ·
  `app/services/execution_runner.py:261-283` · Allowlist github.com/GHE host, enforce https, `response.read(MAX_DIFF_BYTES)`.

(01.M4 PTY-reader terminal-event-on-error, 01.L1 dedup eviction already landed; 01.C1/C2/H1-H5 fixed.)

---

## 02 — Auth / secrets / rate-limit

- [02.H1-residual] HIGH — Login/forgot/reset have no per-email throttle (X-Forwarded-For
  trust + bootstrap opt-in already fixed) · `app_litestar/routes/auth.py:50,94,191,216`
  · Add a per-email fixed-window throttle on login + password-reset in addition to the per-IP limiter.
- [02.H2] HIGH — Webhook replay protection never enabled: GitHub + generic paths
  call `validate_signature` only, no timestamp/delivery-id dedup ·
  `app_litestar/routes/webhooks.py:101-126`, `app/services/trigger_dispatcher.py:88-100`
  · Reject already-seen `X-GitHub-Delivery`; flip custom-trigger receivers to `require_timestamp=True`.
- [02.M2] MEDIUM — `_AUTH_BYPASS_PREFIXES` matches any sub-path of webhook/oauth
  prefixes (latent public-route footgun) · `app_litestar/middleware.py:56-66` ·
  Pin bypass to exact path+method (`POST /api/webhooks/github`), or lint that nothing else mounts there.
- [02.M3] MEDIUM — `validate_timestamp` fail-open (`return True` on missing header);
  no receiver enforces it · `app/services/webhook_validation_service.py:101-103` ·
  Flip production call sites to `require_timestamp=True`; add a test asserting missing-timestamp rejection.
- [02.M5] MEDIUM — Secret decrypt failure during execution silently skipped
  (WARNING only, no audit, partial fail-open) · `app/services/secret_vault_service.py:249-262`
  · Emit `secret.decrypt_failed` audit event; decide fail-closed (abort) vs surface-to-operator per policy.
- [02.L1] LOW — Audit SQLite-persist failure logged at DEBUG (already raised to
  WARNING per fixed-list — VERIFY only) · `app/services/audit_log_service.py:108-113`.
- [02.L3] LOW — Name-enumeration oracle on reveal/me (200 vs 404). Mostly closed by
  C2 admin-gate + M4 id-only reveal; residual: uniform 404 on unknown-id vs unauthorized · `app_litestar/routes/auth.py:128-137`.

(02.C1/C2 admin-gate, H1 XFF, H3 env-attr, H4 reset-token, M1 bootstrap, M4 id-only reveal, L2 sha1 all fixed.)

---

## 03 — Core wiring (DB / middleware / exceptions / lifecycle / streaming)

- [03.H1] HIGH — CLI streaming generators leak subprocess + Timer + pipes on client
  disconnect (cleanup only on normal-exit path, no `finally`/`GeneratorExit`) ·
  `app/services/conversation_streaming.py:728` (`_stream_via_cli`), `:838` (`_stream_via_opencode_cli`)
  · Wrap the read loop in `try/…/finally` that always `timer.cancel()`, kills the proc (guarded), closes stdout/stderr, and `proc.wait()`s.
- [03.M1] MEDIUM — `session_persist_error_handler` returns raw `str(exc)` to client
  (registered for broad Exception) · `app_litestar/exception_handlers.py:142,154` ·
  Return a controlled message; log the detail server-side.
- [03.M2] MEDIUM — `get_connection()` has no `commit()` on success / `rollback()` on
  exception (WAL added, transaction safety not) · `app/db/connection.py:34-56` ·
  Make it transactional: `try: yield; conn.commit() except: conn.rollback(); raise finally: conn.close()` (audit double-commit callers).
- [03.M4] MEDIUM — Retention `enqueue_cleanup()` is a no-op; policy-governed tables
  grow unbounded · `app/services/retention_service.py:126-137` · Implement batched
  `DELETE … WHERE created_at < ?` per policy (VACUUM-aware), or clearly gate the feature off.
- [03.L1] LOW — CSP `script-src/style-src 'unsafe-inline'` applied globally, not just
  `/schema/*` · `app_litestar/middleware.py:351-353` · Scope relaxed CSP to `/schema/*`; strict `script-src 'self'` elsewhere.
- [03.L2] LOW — CLI prompt passed via argv (visible in `ps`/`/proc`) ·
  `app/services/conversation_streaming.py` `_stream_via_cli` cmd · Pass prompt via stdin (`Popen(stdin=PIPE)`).
- [03.L4] LOW — `not_found_handler` does `_SPA_INDEX.read_bytes()` per non-API 404,
  swallows OSError · `app_litestar/exception_handlers.py:79-82` · Cache index bytes at startup; log the OSError.

(03.H2 startup guards, H3 value_error generic, M3 WAL, M5 HSTS-scheme all fixed.)

---

## 04 — Harness evolution / autonomy

- [04.H1] HIGH — Path traversal in deploy file materialization: skill name + team
  `safe_name` not stripped of `/`/`..`, no containment assert ·
  `app/services/harness_deploy_service.py:148,193` · Sanitize each segment to `[alnum-_]`, reject `.`/`..`/empty, assert resolved path `is_relative_to` base.
- [04.H2] HIGH — No per-project serialization of evolution rounds; rate-limit check is
  read-then-act, `mark_applied` not conditional → double-apply ·
  `app/services/harness_evolver.py:1528,1625`, `app/services/harness_autonomy.py:121-164`
  · Advisory lock / CAS status transition per project; make `mark_applied` conditional on expected pre-state.
- [04.H3] HIGH — Scratch dir leaked: `keep_scratch_on_failure` defaults True, cleanup
  only on success branch (no try/finally) → `/tmp` fills with sensitive dumps ·
  `app/services/harness_evolver.py:1519,1540,1656-1657` · Use `try/finally`/`TemporaryDirectory`, remove on every exit unless debug flag; 0700 perms; rename flag.
- [04.H4] HIGH — `claude plugin install` exit code never inspected → silent broken
  provisioning · `app/services/harness_plugin_installer.py:49-56` · Capture+check returncode, log stderr on non-zero, return installed/failed lists.
- [04.H5] HIGH — `_create_skill`/`_delete_skill` write/unlink with no `is_relative_to`
  containment; delete relies on weak `parent.name != "skills"` guard ·
  `app/services/harness_evolver.py:1337-1399` · Resolve and assert `is_relative_to` the project `.claude/skills/` root before any mkdir/write/unlink/rmdir.
- [04.M1] MEDIUM — `validate_patch` never inspects hook shell `content` or mcp_server
  `command`/`args`; autonomy can auto-apply arbitrary-shell hooks ·
  `app/services/harness_evolver.py` validate_patch + `harness_autonomy.py:72-87` · Content-level allowlist, or exclude hook/mcp_server kinds from `policy.allowed_kinds` defaults.
- [04.M2] MEDIUM — `gather_inputs` applies `since`/`until` in Python after DB `limit`
  → can silently yield <limit in-window rows · `app/services/harness_evolver.py:413-418`
  · Push `before_ts`/`after_ts` into `snapshots_repo.list_for_project`.
- [04.M3] MEDIUM — `_git_revert` runs `git revert --abort` unconditionally + no
  clean-tree check → can clobber unrelated in-progress merge / leave half-revert ·
  `app/services/harness_evolution_rollback.py:130-150` · Check `git status --porcelain` clean; only `--abort` if `.git/REVERT_HEAD` exists.
- [04.M4] MEDIUM — `reverse_apply_journal` create-reversal deletes by `asset_id`
  without verifying identity; `_already_restored` swallows all exceptions ·
  `app/services/harness_evolution_rollback.py:46-87` · Verify current asset matches before-image identity before deleting on create-reversal.
- [04.M5] MEDIUM — No aggregate LLM cost/token budget across the round's tesserae/kg/
  judge/codex fan-out; autonomy iterates ≤50 rounds on a count gate only ·
  `app/services/harness_evolver.py:703-766`, `harness_autonomy.py:129` · Add env-configurable per-round + per-day cost budget checked before fan-out.
- [04.M6] MEDIUM — `_run_codex_in_workspace` uses `capture_output=True` (unbounded
  in-memory stdout/stderr) · `app/services/harness_evolver.py:830-862` · Stream from pipes with a max-bytes cap.
- [04.L1] LOW — Kill switch checked at decision time only; flipping `AGENTED_AUTONOMY=0`
  mid-round doesn't abort an in-flight round · `app/services/harness_autonomy.py:24-25`
  · Re-check before `apply_patch`; support aborting in-flight rounds.
- [04.L2] LOW — `check_harness_exists` returns HTTP 200 `exists:False` + raw `str(e)`
  on clone/IO error · `app/services/harness_loader_service.py:66-100` · Distinguish not-found from error; 5xx for genuine failures, no raw exc to client.
- [04.L3] LOW — Loader imports hook/command `content` verbatim from cloned GitHub repo
  (shell content trusted) · `app/services/harness_loader_service.py:190-462` · Treat loaded hook/command content as untrusted; require review before binding.
- [04.L4] LOW — Materialize/commit failure on apply path logged but round still
  `mark_applied` (DB/filesystem diverge silently) · `app/services/harness_evolver.py:1603-1625`
  · Record a `materialization_failed` flag on the round for operator visibility.

(04.C1 apply atomicity, C2 eval-gate fail-closed fixed.)

---

## 05 — External integrations

- [05.H2] HIGH — `issue_comment` slash-command path has no per-repo rate limit and no
  dedup (PR path has both) → unbounded fan-out / duplicate executions ·
  `app_litestar/routes/webhooks.py:50-90`, `app/services/trigger_dispatcher.py:407` · Apply the per-repo rate limit + add `check_and_insert_dedup_key` keyed on (trigger,repo,comment_id,updated_at,command); consider gating on commenter association.
- [05.M1] MEDIUM — Untrusted PR/comment text substituted into agent prompt via raw
  `.replace("{message}", …)` (prompt injection) · `app/services/trigger_dispatcher.py:142,324,474`
  · Fence substituted text in `<untrusted_user_input>…</…>`, truncate consistently, constrain trigger-run tools.
- [05.M4] MEDIUM — `oauth_callback_proxy` forwards with `follow_redirects=True`; the
  loopback CLI server can redirect httpx to an arbitrary URL, body reflected to the
  unauthenticated caller · `app_litestar/routes/webhooks.py:220` · Set `follow_redirects=False`; reject 3xx or return Location verbatim (distinct from the already-fixed leaf_crud_h port-pin).
- [05.M5] MEDIUM — Generic `/` webhook fires unauthenticated when a trigger has no
  `webhook_secret` (signature check is `if webhook_secret`) · `app/services/trigger_dispatcher.py:88-100`, `trigger_service.create_trigger` · Require `webhook_secret` for `trigger_source == "webhook"` at create/update, or a deploy toggle rejecting unsigned dispatch.
- [05.L1] LOW — `validate_repo_url` fails open (`return True` on every error path,
  broad except, `follow_redirects=True`) · `app/services/github_service.py:39-86` · Narrow except to `(TimeoutExpired,FileNotFoundError)`; tri-state on ambiguity; `follow_redirects=False`.
- [05.L3] LOW — Teams/JIRA outbound URLs have no private-IP/SSRF guard (JIRA also no
  https enforce) · `app/services/integrations/teams_adapter.py:58-63`, `jira_adapter.py:88` · Route outbound URLs through the shared `_is_safe_target`, or enforce admin-trusted config via RBAC.
- [05.L4] LOW — `_repo_last_event` rate-limit dict never evicted (attacker-influenced
  `repo_full_name` keys) · `app_litestar/routes/webhooks.py:39,162-170` · Evict entries older than `_REPO_RATE_LIMIT_SECONDS` on access, or use a TTL cache.

(05.H1 webhook_secret redaction, M2 git-clone `--`, M3 mcp SSRF block all fixed.)

---

## 06 — Orchestration / message bus / scheduling

- [06.C2-residual] MEDIUM — `AgentConversationService._subscribers` finally removes the
  queue but never deletes the now-empty `conv_id` key (msg-bus half already fixed) ·
  `app/services/agent_conversation_service.py:404-406` · After remove, `if not _subscribers[conv_id]: del _subscribers[conv_id]`.
- [06.H3] HIGH — Team-execution cleanup relies solely on a 5-min daemon `threading.Timer`
  (lost on restart / daemon kill); no startup sweep or size cap; stale
  `pending_approval` entries persist · `app/services/team_execution_service.py:190` · Use a SchedulerService `date` job (as workflow does); add periodic sweep + map size cap.
- [06.M1] MEDIUM — `_execute_trigger` calls `update_trigger_last_run` BEFORE the
  existence/enabled checks → phantom last_run on disabled/deleted triggers; orphan
  cron not unscheduled · `app/services/scheduler_service.py:213-225` · Move the stamp after the checks; call `unschedule_trigger` on not-found.
- [06.M3] MEDIUM — `_run_workflow` has no outer try/except finalizing the execution as
  `failed`; an exception outside node handlers leaves status `running` forever ·
  `app/services/workflow_execution_service.py:330-669` · Wrap the body so any unexpected exception marks `failed` in mem+DB, emits completion, schedules cleanup.
- [06.M4] MEDIUM — `team_monitor` watchdog `_process_event` doesn't consult mtime
  state → double broadcasts vs the polling loop; poll uses `time.sleep(5)` (non-interruptible)
  · `app/services/team_monitor_service.py:54-75,168-169` · Gate watchdog broadcasts through the mtime helper; use `Event.wait(5)` for prompt stop.
- [06.M5] MEDIUM — `ProcessManager._cancelled` set leaks if `cleanup` is never called
  for a cancelled execution (runner thread died) · `app/services/process_manager.py:34,66,85` · Bound it / TTL, or guarantee cleanup is always paired with cancel.
- [06.M6] MEDIUM — `register` pgid-fallback stores `pid` as pgid on `ProcessLookupError`;
  later `killpg` can signal a recycled / wrong group · `app/services/process_manager.py:42-58` · Mark such ProcessInfo "untracked-pgid" and refuse `killpg` (only `process.kill()` the pid).
- [06.M7] MEDIUM — Goal-loop convergence/iteration-cap `_broadcast_end` branches don't
  re-check `state.stop_event.is_set()` before broadcasting → possible double-broadcast ·
  `app/services/goal_loop_runner.py:424-460` · Check `stop_event.is_set()` immediately before each `_broadcast_end`/`stop_session`.
- [06.L1] LOW — `agent_service.run_agent` `thread.join(timeout=2.0)` can return
  `execution_id: None` while the agent runs (untrackable/uncancellable) ·
  `app/services/agent_service.py:183-204` · Allocate the id synchronously before forking background work.
- [06.L2] LOW — Scheduler `max_instances=1` doesn't prevent overlapping team/workflow
  runs (strategies fork their own daemon threads); coalesced runs unaudited ·
  `app/services/scheduler_service.py:99-105,278-300` · Track in-flight runs, skip-or-log overlap, audit coalesced/skipped runs.
- [06.L3] LOW — Workflow command/script node `subprocess.run` lacks `start_new_session`
  + process-group kill → orphan grandchildren on TimeoutExpired ·
  `app/services/workflow_node_executor.py:157,312` · `start_new_session=True` + `os.killpg` on timeout, or Popen with explicit group teardown.
- [06.L4] LOW — `team_monitor` polling loop has 3+ bare `except Exception: pass` hiding
  degraded monitoring · `app/services/team_monitor_service.py:193,220,222,244` · Replace with rate-limited `logger.debug(..., exc_info=True)`.

(06.C1 msg-bus bounded queues + C2 msg-bus eviction, H1 goal budget, H2 ralph interruptible, H4 workflow node-timeout subprocess cap, H5 goal error-broadcast, H6 scheduler race all fixed.)

---

## 07 — HTTP route layer

- [07.H3] HIGH — Mass-assignment: handlers forward raw request dict to service/DB with
  no field allowlist (agents now strip user_id only) · `leaf_crud_c.py:216-230`
  (findings), `leaf_crud_b.py:415,425,332` (pr_review/audit), `admin_tooling.py:376`
  (create_repo) · Define msgspec/Pydantic request models with explicit fields; reject unknown keys.
- [07.M1] MEDIUM — Collaborative endpoints trust client-supplied `viewer_id`/`viewer_name`
  → impersonation · `app_litestar/routes/leaf_crud_d.py:176-249` · Derive viewer identity from authenticated `caller.user_id`.
- [07.M2-residual] MEDIUM — `get_all_*` listers with NO `limit` param still lack
  pagination (list_marketplaces, list_integrations, list_snippets, list_filters,
  list_all_campaigns, list_execution_tags, list_findings, list_bot_pipes, list_repos,
  list_version_pins …) · `admin_tooling.py`, `leaf_crud_*` · Add LIMIT/OFFSET pagination to the listers that have none (clamp_limit already applied where a limit param exists).
- [07.M3] MEDIUM — No item-count caps: `_bulk` items uncapped, `add_thread_messages`/
  `add_branch_message` arrays uncapped, `run_chunked` spawns one thread per chunk with
  no chunk-count cap · `leaf_crud_f.py:347,117`, `leaf_crud_i.py:392-420` · Cap bulk items (≤500), cap message arrays, bound chunk count per request (global body-size limit already added but doesn't bound item/thread count).
- [07.M4] MEDIUM — Most string creators have no max-length (unlike teams.py 255-cap):
  create_snippet content, create_product name, create_sketch, create_campaign,
  create_bot_pipe, create_project · `projects.py`, `leaf_crud_a/c/d/e/g.py` · Add length caps per the teams.py convention.
- [07.M5] MEDIUM — `del caller` discards identity across most `/admin` mutators →
  audit can't attribute, no ownership decision · `projects.py` (team-edge/install/deploy
  handlers) and others · Thread `caller` into audit logging + ownership checks instead of dropping it.
- [07.L1] LOW — Internal exception text leaked in 500 details (`detail=f"…{e}"` /
  `str(exc)`) · `leaf_crud_g.py:327,349,351,373,375,398…`, `leaf_crud_h.py`,
  `leaf_crud_i.py`, `admin_tooling.py create_secret` · Log detail server-side, return a generic message.
- [07.L2] LOW — `browse_directory`/`create_directory` (FS listing + mkdir under
  `~`/`/tmp`/`/opt`) reachable by editor, unaudited · `leaf_crud_h.py:122,160` · Add `requires_role("admin")` + audit entry.
- [07.L3] LOW — `discover_skills`/`import_plugin`/`sync_to_disk`/`sync_entity` accept
  arbitrary host paths with no allowlist · `leaf_crud_h.py:97`, `leaf_crud_g.py:338` · Validate through the same `_is_path_allowed`/`_ALLOWED_BASES` gate.
- [07.L4] LOW — Numeric coercions trust DB/body with no range checks
  (`sigterm_grace_seconds`, pr_rule `priority`, monitoring batch ints) ·
  `executions.py:37-38`, `leaf_crud_d.py:444`, `leaf_crud_e.py` · Clamp to sane non-negative ranges.

(07.C1 OAuth secret, C2 reveal admin-gate, H1/H2 IDOR, H4 settings allowlist, H5 callback port-pin, M2 clamp_limit (where a limit param exists), global body-size limit all fixed.)

---

## 08 — Frontend (Vue 3)

- [08.H1-residual] HIGH — Long-lived admin **API key** still stored in `localStorage`
  (read into `X-API-Key` every request); the legacy session-token localStorage/Bearer
  path also remains alongside the new cookie+CSRF flow · `frontend/src/services/api/client.ts:16-42,48-75,152-155`
  · Stop storing the long-lived API key in the browser (short-TTL/scoped), and retire the localStorage session-token+Bearer path now that cookie+CSRF exists.
- [08.M1] MEDIUM — `DocumentEditor` hand-rolled `renderMarkdown` re-introduces HTML via
  regex incl. unvalidated `[text](url) -> <a href="$2">` (self-XSS:
  `javascript:`/attribute breakout) · `frontend/src/components/super-agents/DocumentEditor.vue:106-141,197` · Replace with `renderMarkdown()` from `useMarkdown.ts`, or DOMPurify + reject non-http(s)/relative hrefs.
- [08.M2] MEDIUM — `v-html` of interpolated i18n strings (fragile, becomes XSS if a
  future catalog entry / dynamic value flows in) · `WelcomePage.vue:132`,
  `TourOverlay.vue:262`, `RateLimitGauge.vue:105` · Use `<i18n-t>`/slot interpolation, or split into `t()` + static markup; lint inputs are constant.
- [08.M3] MEDIUM — `v-html` of `getTriggerIcon()` SVG strings (static today, drift
  hazard) · `frontend/src/components/triggers/TriggerList.vue:99` · Render SVGs as static components / icon map instead of `v-html`.
- [08.M4] MEDIUM — Router `beforeEach` guard is client-side only and "fails open on
  network errors" — acceptable only if backend enforces authz on every protected route ·
  `frontend/src/router/guards.ts:108-135` · Confirm/keep server-side middleware enforcement; treat the guard strictly as UX.
- [08.L1] LOW — `console.error`/`console.warn` left in prod (raw `event.data`/error
  objects aid recon) · `main.ts:50,62,87`, `useProjectSession.ts:168+`, `client.ts:286-300`,
  `guards.ts` · Gate diagnostics behind `import.meta.env.DEV` or a payload-stripping logger.
- [08.L2] LOW — Geist font loaded from Google CDN at runtime (only hardcoded external
  origin) · `frontend/src/App.vue:278` · Self-host the woff2 files (and add the origin to CSP if kept remote).
- [08.L3] LOW — SSE give-up after `SSE_MAX_ATTEMPTS` is silent if a consumer doesn't
  wire `onGiveUp` → dead stream looks idle · `frontend/src/services/api/client.ts:424-429`,
  `useEventSource.ts` · Ensure every SSE consumer wires `onGiveUp`/`onerror` to a visible "connection lost" state.

(08.C1 ExecutionSearchPage snippet sanitize, C2 MarkdownContent DOMPurify, H2 ANSI-escape, H3 highlightMatch escape, session-token→cookie+CSRF all fixed.)
