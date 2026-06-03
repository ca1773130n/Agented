# Production Hardening Audit — Master Report

Full-codebase review (2026-06-03). Eight parallel reviewers read full source across the
backend execution layer, auth/secrets, core/DB, harness evolution, integrations,
orchestration, HTTP routes, and the Vue frontend. Per-area detail lives in
`01`–`08*.md` in this directory. Totals: **~11 CRITICAL, ~34 HIGH, ~44 MEDIUM, ~30 LOW.**

Several issues surfaced in more than one area; they are deduplicated below and counted once.

---

## P0 — fix before any production exposure (CRITICAL)

1. **Hardcoded Google OAuth `client_secret` committed in source**
   `routes/leaf_crud_h.py:483`, dup `services/provider_usage_client.py:29`. Unrotatable, in every
   clone/git history. → Externalize to env/secret store **and rotate the credential now**.
2. **Plaintext secret reveal/list not admin-gated** (cross-cut 02+07)
   `routes/admin_tooling.py:320-367`. `POST /admin/secrets/{id}/reveal` returns decrypted values
   gated only at `editor`; list/metadata readable by `viewer`; audit principal is a static `"api"`
   string. → `requires_role("admin")` + real principal + redaction.
3. **Webhook secret readable by any viewer → forgeable signed webhooks** (cross-cut 05)
   `app/db/triggers.py:447` (`SELECT *`) surfaced unredacted via `trigger_service`/`routes/triggers.py`.
   → redact `webhook_secret` from all read paths.
4. **Harness `apply_patch` is non-atomic with no partial-failure rollback**
   `harness_evolver.py:1023-1121`. Mid-loop exception leaves k-1 mutations committed and journal
   unsaved → unrevertable corruption. → stage + single transaction, or compensating rollback.
5. **Eval gate fails OPEN, autonomy auto-applies the synthetic pass**
   `harness_evolver.py:1421-1439` + `harness_autonomy.py:56,153`. Eval error stores fake
   `passed=True`; `confidence_threshold=0.0` auto-applies untested mutations. → fail closed.
6. **Stored XSS — execution log search** `views/ExecutionSearchPage.vue:143,147` renders SQLite
   `snippet()` output (agent-controlled, NOT html-escaped) via raw `v-html`. → escape server-side
   + `DOMPurify({ALLOWED_TAGS:['mark']})`.
7. **XSS — agent markdown rendered without DOMPurify** `components/base/MarkdownContent.vue:33-43`
   (`marked.parse` raw) fed untrusted agent content from 3 call sites. → route through sanitized
   `renderMarkdown()`.
8. **Unbounded SSE subscriber queues / no backpressure** (cross-cut 01+06)
   `agent_message_bus_service.py:171-196`, `execution_log_service.py:202`,
   `backend_cli_service.py:1249,1418`. `Queue()` with no `maxsize`; a stalled-but-connected client
   OOMs the single worker. Plus `_subscribers` map never evicts empty keys (perma-leak).
   → bounded queues + drop policy + key eviction.

## P1 — HIGH (fix in the hardening sprint)

**Auth / multi-tenant**
- IDOR on projects & agents: get/update/delete/run/deploy `del caller`, act on any id with no
  ownership check — `routes/projects.py:159,170,196`, `agents_and_tracing.py:55-95`.
- Mass-assignment: raw request dict → service/DB writers, no field allow-list —
  `agents_and_tracing.py:58,73`, `leaf_crud_c.py:208,222`, `leaf_crud_b.py:415,425`.
- Settings store arbitrary key read/write w/o allow-list — `admin_tooling.py:56,85,90`.
- Auth rate-limit bypass: trusts `X-Forwarded-For`, in-memory-only limiter —
  `middleware.py:427-447`. Login/signup/reset defeatable by header rotation.
- Webhook replay protection never enabled (`require_timestamp` defaults False) —
  `webhook_validation_service.py:139`, callers `webhooks.py:119`, `trigger_dispatcher.py:92`.
- Password-reset token logged in clear — `auth.py:204-208`.
- Static env API key silently elevated to `role="admin"` — `middleware.py:195-198`.
- Bootstrap mode fails OPEN (zero roles ⇒ everyone admin) — `middleware.py:158`, `auth.py:82`,
  `rbac_service.py:82`.
