# Evaluation Plan: Phase 11 — Enterprise Integrations & Governance

**Designed:** 2026-03-04
**Designer:** Claude (grd-eval-planner)
**Requirements covered:** INT-01, INT-02, INT-03, INT-04, INT-05, INT-06, INT-07, INT-08
**Plans in scope:** 11-01 through 11-06 (3 waves, 6 plans, 15 tasks)
**Reference research:** `.planning/milestones/v0.1.0/phases/11-enterprise-integrations-governance/11-RESEARCH.md`

---

## Evaluation Overview

Phase 11 is a pure integration-engineering phase — no machine learning, no statistical experiments. The eight requirements span RBAC, audit persistence, secrets encryption, config export/import, four external integration adapters, a GitOps sync engine, multi-repo campaigns, and execution bookmarking. The primary evaluation concerns are **security correctness** (encryption, RBAC enforcement, signature verification), **behavioral correctness** (round-trip fidelity, upsert semantics, conflict resolution), and **integration contract compliance** (adapter APIs called with correct payloads, timing constraints met without blocking).

Most evaluation can be done in-phase through unit and integration tests with mocked external services. The fraction that requires live external systems (real Slack workspace, real JIRA instance, real git remote, real production traffic) is clearly deferred with specific phase references.

The phase has no paper-derived quantitative benchmarks. Targets come from three sources: the RESEARCH.md experiment design section (notification latency <30s, encryption <10ms, audit query <500ms at 10K rows), the PROJECT.md quality targets (100% backend test pass rate, 0 frontend type errors), and security first-principles (100% RBAC enforcement accuracy, timing-safe signature comparisons).

### Metric Sources

| Metric | Source | Why This Metric |
|--------|--------|-----------------|
| pytest pass rate | PROJECT.md quality target | Primary quality gate for the phase |
| `just build` success | PROJECT.md quality target | Prevents type regressions in frontend |
| Fernet encrypt/decrypt <10ms | RESEARCH.md experiment design | Ensures vault doesn't become a bottleneck at execution time |
| RBAC enforcement accuracy (100%) | Security first-principles (NIST RBAC0) | Any unauthorized access = security failure |
| Audit query time <500ms @ 10K rows | RESEARCH.md experiment design | Ensures audit history page remains responsive |
| Notification dispatch <30s | RESEARCH.md / INT-01 requirement | Slack messages that arrive minutes late have no operational value |
| Export/import round-trip lossless | INT-03 correctness requirement | GitOps depends on idempotent upsert; silent data loss breaks the sync model |
| Slash command response <3s | Slack API requirement | Slack times out the slash command if backend doesn't respond within 3 seconds |
| HMAC-SHA256 signature verification | Security (replay attack prevention) | Invalid signatures accepted = arbitrary command injection |
| Semaphore limits concurrency to 5 | RESEARCH.md Pitfall 5 | Unbounded concurrent repos exhausts system resources |

### Verification Level Summary

| Level | Count | Purpose |
|-------|-------|---------|
| Sanity (L1) | 12 checks | Basic functionality, format, and security property verification |
| Proxy (L2) | 14 metrics | Automated correctness and performance measurements (mocked external APIs) |
| Deferred (L3) | 8 validations | Full end-to-end validation requiring live external systems |

---

## Level 1: Sanity Checks

**Purpose:** Verify basic functionality. These MUST ALL PASS before proceeding to proxy evaluation.

### S1: Backend test suite passes without regressions

- **What:** Full pytest run over all backend tests (existing + new)
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest`
- **Expected:** Exit code 0, no failures, no errors
- **Failure means:** A plan introduced a regression in existing functionality. Block progression; identify failing test and fix.

### S2: Frontend build passes with no type errors

- **What:** `vue-tsc` type check + Vite production build
- **Command:** `cd /Users/neo/Developer/Projects/Agented && just build`
- **Expected:** Exit code 0, no TypeScript errors, `frontend/dist/` produced
- **Failure means:** A backend route change broke frontend API type assumptions, or a frontend component has type errors. Fix before proceeding.

### S3: Fernet encrypt/decrypt round-trip

- **What:** Encrypt a test string, decrypt it, verify identical output; confirm MultiFernet key rotation also decrypts old ciphertext
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
  from cryptography.fernet import Fernet, MultiFernet
  import os
  key_a = Fernet.generate_key()
  key_b = Fernet.generate_key()
  os.environ['AGENTED_VAULT_KEYS'] = key_a.decode()
  from app.services.secret_vault_service import SecretVaultService
  ct = SecretVaultService.encrypt('test-secret-value-123')
  pt = SecretVaultService.decrypt(ct, purpose='sanity-check', accessor='eval')
  assert pt == 'test-secret-value-123', f'Round-trip failed: got {pt!r}'
  # Key rotation: add key_b as primary, old ciphertext still decrypts
  os.environ['AGENTED_VAULT_KEYS'] = key_b.decode() + ',' + key_a.decode()
  SecretVaultService._fernet = None  # reset cache
  pt2 = SecretVaultService.decrypt(ct, purpose='rotation-check', accessor='eval')
  assert pt2 == 'test-secret-value-123', f'Key rotation failed: got {pt2!r}'
  print('Fernet round-trip and key rotation: OK')
  "
  ```
