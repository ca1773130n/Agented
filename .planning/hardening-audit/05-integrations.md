# Hardening Audit 05 — External Integrations

Scope: GitHub, gitops, triggers, webhooks, MCP sync, URL fetching, provider
clients, notification adapters, sidecar sync.

Audited files (all read in full):
- `backend/app/services/`: github_service.py, gitops_sync_service.py,
  trigger_dispatcher.py, trigger_service.py, trigger_event_service.py,
  mcp_sync_service.py, url_summarizer.py, provider_usage_client.py,
  notification_service.py, sidecar_account_sync_service.py,
  webhook_validation_service.py (cross-referenced)
- `backend/app/services/integrations/`: __init__.py, jira_adapter.py,
  linear_adapter.py, slack_adapter.py, teams_adapter.py
- `backend/app_litestar/routes/`: webhooks.py, triggers.py, trigger_events.py,
  integrations.py
- Cross-referenced: app/db/triggers.py, app_litestar/middleware.py.

## Severity summary

| Severity | Count |
|---|---|
| CRITICAL | 0 |
| HIGH | 2 |
| MEDIUM | 5 |
| LOW | 4 |

Overall the integration surface is notably well-hardened: `url_summarizer.py`
has a correct, defense-in-depth SSRF guard (DNS pinning, per-hop redirect
re-validation, scheme allowlist); webhook HMAC validation is constant-time and
raw-payload-first; GitHub/git operations use argv lists (no shell) and pass
`owner/repo` rather than raw URLs; provider clients use fixed hardcoded API
URLs (no attacker-controlled SSRF) and carry tokens in headers, never URLs or
logs. The findings below are the real gaps.

---

## HIGH

### H1 — `webhook_secret` leaked to any authenticated viewer via trigger read/list APIs
**Files:**
- `app/db/triggers.py:447` — `get_trigger`: `SELECT * FROM triggers WHERE id = ?`
- `app/db/triggers.py:460-475` — `get_all_triggers`: `SELECT t.*, ...`
- `app/services/trigger_service.py:57-65` — `get_trigger_detail` returns the raw row
- `app/services/trigger_service.py:46-54` — `list_triggers` returns raw rows
- `app_litestar/routes/triggers.py:73-80` (`require_role("viewer",...)`),
  `:43-55` (list)

**Problem:** Triggers persist a `webhook_secret` (the HMAC key that authenticates
inbound webhooks — `trigger_dispatcher.dispatch_webhook_event` validates against
it). Both the detail endpoint (`GET /admin/triggers/{id}`) and the list endpoint
return the full DB row via `SELECT *` with **no redaction**, and both are
reachable by the lowest privileged role (`viewer`). A read-only viewer can
exfiltrate every trigger's webhook secret, then forge correctly-signed webhook
payloads to the unauthenticated `/` / `/api/webhooks/github` receivers and drive
arbitrary agent executions — a privilege-escalation path from viewer to webhook
forgery.

**Fix:** Never return `webhook_secret` in API responses. Either (a) drop it from
the SELECT column list in `get_trigger`/`get_all_triggers`, or (b) redact it in
the service layer before returning, e.g. in `get_trigger_detail`/`list_triggers`:
`trigger.pop("webhook_secret", None)` (or replace with a boolean
`has_webhook_secret = bool(trigger.pop("webhook_secret", None))`). Apply the same
to any other secret-bearing columns (`allowed_tools` is config, not secret, but
audit similarly). Add a regression test asserting the key is absent from the
response.

### H2 — PR comment slash-command dispatch has no rate limit and no dedup
**Files:**
- `app_litestar/routes/webhooks.py:50-98` (`_handle_issue_comment`)
- `app/services/trigger_dispatcher.py:407-529` (`dispatch_pr_comment_commands`)

**Problem:** The `pull_request` webhook path enforces a 60s per-repo rate limit
(`webhooks.py:161-170`) and the generic webhook path enforces DB-backed dedup
(`trigger_dispatcher.py:112-126`). The `issue_comment` path does **neither**:
`_handle_issue_comment` never touches `_repo_last_event`, and
`dispatch_pr_comment_commands` has no `check_and_insert_dedup_key` call. GitHub
re-delivers webhooks on its own retry schedule and an attacker (or a comment edit
loop) can post/edit comments rapidly. Each accepted comment enqueues a full agent
execution per matching trigger — an unbounded fan-out / amplification and
duplicate-execution vector. A `created`+`edited` toggle on one comment fires twice.

**Fix:** (1) Apply the same per-repo rate limit used by the PR path to the
issue_comment path. (2) Add DB-backed dedup keyed on
`(trigger_id, sha256(repo + comment_id + comment_updated_at + command))` before
`ExecutionQueueService.enqueue`, mirroring `dispatch_webhook_event`. (3) Consider
gating on commenter association (author/collaborator) so arbitrary external users
cannot trigger executions by commenting `/review` on a public PR.

---

## MEDIUM