- PR-comment dispatch skips rate-limit + dedup (unbounded fan-out) — `routes/webhooks.py:50-98`,
  `trigger_dispatcher.py:407-529`.

**Process / resource leaks**
- Zombie processes: `SIGTERM` + immediate `waitpid(WNOHANG)`, no SIGKILL escalation —
  `pty_service.py:235-241`, `backend_cli_service.py:432-437,700-705`.
- OAuth temp dir + fake-browser script never cleaned (sensitive data, unbounded inode leak) —
  `backend_cli_service.py:166-175`.
- Chat-agent subprocess leaks on client disconnect; no `start_new_session=True` so grandchildren
  escape kill — `cli_agent_runner_service.py:123-160`.
- CLI streaming generators lack `finally`/`GeneratorExit` → orphan subprocess + armed Timer on SSE
  disconnect — `conversation_streaming.py:728,838`.
- Workflow per-node timeout leaks worker thread + subprocess — `workflow_node_executor.py:57-86`.
- Harness scratch workspace (full config dump) leaked on every non-success exit —
  `harness_evolver.py:1457,1594`.

**Reliability**
- Unguarded startup steps kill the only worker on any exception (workers=1) —
  `lifecycle.py:397,410,471,472`.
- Goal-loop crash is loop-fatal and silent (no `goal_loop_ended` broadcast) —
  `goal_loop_runner.py:456-460`.
- Scheduler/account read-modify-write races (lost updates, DB/cache divergence) —
  `agent_scheduler_service.py:294-345`.
- Path traversal in harness deploy file materialization (skill/team names → fs path, pushed to
  GitHub) — `harness_deploy_service.py:148,193`.
- No lock around concurrent evolution rounds / approval transition (double-apply) —
  `harness_evolver.py:1451-1610`, `harness_autonomy.py:121-164`.
- `value_error_handler` leaks raw internal text to clients — `exception_handlers.py:93`.
- Frontend: bearer token + admin API key in localStorage (XSS-exfiltratable) —
  `services/api/client.ts:16,54`. ANSI terminal & tagging-page `v-html` XSS sinks —
  `LiveExecutionTerminal.vue:52-60,256`, `ExecutionTaggingPage.vue:223-235,354`.

## P2 — MEDIUM (next)
git clone arg injection (no `--`/scheme validation) `gitops_sync_service.py:410-416`; MCP
`test_connection` SSRF `mcp_sync_service.py:244-246`; prompt injection from PR/comment text into
agent prompts `trigger_dispatcher.py:142,324,474`; `get_connection()` never commits/rolls back +
no WAL `app/db/connection.py`; retention `enqueue_cleanup()` is a no-op (unbounded table growth)
`retention_service.py:126`; unbounded list endpoints (no `limit`) and no global request-body-size
limit; goal loop / evolution have no token-cost budget guard; Ralph monitor threads never joined.
See per-area files for the full MEDIUM/LOW lists.

---

## Verified-clean (no regressions — keep as remediation templates)
- `url_summarizer.py` — exemplary SSRF defense (DNS pinning, per-hop redirect re-validation).
- `provider_usage_client.py` — hardcoded URLs, header-only tokens, timeouts everywhere.
- HMAC/signature paths use `hmac.compare_digest`; session tokens 256-bit constant-time; secrets
  Fernet/MultiFernet-encrypted; audit diffs redact secret fields.
- No `shell=True` anywhere; subprocess calls are list-argv (classic shell injection absent).
- API client: timeout + retry/jitter + abort + bounded SSE reconnect; DOMPurify markdown pipeline.
- `routes/teams.py` + `payload_transformers.py` — per-route `require_role` + length caps (the
  template the leaf_crud routes should follow).

## Coverage note
This wave covered the highest-risk surfaces. Not yet read in full: analytics/budget/campaign,
plugin_*/skill_*/sketch_*/replay/report/bulk services, models/, and the bulk of frontend
views/components beyond the XSS sweep. A second wave can cover these if desired.