- **Expected:** `Fernet round-trip and key rotation: OK` with no exceptions
- **Failure means:** Encryption service is broken. The secrets vault cannot be trusted. Block all downstream plans (11-04, 11-06) that rely on vault credentials.

### S4: RBAC permission matrix — all 16 role-permission combinations

- **What:** Each of 4 roles tested against each of 4 permissions (read, execute, edit, manage). Expected matrix: viewer={read}, operator={read, execute}, editor={read, execute, edit}, admin={read, execute, edit, manage}
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_rbac.py -v -k "permission_matrix"`
- **Expected:** All 16 test cases pass; matrix matches RBAC0 specification
- **Failure means:** Permission boundaries are wrong. A Viewer can execute or an Editor can manage — security vulnerability. Fix before shipping.

### S5: RBAC decorator blocks unauthorized requests with 403

- **What:** HTTP call to a protected route with wrong role returns HTTP 403 (not 200, 401, or 500)
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_rbac.py -v -k "unauthorized or 403"`
- **Expected:** All role-blocking test cases pass; response status is 403
- **Failure means:** The `@require_role()` decorator is not being applied or is misconfigured. Security gap.

### S6: Secrets never appear in list API response

- **What:** `GET /admin/secrets` response JSON must not contain `encrypted_value` field or any plaintext credential
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_secret_vault.py -v -k "list_never_returns_value"`
- **Expected:** Test passes; `encrypted_value` field absent from all list response items
- **Failure means:** Secret values are leaking via the API. Security incident — do not ship.

### S7: YAML config export/import round-trip produces identical normalized output

- **What:** Export trigger to YAML → clear DB → import YAML → export again → compare normalized configs (strip timestamps)
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_config_export.py -v -k "roundtrip"`
- **Expected:** Normalized YAML strings are identical; no field loss
- **Failure means:** Config import is lossy. GitOps sync will silently corrupt configurations on repeated syncs.

### S8: All 4 integration adapters registered in ADAPTER_REGISTRY

- **What:** After importing the integrations module, all 4 adapter types are present in the registry
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
  from app.services.integrations import ADAPTER_REGISTRY
  required = {'slack', 'teams', 'jira', 'linear'}
  missing = required - set(ADAPTER_REGISTRY.keys())
  assert not missing, f'Missing adapters: {missing}'
  print(f'All adapters registered: {sorted(ADAPTER_REGISTRY.keys())}')
  "
  ```
- **Expected:** `All adapters registered: ['jira', 'linear', 'slack', 'teams']`
- **Failure means:** One or more adapters failed to register (import error, syntax error). NotificationService cannot dispatch to missing adapter types.

### S9: Slack slash command HMAC-SHA256 rejects invalid signature

- **What:** POST to `/api/integrations/slack/command` with incorrect signature header returns HTTP 401
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_slack_command.py -v -k "invalid_signature or expired_timestamp"`
- **Expected:** Tests for invalid signature and expired timestamp both return 401
- **Failure means:** Unauthenticated requests can trigger bot executions from any source. Security vulnerability.

### S10: Bookmark deep-link URL format is correct

- **What:** `BookmarkService.create_bookmark()` generates `/executions/{exec_id}#line-{N}` when line_number provided, `/executions/{exec_id}` without
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_bookmarks.py -v -k "deep_link"`
- **Expected:** Both URL format variants verified correct
- **Failure means:** Deep-links are malformed. Frontend cannot scroll to referenced log lines.

### S11: Semaphore limits campaign concurrency to maximum 5

- **What:** Attempting to acquire the campaign semaphore a 6th time while 5 are held must block (non-blocking acquire returns False)
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_campaigns.py -v -k "semaphore"`
- **Expected:** Test verifies 6th acquire fails with `blocking=False`; semaphore correctly initialized with value 5
- **Failure means:** Multi-repo campaigns can spawn unlimited concurrent subprocesses. System resource exhaustion risk.

### S12: Post-execution hook ImportError handled gracefully (not a crash)

- **What:** When `NotificationService` raises `ImportError` in `finish_execution()`, the execution still completes normally and logs at DEBUG (not WARNING)
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_post_execution_hooks.py -v -k "import_error"`
- **Expected:** Test passes; execution flow not interrupted; no WARNING-level log entry for the ImportError case
- **Failure means:** During test execution (where NotificationService may not be importable), executions crash. Also breaks the graceful bootstrap design.

**Sanity gate:** ALL 12 sanity checks must pass. Any single failure blocks progression.

---

## Level 2: Proxy Metrics

**Purpose:** Automated quality measurement using mocked external APIs and test fixtures.
**IMPORTANT:** These proxy metrics measure correctness of implementation contracts. They do not validate end-to-end latency with live services or real-world robustness. Treat results as necessary but not sufficient.

### P1: RBAC integration test coverage — 4 roles x existing route matrix

- **What:** RBAC decorator is applied to trigger management and team management routes; each role produces correct HTTP status
- **How:** Parameterized test with (role, route, method, expected_status) tuples
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_rbac.py -v`
- **Target:** All parameterized combinations pass; viewer gets 403 on POST/PUT/DELETE trigger routes; operator gets 403 on PUT trigger routes; editor passes trigger CRUD but gets 403 on team member management; admin passes all
- **Evidence from:** 11-RESEARCH.md#Verification-Strategy, Plan 11-01 Task 3 verification spec
- **Correlation with full metric:** HIGH — the test exercises the actual decorator with real HTTP requests (Flask test client)
- **Blind spots:** Does not test RBAC with real API key management (users must be provisioned first); does not catch routes added in future phases that omit the decorator
- **Validated:** No — awaiting deferred validation DEFER-11-01 for real auth flow integration