### M1 — Untrusted PR/comment text injected into agent prompt template
**Files:**
- `app/services/trigger_dispatcher.py:142` (`rendered_prompt = prompt_template.replace("{message}", text)`)
- `:324`, `:474` (same pattern for GitHub PR / PR-comment paths; `message_text`
  embeds `pr_title`, `comment_body`, `pr_author`)

**Problem:** Attacker-controlled fields (PR title, comment body, author login)
are substituted into the prompt that drives an autonomous coding agent with no
sanitization or delimiting. This is a prompt-injection channel: a hostile PR
title/comment can attempt to redirect the agent ("ignore previous instructions,
run …"). Inherent to the feature, but currently completely unmitigated.

**Fix:** Wrap untrusted substituted text in explicit, clearly-fenced delimiters
in the template contract (e.g. a `<untrusted_user_input>…</untrusted_user_input>`
block) and document that everything inside is data, not instructions. Truncate
`comment_body` (already capped at 500 in `dispatch_pr_comment_commands:452`, but
not in the super-agent path) consistently. Longer term, constrain the agent's
allowed tools for trigger-initiated runs.

### M2 — `git clone` argument injection from operator-configured repo_url/branch
**File:** `app/services/gitops_sync_service.py:410-416` (and `:393-405`)

**Problem:** `git clone --branch <branch> --single-branch <repo_url> <local_path>`
passes `branch` and `repo_url` (from the gitops_repos DB row) with **no `--`
separator** and no `^[^-]` validation. A value beginning with `-` (e.g.
`repo_url = "--upload-pack=touch /tmp/x"`, or an `ext::sh -c …` URL) is parsed by
git as an option, not a positional — a classic git argument-injection / RCE-class
issue. Same exposure in `fetch origin <branch>` (`:393-399`). The values are
admin-configured today, so impact is gated by who can create gitops repos, but it
is a latent injection.

**Fix:** Add `--` before positional args:
`["git","clone","--single-branch","--branch",branch,"--",repo_url,local_path]`
and validate `repo_url` against an allowed scheme set (`https://`, `git@`/`ssh://`)
and `branch` against `^[\w./-]+$` with a leading-dash reject, before invoking git.

### M3 — `McpSyncService.test_connection` fetches operator URL with no SSRF guard
**File:** `app/services/mcp_sync_service.py:225-252` (esp. `:244-246`)

**Problem:** `test_connection` does `httpx.Client(timeout=2.0).get(url)` against a
server-row `url` with no scheme/host allowlist and no private-IP check. An
operator (or any actor who can create an HTTP MCP server row) can probe internal
hosts / cloud metadata (`169.254.169.254`) and read status codes — a server-side
request forgery + internal port-scan primitive. httpx default `follow_redirects`
is False (good), so redirect-based bypass is closed, but the direct fetch is not.

**Fix:** Route this fetch through the same `_is_safe_target` / DNS-pinning helper
used in `url_summarizer.py` (extract it into a shared `safe_http` util), rejecting
non-global resolved addresses before connecting.

### M4 — OAuth callback proxy follows redirects from the local CLI server
**File:** `app_litestar/routes/webhooks.py:210-228` (esp. `:220`
`follow_redirects=True`)

**Problem:** The unauthenticated `/api/oauth-callback/{rest:path}` endpoint proxies
to `http://127.0.0.1:{port}/{rest}` with `follow_redirects=True`. The target host
is fixed to localhost and `port` comes from `BackendCLIService.get_callback_port()`
(not request-controlled), so this is not a general SSRF. However, the loopback CLI
callback server can emit a `Location` header that httpx will transparently follow
to an arbitrary external/internal URL, and the proxy streams that response body +
status back to the unauthenticated caller — an open-redirect-to-fetch / response
reflection primitive if the local server is ever compromised or buggy.

**Fix:** Set `follow_redirects=False` and either reject 3xx or return the
`Location` verbatim without following it. Also strip/forward only an allowlist of
response headers (already partially done at `:221-222`).

### M5 — Generic webhook fires unauthenticated when a trigger has no `webhook_secret`
**Files:**
- `app_litestar/routes/webhooks.py:266-296` (`generic_webhook`, mounted at `/`,
  auth-bypassed via `middleware.py:64-70`)
- `app/services/trigger_dispatcher.py:88-100` (secret check only `if webhook_secret`)

**Problem:** The generic `/` webhook receiver is unauthenticated by design and
relies on per-trigger HMAC. But `dispatch_webhook_event` only validates a
signature **when `trigger.webhook_secret` is set**. A trigger created without a
secret (the default — `webhook_secret` is optional in `create_trigger`) will fire
on any spoofed payload from any internet client that can reach the host. There is
no global gate forcing webhook triggers to carry a secret.

**Fix:** Require `webhook_secret` for any `trigger_source == "webhook"` at
creation/update time (`trigger_service.create_trigger`/`update_trigger`), or add a
deployment-level toggle that rejects unsigned webhook dispatch. At minimum, surface
a prominent "unsigned — accepts any payload" warning and audit-log unsigned fires.

---

## LOW

### L1 — `validate_repo_url` fails open and makes an unauthenticated outbound HTTP call per add-path
**File:** `app/services/github_service.py:38-86` (returns `True` on every failure
path: `:64`, `:81`, `:86`); invoked from `trigger_service.add_path:362`.

**Problem:** Broad `except (..., Exception)` (`:63`) and unconditional `return True`
mean a typo'd/hostile URL passes validation; the outbound `api.github.com` GET
(`:70-74`) has `follow_redirects=True` and runs on a request-handling path,
giving a minor DoS/SSRF-amplification lever (request to GitHub per add-path call).
Security impact is low (clone later surfaces real errors), but the fail-open +
broad except masks integration failures.

**Fix:** Narrow the except to `(subprocess.TimeoutExpired, FileNotFoundError)`;
on genuine ambiguity return a tri-state ("unknown") rather than `True`; set
`follow_redirects=False` on the api.github.com probe.

### L2 — Silent broad `except` swallows integration/scheduler errors
**Files:**
- `github_service.py:63`, `:82` (`pass` on broad except)
- `gitops_sync_service.py:330-331` (`pass` on scheduler `remove_job`)
- `notification_service.py:90-98` (catches all, logs, continues — acceptable but
  per-integration failures never surface to caller)
- `sidecar_account_sync_service.py:60-61`, `:80-81`, `:112-114`, `:158-161`
  (best-effort, returns 0/skips silently — by design, documented)

**Problem:** Several catch-all handlers degrade silently. Most are documented
best-effort paths (sidecar sync, notifications) and acceptable, but the
github_service ones (L1) and the bare scheduler `pass` hide real faults.

**Fix:** Scope excepts to expected exception types; log at `warning` with context
where currently silent.

### L3 — Teams/JIRA outbound webhook/server URLs have no SSRF allowlist
**Files:** `integrations/teams_adapter.py:58-63` (POST to `self.webhook_url`),
`integrations/jira_adapter.py:38-41` (`JIRA(server=self.server, ...)`).

**Problem:** Both POST/connect to operator-configured URLs with no private-IP
guard. Teams at least enforces `https://` in `validate_config` (`:84-85`); JIRA
does not. Operator-controlled, timeouts are set (10s), so impact is low, but a
low-priv actor who can configure an integration could point it at internal hosts.

**Fix:** Apply the shared `_is_safe_target` check (M3) to outbound integration
URLs, or document that integration config is admin-trusted and enforce that with
RBAC.

### L4 — `_repo_last_event` rate-limit dict grows unbounded
**File:** `app_litestar/routes/webhooks.py:38-40`, `:162-170`

**Problem:** `_repo_last_event` is an in-process dict keyed by attacker-influenced
`repo_full_name` that is never evicted. A flood of webhooks with distinct
`repository.full_name` values grows it without bound — a slow memory-exhaustion
vector (mitigated by the GitHub HMAC gate at `:112-125`, since only signed
payloads reach the rate-limit code).

**Fix:** Evict entries older than `_REPO_RATE_LIMIT_SECONDS` on each access, or
cap the dict size / use a TTL cache. Apply the same to `url_summarizer._cache`
(also unbounded, but operator-triggered, hence lower).

---

## Notes — verified NOT vulnerable

- `url_summarizer.py` — correct SSRF defense: scheme allowlist (`:53`), resolves
  ALL A/AAAA records and rejects on any non-global (`:172-202`), pins httpx to the
  validated IP with Host header + SNI to defeat DNS-rebinding/TOCTOU (`:231-273`),
  follows redirects manually re-validating every hop (`:342-401`), byte cap (256KB)
  + 6s timeout + 5-hop cap. Suppresses script/style. Solid.
- `provider_usage_client.py` — all provider API URLs are hardcoded constants
  (`:385`, `:445`, `:585`, `:861`); tokens go only in `Authorization` headers,
  never URLs or logs; 15s timeouts on all `_http_get`/`_http_post`. The embedded
  `_GEMINI_CLI_CLIENT_SECRET` (`:29`) is the public Gemini-CLI OAuth client secret
  (not a user credential) — correct.
- `webhook_validation_service.py` — constant-time `hmac.compare_digest` (`:83`),
  validates raw bytes before JSON parse, rejects unknown/missing prefixes,
  timestamp replay protection (`:85-`).
- `slack_adapter.verify_slack_signature` (`:92-135`) — correct: 5-min replay
  window, constant-time compare.
- GitHub git ops (`github_service.py`) — argv lists (no shell), passes
  `owner/repo` not raw URL to `gh clone` (`:104-105`), PR title/body as separate
  argv (`:223-241`) — no command injection.
- `mcp_sync_service.sync_project` — atomic temp-file write + `os.replace`,
  preserves non-managed entries, JSON-decode guarded. (`json.loads` on stored
  config is benign — no pickle/yaml-unsafe.)
- `trigger_dispatcher.dispatch_webhook_event` — DB-backed dedup with TTL
  (`:112-126`) and queue-depth limit (`QueueFullError`) — bounded fan-out for the
  generic webhook path (contrast H2).
- Admin trigger-event replay (`trigger_event_service.replay` /
  `routes/trigger_events.py`) — admin-guarded (`requires_role("admin")`), and the
  documented signature-bypass is correctly scoped to that admin endpoint only.
