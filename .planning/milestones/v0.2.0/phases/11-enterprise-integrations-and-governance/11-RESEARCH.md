# Phase 11: Enterprise Integrations & Governance - Research

**Researched:** 2026-03-04
**Domain:** Enterprise integration (chat ops, issue tracking, RBAC, secrets, GitOps, multi-repo orchestration)
**Confidence:** MEDIUM-HIGH

## Summary

Phase 11 adds eight capabilities to Agented: Slack/Teams chat-ops (INT-01), JIRA/Linear auto-issue creation (INT-02), bot config import/export with GitOps sync (INT-03), role-based access control (INT-04), full audit trail (INT-05), encrypted secrets vault (INT-06), multi-repo campaigns (INT-07), and execution bookmarking (INT-08). The codebase already provides key infrastructure that these features build on: an `AuditLogService` with in-memory ring buffer (500 events), an API key `before_request` guard, `ExecutionLogService.finish_execution()` as a natural post-execution hook point, YAML parsing via `pyyaml`, `cryptography` library for encryption, `WorkflowTriggerService.on_execution_complete()` for chaining, and a robust settings key-value store.

The recommended approach uses the existing `cryptography` dependency (Fernet symmetric encryption) for the secrets vault, extends the `before_request` middleware pattern for RBAC, adds a notification dispatcher as a post-execution hook in `ExecutionLogService.finish_execution()`, and leverages the established YAML frontmatter export patterns already used by plugins, agents, and skills for bot configuration export/import.

**Primary recommendation:** Build all eight features as independent service modules (`notification_service.py`, `rbac_service.py`, `secret_vault_service.py`, `config_export_service.py`, `campaign_service.py`, `bookmark_service.py`) following the existing classmethod/static-method singleton pattern, each with its own DB module, Pydantic models, and route blueprint -- keeping the architecture consistent with the 90+ services already in the codebase.

## Paper-Backed Recommendations

Every recommendation below cites specific evidence.

### Recommendation 1: Event-Driven Notification Dispatch via Post-Execution Hooks

**Recommendation:** Use an observer/hook pattern at `ExecutionLogService.finish_execution()` to dispatch notifications to Slack, Teams, JIRA, and Linear after execution completes.