### P2: Audit trail SQLite persistence and indexed query performance

- **What:** Audit events written by `AuditLogService.log()` are queryable in SQLite by entity_type, actor, and date range within 500ms for 10K rows
- **How:** Seed 10K audit events, run filtered queries, time with `time.perf_counter()`
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_audit_persistence.py -v`
- **Target:** All query filter tests pass; 10K-row query completes in <500ms; in-memory ring buffer still populated for SSE
- **Evidence from:** 11-RESEARCH.md#Recommended-Metrics (audit query time target), Plan 11-01 Task 2 verification spec
- **Correlation with full metric:** HIGH — uses isolated_db fixture with actual SQLite, not a mock
- **Blind spots:** Test DB is in-memory or temp; production DB will be on disk (generally slower, but indexed queries should still be fast). Does not test under concurrent write load.
- **Validated:** No — awaiting deferred validation DEFER-11-05 for 100K+ event load test

### P3: Secret vault encryption throughput (<10ms per operation)

- **What:** Fernet encrypt and decrypt each complete in <10ms on test hardware
- **How:** Use `time.perf_counter()` in test; assert elapsed < 0.010 seconds per operation
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_secret_vault.py -v -k "performance"`
- **Target:** Both encrypt and decrypt complete in <10ms (Fernet is CPU-bound AES-128-CBC; 10ms is well within range for a single operation)
- **Evidence from:** 11-RESEARCH.md#Recommended-Metrics (secret encrypt/decrypt time target)
- **Correlation with full metric:** MEDIUM — test hardware may differ from production; Fernet is fast enough that this threshold is rarely a concern in practice
- **Blind spots:** Does not test bulk throughput (100+ operations). Execution service calls `get_secrets_for_execution()` which decrypts all global secrets — if there are 50 secrets, that is 50 decrypt calls chained together.
- **Validated:** No — awaiting deferred validation DEFER-11-02 for bulk throughput test

### P4: Secret injection into ExecutionService subprocess env

- **What:** `SecretVaultService.get_secrets_for_execution()` returns dict with `AGENTED_SECRET_` prefix keys; ExecutionService merges them into subprocess env
- **How:** Mock vault, verify `env_overrides` dict populated correctly in ExecutionService
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_secret_vault.py -v -k "execution"`
- **Target:** Dict keys prefixed with `AGENTED_SECRET_`; no plaintext values in logs; vault failure does not break execution
- **Evidence from:** Plan 11-02 Task 3 verification spec
- **Correlation with full metric:** HIGH — tests the actual injection code path with mock vault
- **Blind spots:** Does not verify the subprocess actually receives and can read the env vars (would require a real subprocess run)
- **Validated:** No — awaiting deferred validation DEFER-11-02

### P5: Config export/import lossless round-trip (YAML and JSON)

- **What:** Export trigger → import on clean DB → export again → normalize (strip `exported_at` timestamp) → string comparison
- **How:** Automated test with real DB operations (isolated_db fixture)
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_config_export.py -v`
- **Target:** Normalized YAML strings identical; upsert updates existing trigger by name (no duplicate created); sensitive fields (webhook_secret) not present in exported YAML
- **Evidence from:** Plan 11-03 must_haves, 11-RESEARCH.md#config-export-as-yaml pattern
- **Correlation with full metric:** HIGH — tests actual DB operations, not mocks
- **Blind spots:** Does not test all trigger field types (scheduled triggers with all schedule variants). Does not test import of maliciously crafted YAML (security fuzzing).
- **Validated:** No — awaiting deferred validation DEFER-11-03 (GitOps integration)

### P6: Slack adapter called with correct Block Kit format (mocked)

- **What:** `NotificationService.on_execution_complete()` calls `SlackAdapter.send_notification()` with well-formed Block Kit blocks structure
- **How:** Mock `slack_sdk.WebClient.chat_postMessage`; verify call arguments
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_integrations.py -v -k "slack"`
- **Target:** `chat_postMessage` called with `channel`, `text` (fallback), and `blocks` (list with section blocks containing status and duration fields)
- **Evidence from:** 11-RESEARCH.md#slack-notification-after-execution code example, Plan 11-04 Task 2
- **Correlation with full metric:** MEDIUM — Slack API compatibility verified by mocking; does not test Slack's Block Kit rendering or message delivery
- **Blind spots:** Mocked `WebClient` does not validate that blocks are actually renderable by Slack. Rate limiting and token scope issues not tested.
- **Validated:** No — awaiting deferred validation DEFER-11-04 (live Slack workspace)

### P7: JIRA adapter creates issue with correct severity-to-priority mapping (mocked)

- **What:** `JiraAdapter.create_ticket()` maps critical→Highest, high→High, medium→Medium, low→Low with correct issue type and labels
- **How:** Mock `jira.JIRA.create_issue`; verify `fields` argument matches expected structure
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_integrations.py -v -k "jira"`
- **Target:** All 4 severity→priority mappings verified; labels contain `["agented", "automated"]`; issue type is `Bug`
- **Evidence from:** 11-RESEARCH.md#jira-issue-creation-from-findings code example, Plan 11-04 Task 2
- **Correlation with full metric:** MEDIUM — field structure verified but JIRA field requirements vary by project configuration; some projects require fields this test doesn't cover
- **Blind spots:** Custom fields, required fields per JIRA project schema, JIRA authentication expiry
- **Validated:** No — awaiting deferred validation DEFER-11-04 (live JIRA instance)

### P8: Teams adapter sends correct MessageCard payload (mocked)

- **What:** `TeamsAdapter.send_notification()` posts valid MessageCard JSON to webhook URL with correct color coding and facts
- **How:** Mock `httpx.post`; verify request body structure
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_integrations.py -v -k "teams"`
- **Target:** `@type: MessageCard`, `themeColor` is `00FF00` for success / `FF0000` for failure; `sections[0].facts` includes Status and Duration; 10s timeout respected
- **Evidence from:** 11-RESEARCH.md#teams-incoming-webhook-notification code example, Microsoft Teams Incoming Webhooks docs
- **Correlation with full metric:** MEDIUM — MessageCard format is deprecated (Teams moving to Adaptive Cards via Power Automate); mocked test may not reflect future Teams behavior
- **Blind spots:** Microsoft Teams deprecated O365 Connectors in 2024; this adapter may require migration to Adaptive Cards via Power Automate Workflows in the near future. This proxy test validates current implementation but real-world delivery may fail if Teams connector support is fully removed.
- **Validated:** No — awaiting deferred validation DEFER-11-04

### P9: Notification dispatch completes without blocking (background threading)

- **What:** `NotificationService.on_execution_complete()` returns immediately (dispatches to background thread); does not block caller
- **How:** Time the call with `time.perf_counter()`; verify it returns in <100ms (background thread started but not awaited)
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_integrations.py -v -k "non_blocking or timing"`
- **Target:** `on_execution_complete()` returns in <100ms; background thread created (verify via mock)
- **Evidence from:** 11-RESEARCH.md Anti-Pattern: "Blocking the webhook response"; Plan 11-04 Task 3 non-blocking requirement
- **Correlation with full metric:** HIGH — if the function returns in <100ms, it is definitely non-blocking
- **Blind spots:** Does not test what happens when many background threads accumulate (thread pool exhaustion at high concurrency)
- **Validated:** No — awaiting deferred validation DEFER-11-06 (load test)

### P10: GitOps sync applies YAML changes via import_trigger(upsert=True) (mocked git)

- **What:** `GitOpsSyncService.sync_repo()` with mocked git operations detects YAML file change and calls `ConfigExportService.import_trigger()` with `upsert=True`
- **How:** Mock `subprocess.run` for git operations; create temp YAML files; verify import called with upsert flag
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_gitops.py -v`
- **Target:** Import called with `upsert=True`; existing trigger updated (not duplicated); conflict detected and logged when both sides changed; dry-run returns preview without DB modification
- **Evidence from:** Plan 11-05 Task 1 and 2 verification specs
- **Correlation with full metric:** MEDIUM — git operations fully mocked; does not test real clone/pull performance or large config files
- **Blind spots:** Does not test private repo access (SSH key / token authentication). Does not test merge conflicts in YAML (overlapping changes between Git and UI).
- **Validated:** No — awaiting deferred validation DEFER-11-05 (live git repo)

### P11: Multi-repo campaign dispatches to all repos, respects semaphore (mocked execution)

- **What:** `CampaignService.start_campaign()` with N repos creates N execution entries; semaphore limits to 5 concurrent; partial failure (1 of 3 fails) results in `partial_failure` status
- **How:** Mock `OrchestrationService.execute_with_fallback`; verify campaign_executions table populated with N rows
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_campaigns.py -v`
- **Target:** N campaign_execution rows created; campaign status transitions: pending→running→completed or partial_failure; semaphore blocks 6th concurrent acquire
- **Evidence from:** Plan 11-06 Task 1 and 2 verification specs, 11-RESEARCH.md Pitfall 5
- **Correlation with full metric:** MEDIUM — execution mocked; does not test real subprocess overhead per repo
- **Blind spots:** Does not test campaign with 10+ repos (memory and thread pressure). Does not test campaign cancellation mid-execution.
- **Validated:** No — awaiting deferred validation DEFER-11-06 (real repo campaign)

### P12: Slack slash command parsing and dispatch (mocked execution)

- **What:** `/agented run <trigger-name> on <target>` parsed correctly; execution dispatched in background thread; immediate ephemeral response returned
- **How:** Post valid signed slash command payload to Flask test client; mock ExecutionService; verify parse and dispatch
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_slack_command.py -v`
- **Target:** All parsing test cases pass; unknown trigger returns error response; response returned within 3s window (verify response does not block on execution)
- **Evidence from:** Plan 11-04 Task 3, Slack API 3-second response requirement
- **Correlation with full metric:** HIGH — tests actual endpoint with Flask test client; signing secret mocked via SecretVaultService mock
- **Blind spots:** Does not test Slack's webhook retry behavior. Does not test response_url callback (delayed response after execution completes).
- **Validated:** No — awaiting deferred validation DEFER-11-04

### P13: Bookmark CRUD and tag-based search

- **What:** Create/read/update/delete bookmark operations work; tags stored and searchable; list by trigger_id returns correct subset
- **How:** Standard CRUD tests with isolated_db fixture
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_bookmarks.py -v`
- **Target:** All CRUD test cases pass; tag search returns only matching bookmarks; trigger_id filter returns only that trigger's bookmarks
- **Evidence from:** Plan 11-03 Task 2 verification spec, INT-08 requirement
- **Correlation with full metric:** HIGH — tests actual DB operations
- **Blind spots:** Does not test bookmark display in frontend (deferred). Tags stored as comma-separated string — search is a LIKE query, not full-text search; complex tag queries may behave unexpectedly.
- **Validated:** No — awaiting deferred validation DEFER-11-03 (frontend UI)