**Evidence:**
- Gamma et al. (1994) *Design Patterns* -- The Observer pattern decouples event sources from consumers, enabling extensible notification without modifying the execution pipeline. Chapter 5 documents this as the standard pattern for one-to-many dependencies.
- The codebase already implements this pattern: `WorkflowTriggerService.on_execution_complete()` (line 233 of `workflow_trigger_service.py`) fires registered callbacks after execution completion. The notification dispatcher follows the same model.
- Slack official docs (https://api.slack.com/messaging/webhooks) confirm incoming webhooks accept JSON POST with `text` field for channel posting; the `slack-sdk` `WebhookClient` wraps this cleanly.

**Confidence:** HIGH -- Pattern already proven in the codebase; Slack/JIRA APIs are stable and well-documented.
**Expected improvement:** Execution results reach team collaboration tools within 30 seconds of completion.
**Caveats:** Notification delivery is best-effort; if the external service is down, failures should be logged but not block the execution pipeline.

### Recommendation 2: Fernet Symmetric Encryption for Secrets Vault

**Recommendation:** Use `cryptography.fernet.Fernet` with `MultiFernet` for key rotation to encrypt secrets at rest in SQLite.

**Evidence:**
- The `cryptography` library (already a dependency, `>=41.0.0` in `pyproject.toml`) provides `Fernet` -- AES-128-CBC with HMAC-SHA256 authentication. Official docs (https://cryptography.io/en/latest/fernet/) document it as the recommended approach for symmetric encryption of small values.
- `MultiFernet` enables key rotation without re-encrypting all values at once, which is the NIST-recommended approach to cryptographic key management (NIST SP 800-57 Part 1, Rev. 5, 2020).
- The codebase already uses `cryptography` in `cliproxy_manager.py` for AES-CBC decryption of Chrome-stored OAuth tokens, establishing precedent.

**Confidence:** HIGH -- Library already in dependency tree; Fernet is the Python standard for symmetric encryption of configuration secrets.
**Expected improvement:** Credentials stored encrypted at rest, never exposed in API responses or logs.
**Caveats:** Master key must be stored securely (env var or file with restrictive permissions, following the existing `_get_secret_key()` pattern in `__init__.py`). Fernet tokens are ~1.5x plaintext size.

### Recommendation 3: Decorator-Based RBAC on Flask before_request

**Recommendation:** Extend the existing `_require_api_key()` `before_request` handler to support role-based tokens (Viewer, Operator, Editor, Admin), using a per-route permission decorator.

**Evidence:**
- The codebase already has a working `before_request` API key guard (`__init__.py` lines 125-152) that validates `X-API-Key` headers. Extending this to map keys to roles is architecturally minimal.
- Flask-RBAC (https://flask-rbac.readthedocs.io/) and community patterns (GeeksforGeeks Flask RBAC guide, Permit.io Flask RBAC guide) all recommend decorator-based role checks as the standard Flask approach.
- OWASP Application Security Verification Standard (ASVS) 4.0 section V4 (Access Control) requires that every API endpoint explicitly checks permissions, which decorator-based RBAC enforces at the route level.

**Confidence:** HIGH -- Extends existing infrastructure; well-established Flask pattern.
**Expected improvement:** Four distinct permission levels enforced on all admin/API endpoints.
**Caveats:** Since the system currently uses a single API key, the migration path must support backward compatibility (single key = Admin role).

### Recommendation 4: YAML/JSON Export with Git Repository Watching for GitOps

**Recommendation:** Use the existing `pyyaml` + YAML frontmatter patterns for bot config export/import, and `watchdog` (already a dependency) or periodic `git pull` (already implemented in `ProjectWorkspaceService`) for GitOps sync.

**Evidence:**
- The codebase has extensive YAML frontmatter export patterns: `plugin_export_service.py`, `project_install_service.py`, `harness_deploy_service.py`, `skill_discovery_service.py`, and `sync_persistence_service.py` all use `yaml.dump()` with frontmatter delimiters and `parse_yaml_frontmatter()` for import.
- GitOps best practices (CNCF GitOps Working Group, 2025; https://www.gitops.tech/) define the pattern as: declarative desired state in Git, automated reconciliation. The existing `ProjectWorkspaceService` already does `git fetch`/`git pull` on a 30-minute schedule via APScheduler.
- `watchdog` (`>=6.0.0` in `pyproject.toml`) is already used for filesystem monitoring in `plugin_file_watcher.py` and `team_monitor_service.py`.

**Confidence:** HIGH -- All required libraries already installed; established patterns exist in the codebase.
**Expected improvement:** Bot configs can be version-controlled and synced automatically from a Git repo.
**Caveats:** Conflict resolution when both UI edits and Git changes occur simultaneously must be handled (Git wins for GitOps-managed bots).

### Recommendation 5: Persistent Audit Trail in SQLite

**Recommendation:** Extend the existing `AuditLogService` from in-memory ring buffer to a persistent `audit_events` SQLite table, with who/what/when/before-after state tracking.

**Evidence:**
- The existing `AuditLogService` (`audit_log_service.py`) already emits structured JSON events with `action`, `entity_type`, `entity_id`, `outcome`, and field-level diffs. The `log_field_changes()` method already computes before/after state diffs.
- The current implementation stores events only in a `collections.deque(maxlen=500)` ring buffer -- events are lost on restart and limited to 500. Persisting to SQLite is the natural evolution.
- OWASP Logging Cheat Sheet (2024 revision) recommends: who, what, when, where, outcome, and severity for all audit events. The existing event structure covers all fields except "who" (actor), which is the key addition.

**Confidence:** HIGH -- Direct extension of existing infrastructure.
**Expected improvement:** Full queryable audit trail that survives restarts, filterable by entity, actor, and date range.
**Caveats:** High-volume operations (e.g., batch imports) should batch audit inserts to avoid SQLite write contention.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `slack-sdk` | `>=3.33.0` | Slack API (WebhookClient, slash commands) | Official Slack SDK for Python; actively maintained by Slack |
| `pymsteams` | `>=0.2.5` | MS Teams incoming webhook messages | Most popular Python Teams webhook library; simple API |
| `jira` | `>=3.10.0` | JIRA issue creation and management | Official Atlassian-community library; REST v3 compatible |
| `cryptography` | `>=41.0.0` | Fernet encryption for secrets vault | Already in `pyproject.toml`; Python standard for symmetric encryption |
| `pyyaml` | `>=6.0.0` | Bot config YAML export/import | Already in `pyproject.toml`; used extensively in codebase |
| `watchdog` | `>=6.0.0` | Filesystem monitoring for GitOps sync | Already in `pyproject.toml`; used in plugin_file_watcher.py |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `httpx` | `>=0.28.1` | HTTP client for Linear GraphQL API | Already in `pyproject.toml`; for Linear API calls (no SDK needed) |
| `APScheduler` | `>=3.10.0` | Periodic GitOps sync polling | Already in `pyproject.toml`; scheduled repo sync |

### Alternatives Considered

| Instead of | Could Use | Tradeoff | Decision Rationale |
|------------|-----------|----------|-------------------|
| `slack-sdk` | `slack-bolt` (full framework) | Bolt adds slash command server; heavier dependency for webhook-only use | Use `slack-sdk` for outbound webhooks, add Bolt only if slash commands need a dedicated listener |
| `pymsteams` | Direct `httpx` POST to Teams webhook URL | pymsteams handles card formatting; raw HTTP is simpler but less ergonomic | Use `pymsteams` for structured Adaptive Cards support |
| `jira` | `atlassian-python-api` | atlassian-python-api covers more Atlassian products; `jira` is lighter and purpose-built | Use `jira` for focused JIRA issue creation |
| SQLite audit table | Separate audit database / log file | SQLite keeps audit data queryable via existing DB patterns; separate DB adds operational complexity | SQLite is sufficient for single-instance deployment |
| Fernet | `nacl.secret.SecretBox` (libsodium) | NaCl uses XSalsa20-Poly1305 (256-bit); Fernet uses AES-128-CBC + HMAC-SHA256 | Fernet is already available via `cryptography` dependency; both are secure for config secrets |

**Installation:**
```bash
cd backend && uv add slack-sdk pymsteams jira
```

No frontend npm additions required -- all integrations are backend-only with UI configuration via existing settings patterns.

## Architecture Patterns

### Recommended Project Structure

New files for Phase 11 (following existing codebase conventions):

```
backend/app/
├── db/
│   ├── audit_events.py       # Persistent audit event CRUD
│   ├── secrets.py             # Encrypted secrets vault CRUD
│   ├── integrations.py        # Integration config CRUD (Slack, JIRA, etc.)
│   ├── rbac.py                # API key-to-role mapping CRUD
│   ├── campaigns.py           # Multi-repo campaign CRUD
│   └── bookmarks.py           # Execution bookmark CRUD
├── models/
│   ├── integration.py         # Pydantic models for integrations
│   ├── rbac.py                # Pydantic models for RBAC
│   ├── secret.py              # Pydantic models for secrets
│   ├── campaign.py            # Pydantic models for campaigns
│   └── bookmark.py            # Pydantic models for bookmarks
├── services/
│   ├── notification_service.py    # Dispatches to Slack/Teams/JIRA/Linear
│   ├── slack_service.py           # Slack-specific operations
│   ├── teams_service.py           # MS Teams-specific operations
│   ├── jira_service.py            # JIRA-specific operations
│   ├── linear_service.py          # Linear-specific operations
│   ├── rbac_service.py            # RBAC enforcement logic
│   ├── secret_vault_service.py    # Encrypted secrets management
│   ├── config_export_service.py   # Bot config YAML/JSON export/import
│   ├── gitops_sync_service.py     # GitOps repository watching and sync
│   ├── campaign_service.py        # Multi-repo campaign orchestration
│   └── bookmark_service.py        # Execution bookmarking
├── routes/
│   ├── integrations.py        # /admin/integrations/*
│   ├── rbac.py                # /admin/rbac/*
│   ├── secrets.py             # /admin/secrets/*
│   ├── campaigns.py           # /admin/campaigns/*
│   └── bookmarks.py           # /admin/bookmarks/*
frontend/src/
├── services/api/
│   ├── integrations.ts        # integrationApi
│   ├── rbac.ts                # rbacApi
│   ├── secrets.ts             # secretApi
│   ├── campaigns.ts           # campaignApi
│   └── bookmarks.ts           # bookmarkApi
├── views/
│   ├── IntegrationsPage.vue   # Integration configuration UI
│   ├── RbacPage.vue           # RBAC management UI
│   ├── SecretsPage.vue        # Secrets vault UI
│   └── CampaignsPage.vue     # Multi-repo campaign UI
└── components/
    ├── integrations/          # Integration-specific components
    ├── secrets/               # Secret management components
    └── campaigns/             # Campaign components
```

### Pattern 1: Notification Dispatcher (Observer/Hook)

**What:** A central `NotificationService` that registers as a post-execution hook and fans out to configured integration channels.
**When to use:** After any execution completes (trigger, workflow, team, campaign).
**Example:**
```python
# Source: Existing pattern from WorkflowTriggerService.on_execution_complete()
class NotificationService:
    """Dispatches execution result notifications to configured integration channels."""

    @classmethod
    def on_execution_complete(
        cls,
        trigger_id: str,
        execution_id: str,
        status: str,
        summary: str,
    ) -> None:
        """Called by ExecutionLogService.finish_execution() after DB flush."""
        configs = get_integration_configs(trigger_id)
        for config in configs:
            try:
                if config["type"] == "slack":
                    SlackService.post_execution_summary(config, execution_id, status, summary)
                elif config["type"] == "teams":
                    TeamsService.post_execution_summary(config, execution_id, status, summary)
                elif config["type"] == "jira":
                    JiraService.create_issue_from_execution(config, execution_id, status, summary)
                elif config["type"] == "linear":
                    LinearService.create_issue_from_execution(config, execution_id, status, summary)
            except Exception:
                logger.exception(f"Notification failed for {config['type']}")
```

### Pattern 2: RBAC Middleware Extension

**What:** Extend `_require_api_key()` to resolve API keys to roles, then check per-route permissions.
**When to use:** On every authenticated request.
**Example:**
```python
# Source: Existing pattern from __init__.py lines 125-152
# Role hierarchy: Admin > Editor > Operator > Viewer
ROLE_HIERARCHY = {"admin": 4, "editor": 3, "operator": 2, "viewer": 1}

def require_role(min_role: str):
    """Decorator for route-level RBAC enforcement."""
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            current_role = getattr(request, '_user_role', None)
            if not current_role:
                return {"error": "Unauthorized"}, 401
            if ROLE_HIERARCHY.get(current_role, 0) < ROLE_HIERARCHY[min_role]:
                return {"error": "Forbidden"}, 403
            return f(*args, **kwargs)
        return wrapper
    return decorator
```

### Pattern 3: Secrets Vault with Fernet

**What:** Encrypt secrets before storing in SQLite, decrypt at execution time, audit every access.
**When to use:** For any credential that bots need at execution time.
**Example:**
```python
# Source: cryptography official docs (https://cryptography.io/en/latest/fernet/)
from cryptography.fernet import Fernet, MultiFernet

class SecretVaultService:
    _fernet: MultiFernet = None

    @classmethod
    def _get_fernet(cls) -> MultiFernet:
        if cls._fernet is None:
            # Load master key from env or persisted file (same pattern as SECRET_KEY)
            master_key = os.environ.get("AGENTED_VAULT_KEY", "")
            if not master_key:
                master_key = cls._load_or_generate_key()
            keys = [Fernet(k) for k in master_key.split(",")]
            cls._fernet = MultiFernet(keys)
        return cls._fernet

    @classmethod
    def encrypt(cls, plaintext: str) -> str:
        return cls._get_fernet().encrypt(plaintext.encode()).decode()

    @classmethod
    def decrypt(cls, token: str) -> str:
        return cls._get_fernet().decrypt(token.encode()).decode()
```

### Anti-Patterns to Avoid

- **Storing secrets in the settings table:** The existing `settings` table is unencrypted key-value; secrets must go in a dedicated `secrets` table with encryption. Never reuse the `set_setting()` function for credentials.
- **Synchronous notification delivery in the request path:** Notifications to Slack/JIRA must happen asynchronously (in a background thread or via the existing `threading.Thread` pattern) to avoid blocking the execution flow.
- **Hardcoding integration credentials in service code:** All integration tokens/URLs must come from the database (encrypted) or environment variables, never from source code.
- **Checking roles with string equality instead of hierarchy:** Use `ROLE_HIERARCHY[current] >= ROLE_HIERARCHY[required]` instead of `current == required` to support hierarchical permissions (Admin can do everything Editor can do).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Slack message posting | Custom HTTP POST to Slack | `slack_sdk.webhook.WebhookClient` | Handles retries, rate limits, message formatting |
| Teams message cards | Custom JSON construction | `pymsteams.connectorcard` | Handles Adaptive Card formatting, sections, actions |
| JIRA issue creation | Direct REST calls to JIRA API | `jira.JIRA.create_issue()` | Handles auth, field validation, project key resolution |
| Symmetric encryption | Custom AES implementation | `cryptography.fernet.Fernet` | Handles IV generation, HMAC verification, padding |
| Key rotation | Manual key migration scripts | `cryptography.fernet.MultiFernet` | Handles multi-key decryption, transparent rotation |
| YAML serialization | Custom string formatting | `yaml.dump()` / `yaml.safe_load()` | Handles escaping, multiline, complex types |

**Key insight:** Every external integration has an official or well-maintained SDK. Hand-rolling HTTP calls introduces edge cases around authentication, error handling, and rate limiting that the SDKs handle.

## Common Pitfalls

### Pitfall 1: Notification Delivery Blocking Execution Pipeline

**What goes wrong:** Posting to Slack/JIRA synchronously in `finish_execution()` adds latency and can fail, causing execution status to appear stuck.
**Why it happens:** Developers add the notification call directly in the finish path without threading.
**How to avoid:** Dispatch notifications in a daemon thread (same pattern as `_stream_pipe` threads in `execution_service.py`). Use `threading.Thread(target=..., daemon=True).start()`.
**Warning signs:** Execution completion times increase; SSE `complete` events are delayed.

### Pitfall 2: Vault Master Key Loss

**What goes wrong:** If the `AGENTED_VAULT_KEY` is lost, all encrypted secrets become unrecoverable.
**Why it happens:** Key stored only in env var on a single machine with no backup.
**How to avoid:** Follow the existing `_get_secret_key()` pattern: check env var first, then fall back to a persisted `.vault_key` file with `0o600` permissions. Document key backup in deployment docs.
**Warning signs:** After server migration, all secrets return decryption errors.

### Pitfall 3: RBAC Bypass via Direct DB Access

**What goes wrong:** Services that import from `app.db` directly can bypass RBAC checks that only exist in route handlers.
**Why it happens:** RBAC is enforced at the HTTP layer; internal service calls have no auth context.
**How to avoid:** RBAC enforcement should be exclusively at the route/middleware layer. Services should not make authorization decisions. This matches the existing architecture where routes are thin wrappers that delegate to services.
**Warning signs:** A service function modifies data without any caller checking permissions.

### Pitfall 4: GitOps Sync Race Condition with UI Edits

**What goes wrong:** User edits a bot in the UI at the same time a GitOps sync pulls a different version from Git, causing data loss.
**Why it happens:** No conflict detection between UI writes and Git-synced writes.
**How to avoid:** Add a `managed_by` field to the `triggers` table (values: `"ui"` or `"gitops"`). GitOps-managed bots are read-only in the UI; UI-managed bots are not overwritten by GitOps sync.
**Warning signs:** Bot configuration reverts unexpectedly after Git push.

### Pitfall 5: Audit Table Growth Without Pruning

**What goes wrong:** The `audit_events` table grows unboundedly, eventually slowing queries and consuming disk.
**Why it happens:** Every API mutation, every execution, and every secret access generates an audit record.
**How to avoid:** Add an APScheduler job to prune audit records older than a configurable retention period (default 90 days). Add an index on `created_at` for efficient range queries.
**Warning signs:** Query latency on `/admin/audit-events` increases over time; SQLite file size grows unexpectedly.

### Pitfall 6: Leaking Secrets in Audit Logs

**What goes wrong:** When a secret is updated, the `log_field_changes()` method includes old/new values in the diff.
**Why it happens:** The existing `_REDACTED_FIELDS` set covers `webhook_secret`, `api_key`, `password`, `token`, but may miss new field names.
**How to avoid:** Ensure the secret vault service uses `AuditLogService.log()` directly (not `log_field_changes()`) with only the secret name/ID, never the value. Extend `_REDACTED_FIELDS` to include any new sensitive field names.
**Warning signs:** Decrypted secret values appear in audit event `details.changes`.

## Experiment Design

### Recommended Experimental Setup

**Independent variables:** Integration type (Slack, Teams, JIRA, Linear), notification payload size, concurrent execution count
**Dependent variables:** Notification delivery latency (time from `finish_execution()` to external API acknowledgment), throughput (notifications/second), error rate
**Controlled variables:** Network conditions, SQLite write concurrency, vault key configuration

**Baseline comparison:**
- Method: No notifications (current behavior)
- Expected performance: `finish_execution()` completes in <10ms (DB update + SSE broadcast)
- Our target: Adding notifications should not increase `finish_execution()` latency by more than 5ms (notification dispatched asynchronously)

**Ablation plan:**
1. Notifications enabled vs. disabled -- tests that notification dispatch does not degrade execution pipeline performance
2. Encrypted vs. plaintext secrets -- tests encryption/decryption overhead on execution startup
3. RBAC checks enabled vs. disabled -- tests authorization overhead per request

**Statistical rigor:**
- Number of runs: 5 per configuration
- Confidence intervals: 95% CI via Student's t-test
- Significance testing: Paired t-test for latency comparisons

### Recommended Metrics

| Metric | Why | How to Compute | Baseline |
|--------|-----|----------------|----------|
| Notification delivery latency | Core SLA: 30s for Slack/Teams | Timestamp diff: `finish_execution()` to external API HTTP 200 | N/A (new feature) |
| JIRA ticket creation time | Core SLA: 60s for issue trackers | Timestamp diff: execution end to JIRA issue created_at | N/A (new feature) |
| RBAC check overhead | Must not degrade API response time | Per-request `before_request` duration (add timing in middleware) | ~0.1ms (current API key check) |
| Secret decrypt latency | Must not delay execution startup | Time to call `SecretVaultService.decrypt()` | N/A (new feature) |
| Audit write throughput | Must not cause SQLite contention | Writes/second to `audit_events` table under concurrent executions | N/A (new feature) |
| Config export/import round-trip fidelity | 100% field preservation required | Export bot, import on clean instance, diff all fields | N/A (new feature) |

## Verification Strategy

### Recommended Verification Tiers for This Phase

| Item | Recommended Tier | Rationale |
|------|-----------------|-----------|
| RBAC decorator blocks unauthorized access | Level 1 (Sanity) | Can test immediately with Flask test client |
| Secret encryption/decryption round-trip | Level 1 (Sanity) | Pure function test, no external deps |
| Bot config YAML export/import fidelity | Level 1 (Sanity) | Deterministic serialization test |
| Audit event persistence and querying | Level 1 (Sanity) | DB CRUD test with isolated_db fixture |
| Execution bookmarks CRUD + deep links | Level 1 (Sanity) | Standard DB + API test |
| Slack webhook delivery (mocked) | Level 2 (Proxy) | Mock external API, verify payload structure |
| JIRA issue creation (mocked) | Level 2 (Proxy) | Mock JIRA client, verify issue fields |
| Teams message posting (mocked) | Level 2 (Proxy) | Mock pymsteams, verify card content |
| Linear issue creation (mocked) | Level 2 (Proxy) | Mock httpx POST, verify GraphQL mutation |
| Multi-repo campaign across 3 repos | Level 2 (Proxy) | Mock repo clones, verify parallel dispatch |
| GitOps sync detects and applies changes | Level 2 (Proxy) | Create temp git repo, modify, verify sync |
| Notification delivery within 30s SLA | Level 3 (Deferred) | Requires live Slack/Teams workspace |
| JIRA ticket appears within 60s SLA | Level 3 (Deferred) | Requires live JIRA instance |
| End-to-end RBAC with real API keys | Level 3 (Deferred) | Requires multi-user setup |

**Level 1 checks to always include:**
- Fernet encrypt/decrypt round-trip preserves plaintext exactly
- RBAC decorator returns 403 for insufficient role, 200 for sufficient role
- Audit events include `actor`, `action`, `entity_type`, `entity_id`, `outcome`, `timestamp`
- Bot config YAML export then import produces identical trigger configuration
- Bookmark creation returns valid deep-link URL format
- Secret values never appear in any API response body

**Level 2 proxy metrics:**
- Slack `WebhookClient.send()` called with correct channel and formatted summary (mock)
- `jira.JIRA.create_issue()` called with correct project key, issue type, severity field (mock)
- Multi-repo campaign dispatches `ExecutionService.run_trigger()` for each repo in parallel threads
- GitOps sync detects file changes in watched repository and calls `update_trigger()` with new config

**Level 3 deferred items:**
- Live Slack workspace receives actual message within 30 seconds
- Live JIRA project shows created ticket within 60 seconds
- GitOps sync from real GitHub repository applies config changes on push
- Multi-repo campaign across 3 real GitHub repositories produces consolidated findings view

## Production Considerations

### Known Failure Modes

- **External API downtime:** Slack, Teams, JIRA, or Linear may be temporarily unavailable.
  - Prevention: Wrap all external API calls in try/except; log errors to audit trail; never block execution pipeline.
  - Detection: Monitor notification failure count via audit events with `outcome: "notification_failed"`.

- **Vault master key rotation breaks existing secrets:** Rotating the master key without re-encrypting existing secrets makes them unreadable.
  - Prevention: Use `MultiFernet` with the new key first in the list; old keys remain for decryption. Provide a migration command that re-encrypts all secrets with the new primary key.
  - Detection: `SecretVaultService.decrypt()` raises `InvalidToken` exception.

- **SQLite write contention from audit logging:** Under concurrent executions, frequent audit writes can hit the 5-second busy timeout.
  - Prevention: Batch audit writes (collect events in a buffer, flush periodically). The existing `_log_buffers` pattern in `ExecutionLogService` shows the approach.
  - Detection: `sqlite3.OperationalError: database is locked` in logs.

### Scaling Concerns

- **Audit table size:** At current scale (10-20 executions/day), 90-day retention produces ~50K records, well within SQLite capacity. At production scale (1000+ executions/day), consider archiving old records to a separate file or migrating to PostgreSQL.
  - At current scale: SQLite with indexed queries is sufficient.
  - At production scale: Add `VACUUM` schedule, consider partitioned tables or external audit sink.

- **Notification fan-out:** At current scale, sequential notification dispatch is acceptable. At high concurrency, use a thread pool (matching the existing `threading.Thread` pattern).
  - At current scale: One daemon thread per notification.
  - At production scale: `concurrent.futures.ThreadPoolExecutor(max_workers=10)`.

- **Multi-repo campaigns:** Parallel execution across repos creates N concurrent subprocess executions.
  - At current scale: 3-5 repos is manageable.
  - At production scale: Add a campaign execution queue with configurable concurrency limit.

### Common Implementation Traps

- **Trap:** Adding `slack-bolt` as a full app server alongside Flask for slash commands.
  - Correct approach: Register a Flask route (`/api/integrations/slack/commands`) that handles Slack's POST payload directly using `slack-sdk` verification utilities. Do not run a separate Bolt server.

- **Trap:** Storing RBAC roles in the session (Flask session is cookie-based, not suitable for API key auth).
  - Correct approach: Store API key -> role mappings in SQLite. Look up role in `before_request`. Attach to `request._user_role = role` (or `g.user_role`).

- **Trap:** Exporting bot config including computed/runtime fields (like `next_run_at`, `last_run_at`).
  - Correct approach: Define an explicit allowlist of exportable fields. Exclude timestamps, execution history, and runtime state.

## Code Examples

Verified patterns from official sources and codebase conventions:

### Slack Incoming Webhook Post
```python
# Source: slack-sdk official docs (https://slack.dev/python-slack-sdk/webhook/)
from slack_sdk.webhook import WebhookClient

def post_to_slack(webhook_url: str, text: str, blocks: list = None) -> bool:
    """Post a message to a Slack channel via incoming webhook."""
    client = WebhookClient(webhook_url)
    response = client.send(text=text, blocks=blocks)
    return response.status_code == 200
```

### JIRA Issue Creation
```python
# Source: jira library official docs (https://jira.readthedocs.io/)
from jira import JIRA

def create_jira_issue(server: str, token: str, project_key: str,
                      summary: str, description: str, issue_type: str = "Bug",
                      priority: str = "Medium") -> str:
    """Create a JIRA issue and return the issue key."""
    jira = JIRA(server=server, token_auth=token)
    issue = jira.create_issue(fields={
        "project": {"key": project_key},
        "summary": summary,
        "description": description,
        "issuetype": {"name": issue_type},
        "priority": {"name": priority},
    })
    return issue.key
```

### Linear Issue Creation via GraphQL
```python
# Source: Linear API docs (https://linear.app/developers/graphql)
import httpx

def create_linear_issue(api_key: str, team_id: str,
                        title: str, description: str,
                        priority: int = 2) -> str:
    """Create a Linear issue via GraphQL API and return the issue ID."""
    mutation = """
    mutation CreateIssue($input: IssueCreateInput!) {
        issueCreate(input: $input) {
            success
            issue { id identifier url }
        }
    }
    """
    response = httpx.post(
        "https://api.linear.app/graphql",
        headers={"Authorization": api_key, "Content-Type": "application/json"},
        json={
            "query": mutation,
            "variables": {
                "input": {
                    "teamId": team_id,
                    "title": title,
                    "description": description,
                    "priority": priority,
                }
            },
        },
        timeout=30,
    )
    data = response.json()
    return data["data"]["issueCreate"]["issue"]["id"]
```

### Bot Config YAML Export
```python
# Source: Existing pattern from plugin_export_service.py, project_install_service.py
import yaml

# Exportable fields allowlist (excludes runtime/computed fields)
_EXPORTABLE_TRIGGER_FIELDS = [
    "name", "prompt_template", "backend_type", "trigger_source",
    "detection_keyword", "match_field_path", "match_field_value",
    "text_field_path", "enabled", "auto_resolve", "schedule_type",
    "schedule_time", "schedule_day", "schedule_timezone", "skill_command",
    "model", "execution_mode", "timeout_seconds", "allowed_tools",
    "sigterm_grace_seconds",
]

def export_trigger_as_yaml(trigger: dict) -> str:
    """Export a trigger configuration as YAML."""
    config = {k: trigger[k] for k in _EXPORTABLE_TRIGGER_FIELDS if k in trigger}
    # Include project paths
    paths = get_paths_for_trigger_detailed(trigger["id"])
    if paths:
        config["project_paths"] = [
            {"path": p["local_project_path"], "type": p["path_type"],
             "github_url": p.get("github_repo_url")}
            for p in paths
        ]
    return yaml.dump(config, default_flow_style=False, sort_keys=False)
```

### Execution Bookmark Schema
```python
# Source: Follows existing schema.py CREATE TABLE pattern
"""
CREATE TABLE IF NOT EXISTS execution_bookmarks (
    id TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL,
    trigger_id TEXT NOT NULL,
    user_label TEXT,
    notes TEXT,
    tags TEXT,
    pinned_log_line INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (execution_id) REFERENCES execution_logs(execution_id) ON DELETE CASCADE,
    FOREIGN KEY (trigger_id) REFERENCES triggers(id) ON DELETE CASCADE
)
"""
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Slack Legacy Tokens | Slack Bot Tokens + OAuth 2.0 | 2023 | Legacy tokens deprecated; use Bot tokens with scopes |
| JIRA REST API v2 | JIRA REST API v3 | 2024-2025 | v2 endpoints being deprecated; `jira>=3.10` defaults to v3 |
| Teams O365 Connectors | Teams Incoming Webhooks (Workflows) | 2024 | O365 Connectors deprecated; use Power Automate Workflows or webhook URLs |
| Manual RBAC in views | Middleware/decorator RBAC | Standard | Decorator-based RBAC is the established Flask pattern |
| `.env` file secrets | Encrypted vault with key rotation | Standard | Plaintext secrets in files violate OWASP ASVS v4 |

**Deprecated/outdated:**
- Slack Legacy Tokens: Deprecated since 2020; use Bot tokens with `chat:write` scope.
- Office 365 Connectors for Teams: Microsoft deprecated O365 Connectors in late 2024; incoming webhooks via Workflows app are the replacement.
- JIRA API v2 search endpoint `/rest/api/2/search`: Migrated to `/rest/api/3/search/jql` in 2025; the `jira` library >=3.10 handles this automatically.

## Open Questions

1. **Slash command routing: Flask route vs. Bolt server?**
   - What we know: Slack slash commands POST to a configurable URL. Flask can handle this as a regular POST route.
   - What's unclear: Whether Socket Mode (for apps behind firewalls without public URLs) is needed. Socket Mode requires `slack-bolt`.
   - Recommendation: Start with a Flask route for slash commands (simpler, no extra server). Add Socket Mode via Bolt only if users need it behind firewalls.

2. **Linear vs. JIRA: Which gets priority?**
   - What we know: Both are issue trackers with well-documented APIs. JIRA has a dedicated Python library; Linear uses GraphQL via httpx.
   - What's unclear: Which is more commonly used by the target user base.
   - Recommendation: Implement both behind a common `IssueTrackerService` interface. JIRA first (has SDK), Linear second (raw GraphQL).

3. **GitOps: Poll-based vs. webhook-based sync?**
   - What we know: The codebase already has `ProjectWorkspaceService` doing periodic `git pull` (30-minute interval). Webhook-based sync is more responsive but requires a public URL.
   - What's unclear: Whether users will have publicly accessible Agented instances for GitHub webhooks.
   - Recommendation: Start with poll-based sync (configurable interval, default 5 minutes for GitOps repos). The existing GitHub webhook infrastructure (`/api/webhooks/github/`) can be extended to trigger GitOps sync on push events.

4. **Multi-repo campaign: Parallel vs. sequential execution?**
   - What we know: The existing `ExecutionService.run_trigger()` runs executions in background threads. Multiple concurrent executions are already supported.
   - What's unclear: Resource limits when running 10+ repos simultaneously.
   - Recommendation: Parallel execution with configurable concurrency limit (default 3). Use `concurrent.futures.ThreadPoolExecutor` to cap concurrent subprocess count.

## Sources

### Primary (HIGH confidence)
- `cryptography` library official docs (https://cryptography.io/en/latest/fernet/) -- Fernet API, MultiFernet key rotation
- Slack SDK Python official docs (https://slack.dev/python-slack-sdk/webhook/) -- WebhookClient API
- Slack Bolt Python official docs (https://tools.slack.dev/bolt-python/concepts/commands) -- Slash command handling
- JIRA Python library official docs (https://jira.readthedocs.io/) -- Issue creation API
- Linear GraphQL API docs (https://linear.app/developers/graphql) -- Mutation schema for issue creation
- NIST SP 800-57 Part 1 Rev. 5 (2020) -- Cryptographic key management recommendations
- OWASP ASVS v4.0 Section V4 -- Access control verification requirements
- OWASP Logging Cheat Sheet (2024) -- Audit trail field requirements
- Gamma et al. (1994) *Design Patterns: Elements of Reusable Object-Oriented Software* -- Observer pattern (Chapter 5)

### Secondary (MEDIUM confidence)
- pymsteams GitHub repository (https://github.com/rveachkc/pymsteams) -- Teams webhook API
- atlassian-python-api GitHub repository (https://github.com/atlassian-api/atlassian-python-api) -- Alternative JIRA SDK
- CNCF GitOps Working Group (https://www.gitops.tech/) -- GitOps principles and patterns
- Flask-RBAC docs (https://flask-rbac.readthedocs.io/) -- Flask RBAC patterns

### Tertiary (LOW confidence)
- GeeksforGeeks Flask RBAC guide -- General Flask RBAC tutorial
- Permit.io Flask RBAC blog -- Decorator-based RBAC patterns
- PyPI `linear-api` package -- Python Linear wrapper (limited adoption, verify API compatibility)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- All libraries are established, most already in dependency tree
- Architecture: HIGH -- Follows existing codebase patterns exactly (services, db modules, routes, models)
- Paper recommendations: MEDIUM-HIGH -- Observer pattern and encryption are well-established; integration-specific recommendations based on official SDK docs
- Pitfalls: MEDIUM-HIGH -- Based on codebase analysis and known SQLite/threading constraints
- Experiment design: MEDIUM -- Baselines are limited (new features with no prior data)

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (30 days -- stable domain, APIs change slowly)