### P14: Vault unconfigured state handled gracefully (503 for API, silent skip for execution)

- **What:** When `AGENTED_VAULT_KEYS` not set, API returns HTTP 503 with clear message; execution proceeds without error
- **How:** Test with `AGENTED_VAULT_KEYS` unset in env; verify API responses and execution path
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_secret_vault.py -v -k "unconfigured"`
- **Target:** `GET /admin/secrets` → 503 with `{"error": "Vault not configured"}`; execution test with mocked vault skip → completes without exception
- **Evidence from:** Plan 11-02 verification spec, graceful bootstrap design
- **Correlation with full metric:** HIGH — tests actual error handling code paths
- **Blind spots:** Does not test partial configuration (malformed Fernet key in env var)
- **Validated:** No — in-phase validation sufficient for this check; no deferred validation needed

---

## Level 3: Deferred Validations

**Purpose:** Full end-to-end evaluation requiring live external systems or resources not available during development.

### D1: RBAC with real authentication flow — DEFER-11-01

- **What:** RBAC enforcement tested with real API key provisioning workflow: create API key → assign role → make authenticated requests → verify access controls
- **How:** Manual or automated end-to-end test against a running server instance with real HTTP clients
- **Why deferred:** The current app has no user authentication system. RBAC operates on API-key-based identity (per RESEARCH.md Open Question 1). Full validation of the auth+RBAC integration requires a running server and provisioned test keys — not available in isolated_db test context.
- **Validates at:** Manual QA session after phase deployment, or a future phase adding full authentication
- **Depends on:** Running Agented server instance with AGENTED_VAULT_KEYS set; at least one API key created via RBAC routes
- **Target:** 100% of protected routes blocked for incorrect roles; 100% of allowed routes pass for correct roles; audit log records every denial
- **Risk if unmet:** RBAC has implementation bugs not caught by mocked tests. Route missing decorator is the most likely failure mode. Impact: security gap — unauthorized users can perform privileged operations.
- **Fallback:** Add a startup check that scans all registered routes and warns if admin-level routes lack the `@require_role()` decorator (RESEARCH.md Pitfall 4).

### D2: Secrets vault bulk throughput and key recovery — DEFER-11-02

- **What:** Encryption throughput at 100+ simultaneous operations; key backup and recovery procedure validated
- **How:** Benchmark test with 100 concurrent encrypt/decrypt calls; simulate key loss and recovery with MultiFernet
- **Why deferred:** Single-operation <10ms target is verifiable in-phase. Bulk throughput (e.g., `get_secrets_for_execution()` with 50+ secrets) requires production-scale secret count. Key recovery procedure requires documentation and a separate operational runbook, not a unit test.
- **Validates at:** Operational review before production deployment
- **Depends on:** Production server with populated secrets vault and documented backup procedure
- **Target:** `get_secrets_for_execution(50 secrets)` completes in <500ms; key recovery from backup restores all secrets within 5 minutes
- **Risk if unmet:** Execution startup latency grows with vault size. Key loss = all secrets unrecoverable.
- **Fallback:** Cache decrypted secrets in-process for TTL period; document key backup as mandatory setup step.

### D3: Config export/import with GitOps in production — DEFER-11-03

- **What:** Export all triggers → commit YAML to Git repo → GitOps sync applies on next poll cycle → verify DB matches YAML → modify via UI → GitOps re-applies Git version (conflict resolution)
- **How:** Manual or automated end-to-end test with a real git repository (GitHub/GitLab)
- **Why deferred:** GitOps sync requires a real git remote; subprocess.run git operations cannot be meaningfully mocked for the full cycle including authentication, clone performance, and remote push notification.
- **Validates at:** After plan 11-05 deployment to a staging environment with a real git repo
- **Depends on:** Configured git remote; AGENTED_VAULT_KEYS set; at least one trigger existing in DB
- **Target:** Sync cycle completes in <120s for a repo with 10 YAML files; conflict detection logs warning; Git-wins policy applied
- **Risk if unmet:** GitOps conflict resolution silently corrupts configurations. Impact: medium — affects only users who manage configuration via both UI and Git simultaneously.
- **Fallback:** Restrict GitOps to read-only mode (dry-run only) until full conflict resolution is validated.

### D4: End-to-end Slack integration with live workspace — DEFER-11-04

- **What:** Configure Slack adapter with real bot token → trigger bot execution → verify Slack message delivered to target channel within 30 seconds → send slash command from Slack → verify execution triggered and response delivered
- **How:** Manual test against a real Slack workspace with a test Agented bot app installed
- **Why deferred:** Requires real Slack workspace, installed bot app with correct OAuth scopes, and a running Agented server reachable from the internet (for slash command webhook)
- **Validates at:** Manual QA session with Slack test workspace configured
- **Depends on:** Live Agented server with public URL; Slack bot app configured with `chat:write` and `commands` scopes; `AGENTED_VAULT_KEYS` set; Slack token and signing secret stored in vault
- **Target:** Notification delivered within 30 seconds of execution completion; slash command acknowledged within 3 seconds; execution result posted as delayed response within 60 seconds
- **Risk if unmet:** Slack integration ships but does not deliver messages due to OAuth scope misconfiguration (RESEARCH.md Pitfall 1). Impact: INT-01 requirement unmet.
- **Fallback:** Provide webhook-based integration as fallback (simpler than bot token, no scope management). Teams integration (webhook-only, no app installation) as alternative for initial rollout.

### D5: End-to-end JIRA/Linear integration with live instances — DEFER-11-04

- **What:** Configure JIRA adapter with real API token → trigger security bot execution → verify JIRA issue created with correct priority, labels, and description within 60 seconds
- **How:** Manual test against a real JIRA Cloud or Server instance with a test project
- **Why deferred:** Requires real JIRA instance; JIRA project configuration varies (required fields, field schemes) and cannot be generalized in mocked tests
- **Validates at:** Manual QA session with JIRA test project configured
- **Depends on:** JIRA instance accessible from Agented server; API token stored in vault; project key configured in integration; issues create permission granted
- **Target:** Issue created within 60 seconds; severity-to-priority mapping correct; issue URL returned in execution log
- **Risk if unmet:** JIRA field requirements differ from what adapter sends — `create_issue` call fails with 400. Impact: INT-02 requirement unmet.
- **Fallback:** Support user-configurable field mapping (per-project override) to handle JIRA schema variability.

### D6: GitOps sync with real GitHub/GitLab webhook — DEFER-11-05

- **What:** Push a YAML config change to a watched Git branch → GitHub/GitLab fires webhook → Agented applies change within 30 seconds (webhook-triggered sync, not polling)
- **How:** Live integration test with a real git host and publicly accessible Agented server
- **Why deferred:** Webhook-triggered sync requires a publicly accessible server; polling is testable in-phase but webhook delivery requires external infrastructure
- **Validates at:** Staging environment with public URL and git webhook configured
- **Depends on:** Public Agented URL; git repo with webhook pointing to `/admin/gitops/webhook`; changes to push
- **Target:** Config change applied within 30s of git push (webhook) or within 90s (polling fallback at 60s interval)
- **Risk if unmet:** GitOps only works via polling, introducing 60-second lag between config change and application. Impact: acceptable degradation (polling still works), but webhook path remains untested.
- **Fallback:** Document polling-only mode as the supported configuration; webhook-triggered sync as future enhancement.

### D7: Multi-repo campaign with 10+ real repositories — DEFER-11-06

- **What:** Launch a campaign against 10+ real git repositories; verify all repos processed; semaphore limits peak to 5 concurrent; campaign completes within reasonable wall-clock time
- **How:** Live campaign run with real repositories (can be mock repos with simple content)
- **Why deferred:** Requires real subprocess execution (clone, run bot, capture output) across multiple repos. Real I/O latency and subprocess overhead cannot be simulated.
- **Validates at:** Staging environment with 10+ accessible git repos
- **Depends on:** 10+ git repos accessible via SSH or HTTPS; bot trigger configured; vault secrets available for execution
- **Target:** Campaign completes within `single_repo_time * 1.5` (semaphore concurrency reduces total time vs serial); semaphore never allows >5 simultaneous subprocesses (verified via process count monitoring)
- **Risk if unmet:** Campaign performance is worse than expected (semaphore too conservative) or system resources exhausted (semaphore not effective). Impact: INT-07 requirement met functionally but not operationally.
- **Fallback:** Reduce max concurrency from 5 to 3 if resource pressure observed. Add configurable concurrency limit per campaign.

### D8: Audit trail load test with 100K+ events — DEFER-11-05

- **What:** Audit events table at 100K+ rows; query by date range and entity_type completes in <500ms; retention cleanup job removes events older than 90 days
- **How:** Seed 100K rows to audit_events table; run timed queries; trigger retention cleanup job
- **Why deferred:** Seeding 100K rows is a slow test setup not appropriate for the per-test isolated_db fixture. Requires dedicated load testing setup.
- **Validates at:** Performance testing session against a populated DB
- **Depends on:** Populated audit_events table (100K rows); retention cleanup job configured in APScheduler
- **Target:** `SELECT ... WHERE created_at > ? AND entity_type = ?` in <500ms with indexed columns; cleanup deletes correct rows; DB file size stabilizes after cleanup
- **Risk if unmet:** Audit history page loads slowly at production scale. Impact: usability degradation. SQLite with proper indexes handles millions of rows well — this risk is LOW but worth validating.
- **Fallback:** Add retention policy UI to let admins configure cleanup threshold. Add `EXPLAIN QUERY PLAN` assertions in tests to verify index usage.

---

## Ablation Plan

**Purpose:** Verify that each security/correctness mechanism actually works in isolation.

### A1: RBAC disabled mode (no roles configured) — all routes pass

- **Condition:** `user_roles` table is empty; `get_role_for_api_key()` returns None for any key
- **Expected impact:** All routes pass (graceful bootstrap), consistent with Plan 11-01 Task 1 design ("when no roles exist in DB, RBAC is disabled")
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_rbac.py -v -k "disabled or bootstrap or no_roles"`
- **Evidence:** Plan 11-01 Task 1 action spec; backward compatibility requirement (existing users without RBAC configured must not be locked out)

### A2: Notification dispatch with integrations disabled — execution still completes

- **Condition:** All integrations disabled (`enabled=0` in DB) for a trigger
- **Expected impact:** `NotificationService.on_execution_complete()` finds no enabled integrations; dispatches nothing; execution log shows normal completion without errors
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_integrations.py -v -k "no_integrations or disabled"`
- **Evidence:** Plan 11-04 Task 3; non-integration users must not be affected by integration framework

### A3: GitOps dry-run vs. apply — DB state changes only on non-dry-run

- **Condition:** Call `sync_repo(dry_run=True)` then `sync_repo(dry_run=False)` with same config changes
- **Expected impact:** dry_run returns list of pending changes, DB unchanged; non-dry_run applies changes and DB reflects YAML
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_gitops.py -v -k "dry_run"`
- **Evidence:** Plan 11-05 Task 1 dry-run requirement; critical for operators to preview changes before applying

### A4: Vault failure isolation — execution proceeds without secrets

- **Condition:** `SecretVaultService.get_secrets_for_execution()` raises an exception (e.g., corrupt key)
- **Expected impact:** ExecutionService logs a warning, continues execution without AGENTED_SECRET_* env vars; execution does not crash
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_secret_vault.py -v -k "vault_failure_isolation"`
- **Evidence:** Plan 11-02 Task 3 graceful degradation requirement; execution availability must not depend on vault health

---

## WebMCP Tool Definitions

WebMCP tool definitions skipped — phase does not modify frontend views.

Phase 11 is entirely backend-focused (services, routes, DB schema). No HTML, JSX, TSX, Vue, or CSS files are listed in any plan's `files_modified`. The phase adds new admin API endpoints but no corresponding frontend pages.

---

## Baselines

| Baseline | Description | Expected Score | Source |
|----------|-------------|----------------|--------|
| Notification latency (before phase) | No notification system exists — manual checking only | Infinity (no automation) | 11-RESEARCH.md experiment design |
| Audit persistence (before phase) | In-memory ring buffer, 500 events max, lost on restart | 0% persistence across restarts | Existing AuditLogService in codebase |
| RBAC enforcement (before phase) | No access control — all routes open | 0% enforcement | Existing codebase (no auth) |
| Secret storage (before phase) | No vault — credentials stored in plaintext env vars or omitted | 0% encrypted at rest | Existing codebase |
| Config portability (before phase) | No export/import — configuration locked to DB | 0% portability | Existing codebase |
| Multi-repo campaigns (before phase) | Single-trigger single-repo only | 1 repo per execution | Existing ExecutionService |

---

## Evaluation Scripts

**Location of evaluation code:**
```
backend/tests/test_rbac.py                    # Plan 11-01 — RBAC and role enforcement
backend/tests/test_audit_persistence.py       # Plan 11-01 — Audit trail SQLite persistence
backend/tests/test_secret_vault.py            # Plan 11-02 — Fernet encryption, vault API
backend/tests/test_config_export.py           # Plan 11-03 — Config export/import round-trip
backend/tests/test_bookmarks.py               # Plan 11-03 — Execution bookmarks and deep-links
backend/tests/test_integrations.py            # Plan 11-04 — Adapter framework and notification dispatch
backend/tests/test_slack_command.py           # Plan 11-04 — Slash command HMAC verification and parsing
backend/tests/test_gitops.py                  # Plan 11-05 — GitOps sync engine (mocked git)
backend/tests/test_campaigns.py               # Plan 11-06 — Multi-repo campaign orchestration
backend/tests/test_post_execution_hooks.py    # Plan 11-06 — Post-execution notification hooks
```

**How to run full evaluation suite:**
```bash
# Level 1 sanity gate (run all tests, verify no regressions)
cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest

# Level 1 sanity gate (frontend build)
cd /Users/neo/Developer/Projects/Agented && just build

# Level 2 proxy metrics (plan-by-plan)
cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_rbac.py tests/test_audit_persistence.py -v
cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_secret_vault.py -v
cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_config_export.py tests/test_bookmarks.py -v
cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_integrations.py tests/test_slack_command.py -v
cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_gitops.py -v
cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_campaigns.py tests/test_post_execution_hooks.py -v
```

---

## Results Template

*To be filled by grd-eval-reporter after phase execution.*

### Sanity Results

| Check | Status | Output | Notes |
|-------|--------|--------|-------|
| S1: pytest full suite | [PASS/FAIL] | | |
| S2: just build | [PASS/FAIL] | | |
| S3: Fernet round-trip + key rotation | [PASS/FAIL] | | |
| S4: RBAC permission matrix 16 combos | [PASS/FAIL] | | |
| S5: Decorator blocks with 403 | [PASS/FAIL] | | |
| S6: Secrets not in list API response | [PASS/FAIL] | | |
| S7: YAML config round-trip lossless | [PASS/FAIL] | | |
| S8: All 4 adapters registered | [PASS/FAIL] | | |
| S9: HMAC rejects invalid signature | [PASS/FAIL] | | |
| S10: Bookmark deep-link format correct | [PASS/FAIL] | | |
| S11: Semaphore limits to 5 concurrent | [PASS/FAIL] | | |
| S12: ImportError handled at DEBUG level | [PASS/FAIL] | | |

### Proxy Results

| Metric | Target | Actual | Status | Notes |
|--------|--------|--------|--------|-------|
| P1: RBAC integration tests | All pass | | [MET/MISSED] | |
| P2: Audit query <500ms @ 10K | <500ms | | [MET/MISSED] | |
| P3: Fernet ops <10ms | <10ms | | [MET/MISSED] | |
| P4: Secrets injected into exec env | AGENTED_SECRET_* prefix | | [MET/MISSED] | |
| P5: Config round-trip lossless | Identical normalized YAML | | [MET/MISSED] | |
| P6: Slack Block Kit format | Verified structure | | [MET/MISSED] | |
| P7: JIRA severity→priority mapping | All 4 mappings correct | | [MET/MISSED] | |
| P8: Teams MessageCard payload | Verified structure | | [MET/MISSED] | |
| P9: Notification non-blocking | Returns in <100ms | | [MET/MISSED] | |
| P10: GitOps applies via upsert | No duplicates created | | [MET/MISSED] | |
| P11: Campaign dispatches to N repos | Semaphore at 5 | | [MET/MISSED] | |
| P12: Slash command parsed correctly | All parse cases pass | | [MET/MISSED] | |
| P13: Bookmark CRUD + tag search | All test cases pass | | [MET/MISSED] | |
| P14: Vault unconfigured → 503 | Graceful degradation | | [MET/MISSED] | |

### Ablation Results

| Condition | Expected | Actual | Conclusion |
|-----------|----------|--------|------------|
| A1: RBAC disabled (no roles) | All routes pass | | |
| A2: Integrations all disabled | Execution completes normally | | |
| A3: GitOps dry-run vs apply | DB unchanged on dry-run | | |
| A4: Vault failure isolation | Execution proceeds without secrets | | |

### Deferred Status

| ID | Metric | Status | Validates At |
|----|--------|--------|-------------|
| DEFER-11-01 | RBAC with real auth flow | PENDING | Manual QA / future auth phase |
| DEFER-11-02 | Vault bulk throughput + key recovery | PENDING | Operational review pre-deployment |
| DEFER-11-03 | GitOps full cycle with real git remote | PENDING | Staging environment |
| DEFER-11-04 | Live Slack workspace end-to-end | PENDING | Manual QA with Slack test workspace |
| DEFER-11-04 | Live JIRA/Linear end-to-end | PENDING | Manual QA with JIRA test project |
| DEFER-11-05 | GitOps webhook-triggered sync | PENDING | Staging with public URL + webhook |
| DEFER-11-06 | Campaign with 10+ real repos | PENDING | Staging environment |
| DEFER-11-05 | Audit trail 100K+ event load test | PENDING | Performance testing session |

---

## Evaluation Confidence

**Overall confidence in evaluation design:** MEDIUM-HIGH

**Justification:**

- **Sanity checks:** ADEQUATE — 12 checks cover the critical security properties (RBAC enforcement, secret non-disclosure, HMAC verification) and structural correctness (round-trip fidelity, adapter registration). All are executable with exact commands.

- **Proxy metrics:** WELL-EVIDENCED for backend correctness — 11-RESEARCH.md provides quantitative targets (10ms encryption, 500ms audit query, 30s notification) that translate directly to automated assertions. However, proxy confidence for external adapter behavior is MEDIUM because mocked external APIs do not validate server-side schema requirements (JIRA field configuration, Slack OAuth scopes).

- **Deferred coverage:** PARTIAL but ACKNOWLEDGED — the most important deferred items (live Slack, live JIRA, real git remote) cannot be automated without external infrastructure. All deferred items have specific validates_at references and fallback plans. The Teams adapter has an acknowledged risk (Microsoft deprecation of O365 Connectors) that may require migration before real-world validation is possible.

**What this evaluation CAN tell us:**
- Whether RBAC enforcement is implemented correctly for the defined 4-role permission matrix
- Whether secrets are encrypted at rest and never exposed via API
- Whether config export/import is lossless and upsert semantics work for GitOps
- Whether external adapters call the correct APIs with correctly-shaped payloads (mocked)
- Whether notification dispatch is non-blocking and does not break execution flow
- Whether multi-repo campaigns respect the 5-concurrent-execution semaphore limit

**What this evaluation CANNOT tell us (and when it will be addressed):**
- Whether Slack/Teams messages are actually delivered and rendered correctly in-app — deferred to manual QA (DEFER-11-04)
- Whether JIRA field requirements match all target project configurations — deferred to JIRA integration QA (DEFER-11-04)
- Whether GitOps sync is fast enough with a real git remote (clone time, network latency) — deferred to staging (DEFER-11-03)
- Whether RBAC has gaps on routes added in future phases — risk noted; startup route scanner recommended
- Whether Microsoft's Teams connector deprecation (2024) affects this adapter before real-world testing — noted in P8 blind spots

---

*Evaluation plan by: Claude (grd-eval-planner)*
*Design date: 2026-03-04*
