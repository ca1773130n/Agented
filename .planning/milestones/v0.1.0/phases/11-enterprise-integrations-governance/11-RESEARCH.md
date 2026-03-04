# Phase 11: Enterprise Integrations & Governance - Research

**Researched:** 2026-03-04
**Domain:** External integrations (Slack, Teams, JIRA, Linear), RBAC, audit trails, secrets management, GitOps, multi-repo orchestration, execution bookmarking
**Confidence:** MEDIUM-HIGH

## Summary

Phase 11 covers eight requirements spanning external collaboration integrations (Slack/Teams, JIRA/Linear), configuration-as-code with GitOps, role-based access control, persistent audit trails, encrypted secrets management, multi-repo campaign execution, and execution bookmarking. The codebase already has strong foundations: an `AuditLogService` with in-memory ring buffer and field-change diffing, `watchdog`-based file system watchers, `cryptography` library already in dependencies, YAML parsing via `pyyaml`, and a proven export/import pattern from `SuperAgentExportService` and `ExportService`.

The primary challenge is scope breadth -- eight distinct requirements touching different domains. The recommended approach is to implement a lightweight integration adapter pattern where each external service (Slack, Teams, JIRA, Linear) is encapsulated behind a unified `IntegrationService` interface. RBAC should use a decorator-based approach consistent with the existing Flask route patterns rather than introducing a heavyweight framework. The secrets vault should leverage the `cryptography.fernet` module (already a dependency) for AES-128-CBC symmetric encryption with `MultiFernet` for key rotation.

**Primary recommendation:** Build a pluggable integration adapter layer with a shared `NotificationService` for outbound notifications and a `SlashCommandService` for inbound triggers, implement RBAC as a Flask decorator checking roles from a `user_roles` DB table, persist audit events to SQLite instead of the current in-memory-only ring buffer, and use Fernet symmetric encryption for the secrets vault.

## Paper-Backed Recommendations

### Recommendation 1: Role-Based Access Control via Decorator Pattern

**Recommendation:** Implement RBAC using a Python decorator (`@require_role("editor")`) that wraps Flask route handlers, checking the user's role against a permission matrix before allowing access.

**Evidence:**
- Ferraiolo & Kuhn, "Role-Based Access Controls" (1992, NIST) -- Established the foundational RBAC model with Users, Roles, Permissions, and Sessions. The four-level RBAC model (Core, Hierarchical, Constrained, Symmetric) is the industry standard.
- Sandhu et al., "Role-Based Access Control Models" (IEEE Computer, 1996) -- Formalized RBAC0-RBAC3 models. For this application, RBAC0 (flat roles without hierarchy) is sufficient given only 4 roles.
- Flask community pattern -- Decorator-based RBAC is the standard Flask pattern, documented across official Flask extensions (Flask-RBAC, Flask-Principal) and community guides.

**Confidence:** HIGH -- RBAC is a well-established security pattern with decades of research and industry adoption.
**Expected improvement:** Clear separation of authorization concerns from business logic. Four roles (Viewer, Operator, Editor, Admin) map directly to RBAC0 model.
**Caveats:** Without a proper authentication system in place, RBAC enforcement depends on correctly identifying the current user. The current app has no user authentication -- a minimal user identity mechanism is needed or RBAC operates on API-key-based identity.

### Recommendation 2: Fernet Symmetric Encryption for Secrets Vault

**Recommendation:** Use `cryptography.fernet.Fernet` for encrypting secrets at rest in SQLite, with `MultiFernet` for key rotation support. Derive the encryption key from an environment variable using PBKDF2.

**Evidence:**
- Cryptography.io official documentation -- Fernet provides authenticated encryption using AES-128-CBC + HMAC-SHA256, preventing both data exposure and tampering. The library is already in `pyproject.toml` (`cryptography>=41.0.0`).
- NIST SP 800-132 (2010) -- Recommends PBKDF2 for key derivation from passwords/passphrases with minimum 1000 iterations (modern recommendation: 600,000+ for SHA-256).
- MultiFernet documentation -- Supports transparent key rotation by attempting decryption with each key in order, encrypting new values with the primary key.

**Confidence:** HIGH -- `cryptography` is already a project dependency (used for Chrome cookie decryption in `cliproxy_manager.py`). Fernet is the standard Python approach for application-level symmetric encryption.
**Expected improvement:** Secrets encrypted at rest with authenticated encryption; key rotation without downtime; audit trail on every access.
**Caveats:** The master encryption key must be stored securely (environment variable or OS keychain), not in the database. If the key is lost, all encrypted secrets are unrecoverable.

### Recommendation 3: Adapter Pattern for External Integrations

**Recommendation:** Implement external integrations (Slack, Teams, JIRA, Linear) using a pluggable adapter pattern with a shared `IntegrationAdapter` base class. Each adapter handles authentication, message formatting, and error handling for its specific service.

**Evidence:**
- Gamma et al., "Design Patterns" (1994) -- The Adapter pattern enables incompatible interfaces to work together. The Strategy pattern allows runtime selection of integration behavior.
- Slack Python SDK (`slack-sdk`) -- Official SDK provides `WebClient` for API calls and supports both token-based and OAuth authentication. Version 3.x is current and actively maintained.
- Atlassian Python API (`atlassian-python-api`) -- Community-maintained library with 1.7k+ GitHub stars for JIRA, Confluence, and Bitbucket integration.
- Linear API -- GraphQL-based API with webhook support and HMAC-SHA256 signature verification.
- Microsoft Teams -- Incoming Webhooks use simple HTTP POST with JSON Adaptive Card payloads; no SDK required.

**Confidence:** MEDIUM-HIGH -- Individual integrations are well-documented, but the unified adapter pattern is an architectural decision that needs validation through implementation.

### Recommendation 4: Event-Sourced Audit Trail with SQLite Persistence

**Recommendation:** Extend the existing `AuditLogService` to persist events to a new `audit_events` SQLite table with indexed columns for entity, actor, and date range queries, while keeping the in-memory ring buffer for real-time SSE streaming.

**Evidence:**
- Fowler, "Event Sourcing" pattern (2005) -- Storing state changes as a sequence of events enables complete audit reconstruction. The existing `log_field_changes()` method already captures before/after diffs.
- OWASP Logging Cheat Sheet -- Recommends structured logging with who (actor), what (action), when (timestamp), where (entity), and outcome for security audit trails.
- The current `AuditLogService` already implements the event format (`ts`, `action`, `entity_type`, `entity_id`, `outcome`, `details`) -- only persistence to SQLite is missing.

**Confidence:** HIGH -- The existing implementation provides 80% of the needed functionality. Adding SQLite persistence is a straightforward extension.

### Recommendation 5: Git-Based Configuration Sync for GitOps

**Recommendation:** Use the existing `watchdog` library (already in dependencies) combined with `subprocess` git operations and `pyyaml` for parsing to implement GitOps sync. The sync engine should poll a configured git remote, detect changes via `git diff`, and apply YAML configuration changes to the database.

**Evidence:**
- GitOps principles (Weaveworks, 2017) -- Git as single source of truth; pull-based reconciliation; declarative desired state.
- Existing codebase patterns -- `GrdSyncService` already syncs filesystem state to database. `PluginFileWatcher` uses `watchdog` for real-time file change detection. Both patterns can be extended for GitOps.
- `pyyaml>=6.0.0` is already in `pyproject.toml` -- used across 8+ service files for YAML parsing.

**Confidence:** MEDIUM -- The GitOps sync pattern is well-established in the Kubernetes ecosystem but requires careful adaptation for this application's SQLite-based configuration model. Conflict resolution needs design attention.

## Standard Stack

### Core (Already in Project)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `cryptography` | >=41.0.0 | Fernet encryption for secrets vault | Already a dependency; industry standard for Python encryption |
| `pyyaml` | >=6.0.0 | YAML parsing for config export/import and GitOps | Already a dependency; used in 8+ services |
| `watchdog` | >=6.0.0 | File system watching for GitOps sync | Already a dependency; used in plugin/team file watchers |
| `httpx` | >=0.28.1 | HTTP client for external API calls (Teams, Linear) | Already a dependency; async support for non-blocking integrations |
| `APScheduler` | >=3.10.0 | Background job scheduling for GitOps polling | Already a dependency; scheduler infrastructure exists |

### New Dependencies

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `slack-sdk` | >=3.27.0 | Slack WebClient for posting messages and handling slash commands | Slack integration (INT-01) |
| `jira` | >=3.8.0 | JIRA REST API client for issue creation | JIRA integration (INT-02) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `slack-sdk` | Raw `httpx` calls | `slack-sdk` handles token rotation, rate limiting, retry logic; raw HTTP loses these |
| `jira` library | `atlassian-python-api` | `jira` is more focused and lighter; `atlassian-python-api` covers more Atlassian products but larger footprint |
| `jira` library for Linear | `httpx` + GraphQL | Linear has no official Python SDK; use raw GraphQL queries via httpx |
| Flask-RBAC extension | Custom decorator | Custom decorator is simpler and more consistent with existing codebase patterns; Flask-RBAC adds unnecessary abstraction |
| SQLite for audit persistence | Dedicated log service (ELK) | SQLite keeps the single-binary deployment model; ELK adds infrastructure complexity |

**Installation:**
```bash
cd backend && uv add slack-sdk jira
```

## Architecture Patterns

### Recommended Project Structure

```
backend/app/
  services/
    integrations/
      __init__.py              # IntegrationAdapter base class, registry
      slack_adapter.py          # Slack WebClient adapter
      teams_adapter.py          # Teams webhook adapter
      jira_adapter.py           # JIRA issue creation adapter
      linear_adapter.py         # Linear GraphQL adapter
    notification_service.py     # Unified notification dispatch (uses adapters)
    integration_config_service.py # Integration CRUD and config management
    rbac_service.py             # Role checking, permission matrix
    secret_vault_service.py     # Fernet encrypt/decrypt with audit logging
    config_export_service.py    # Bot config YAML/JSON export/import
    gitops_sync_service.py      # Git repo sync engine
    campaign_service.py         # Multi-repo campaign orchestration
    bookmark_service.py         # Execution bookmarking and deep links
  db/
    integrations.py             # Integration config CRUD
    audit_events.py             # Persistent audit event CRUD
    secrets.py                  # Encrypted secrets CRUD
    bookmarks.py                # Bookmark CRUD
    rbac.py                     # User roles CRUD
  models/
    integration.py              # Integration Pydantic models
    rbac.py                     # RBAC Pydantic models
    secret.py                   # Secret vault Pydantic models
    bookmark.py                 # Bookmark Pydantic models
  routes/
    integrations.py             # /admin/integrations/* endpoints
    rbac.py                     # /admin/rbac/* endpoints
    secrets.py                  # /admin/secrets/* endpoints
    bookmarks.py                # /admin/bookmarks/* endpoints
    gitops.py                   # /admin/gitops/* endpoints
    campaigns.py                # /admin/campaigns/* endpoints
```

### Pattern 1: Integration Adapter Pattern

**What:** Each external integration (Slack, Teams, JIRA, Linear) implements a common interface with `send_notification()`, `create_ticket()`, and `validate_config()` methods.
**When to use:** Any time a new external service needs to be integrated.
**Example:**
```python
# Source: Design Patterns (Gamma et al.) + codebase conventions
from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple
from http import HTTPStatus

class IntegrationAdapter(ABC):
    """Base class for external service integrations."""

    @abstractmethod
    def send_notification(self, channel: str, message: str, metadata: dict = None) -> bool:
        """Send a notification to the external service."""
        ...

    @abstractmethod
    def validate_config(self, config: dict) -> Tuple[bool, Optional[str]]:
        """Validate integration configuration. Returns (valid, error_message)."""
        ...

class SlackAdapter(IntegrationAdapter):
    def __init__(self, token: str):
        from slack_sdk import WebClient
        self.client = WebClient(token=token)

    def send_notification(self, channel: str, message: str, metadata: dict = None) -> bool:
        try:
            self.client.chat_postMessage(channel=channel, text=message)
            return True
        except Exception:
            return False

    def validate_config(self, config: dict) -> Tuple[bool, Optional[str]]:
        if not config.get("token"):
            return False, "Slack bot token required"
        return True, None
```

### Pattern 2: RBAC Decorator Pattern

**What:** A `@require_role()` decorator that checks the current user's role before allowing route handler execution.
**When to use:** Every route that needs authorization beyond authentication.
**Example:**
```python
# Source: Flask community RBAC patterns + NIST RBAC model
import functools
from http import HTTPStatus
from flask import request

# Permission matrix: role -> set of allowed permissions
ROLE_PERMISSIONS = {
    "viewer":   {"read"},
    "operator": {"read", "execute"},
    "editor":   {"read", "execute", "edit"},
    "admin":    {"read", "execute", "edit", "manage"},
}

def require_role(*allowed_roles):
    """Decorator that checks user role before allowing access."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            user_role = _get_current_user_role(request)
            if user_role not in allowed_roles:
                return {"error": "Insufficient permissions"}, HTTPStatus.FORBIDDEN
            return func(*args, **kwargs)
        return wrapper
    return decorator

# Usage in route:
@triggers_bp.post("/<trigger_id>/execute")
@require_role("operator", "editor", "admin")
def execute_trigger(path: TriggerPath):
    ...
```

### Pattern 3: Secrets Vault with Audit Trail

**What:** Encrypted secret storage with every access logged to the audit trail.
**When to use:** Storing API keys, tokens, and credentials.
**Example:**
```python
# Source: cryptography.io Fernet docs + NIST SP 800-132
import os
from cryptography.fernet import Fernet, MultiFernet

class SecretVaultService:
    _fernet: MultiFernet = None

    @classmethod
    def _get_fernet(cls) -> MultiFernet:
        if cls._fernet is None:
            keys_str = os.environ.get("AGENTED_VAULT_KEYS", "")
            if not keys_str:
                raise RuntimeError("AGENTED_VAULT_KEYS environment variable not set")
            keys = [Fernet(k.strip()) for k in keys_str.split(",")]
            cls._fernet = MultiFernet(keys)
        return cls._fernet

    @classmethod
    def encrypt(cls, plaintext: str) -> str:
        f = cls._get_fernet()
        return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    @classmethod
    def decrypt(cls, ciphertext: str, purpose: str = "", accessor: str = "") -> str:
        AuditLogService.log(
            action="secret.access",
            entity_type="secret",
            entity_id=purpose,
            outcome="accessed",
            details={"accessor": accessor},
        )
        f = cls._get_fernet()
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
```

### Pattern 4: Post-Execution Hook for Notifications

**What:** A hook point in `ExecutionLogService.finish_execution()` that dispatches notifications to configured integrations after execution completes.
**When to use:** Sending Slack/Teams messages and creating JIRA/Linear tickets after bot runs finish.
**Example:**
```python
# In execution_log_service.py finish_execution():
# After broadcasting completion to SSE subscribers, dispatch to integrations
from .notification_service import NotificationService
NotificationService.on_execution_complete(
    execution_id=execution_id,
    trigger_id=trigger_id,
    status=status,
    duration_ms=duration_ms,
)
```

### Anti-Patterns to Avoid

- **Inline integration logic in routes:** Keep all external API calls in service layer adapters, never in route handlers. Route handlers remain thin.
- **Storing encryption keys in the database:** The vault encryption key MUST come from an environment variable, never from SQLite. Storing the key alongside the encrypted data defeats the purpose.
- **Synchronous external API calls in the request path:** Slack/JIRA API calls should happen in background threads (using the existing threaded execution pattern) to avoid blocking webhook responses.
- **Polling-only GitOps:** Use webhook notifications from the Git host where possible, with polling as a fallback. Pure polling introduces unnecessary latency.
- **Hardcoded role checks:** Use the permission matrix pattern, not `if role == "admin"` scattered throughout the code.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Slack API interaction | Custom HTTP client for Slack | `slack-sdk` WebClient | Handles token rotation, rate limiting, retry, pagination, type safety |
| JIRA issue creation | Raw REST calls to JIRA | `jira` library | Handles auth (Basic, OAuth, PAT), field validation, JQL queries |
| Symmetric encryption | Custom AES implementation | `cryptography.fernet.Fernet` | Authenticated encryption (AES+HMAC), key rotation via MultiFernet, timestamp validation |
| YAML serialization | Custom config format parser | `pyyaml` | Already a dependency; handles anchors, aliases, multi-doc streams |
| File watching | Custom inotify/kqueue wrapper | `watchdog` Observer | Cross-platform (macOS FSEvents, Linux inotify, Windows), already used in 3 services |
| Webhook signature verification | Custom HMAC computation | `hmac.compare_digest()` | Timing-safe comparison prevents timing attacks; already used in GitHub webhook handler |

**Key insight:** The codebase already has patterns and dependencies for most of these problems. The phase is about composition and extension of existing infrastructure, not building from scratch.

## Common Pitfalls

### Pitfall 1: Slack Token Scope Misconfiguration

**What goes wrong:** Slack bot token lacks required OAuth scopes, causing `chat_postMessage` to fail silently or with cryptic errors.
**Why it happens:** Slack requires explicit scopes per API method (`chat:write`, `commands`, `incoming-webhook`).
**How to avoid:** Validate scopes at integration configuration time using `auth.test` API method. Document required scopes in integration setup UI.
**Warning signs:** 403 errors from Slack API, `missing_scope` error codes.

### Pitfall 2: Secrets Leaked in Logs or API Responses

**What goes wrong:** Encrypted secrets get decrypted and appear in execution stdout/stderr logs or API response bodies.
**Why it happens:** Environment variables injected at execution time appear in process output; API serialization includes sensitive fields.
**How to avoid:** The existing `_REDACTED_FIELDS` frozenset in `AuditLogService` already filters `webhook_secret`, `api_key`, `password`, `token`. Extend this pattern to all API responses. Use `AGENTED_SECRET_*` naming convention for injected env vars and strip them from log output.
**Warning signs:** Plaintext credentials visible in execution log viewer.

### Pitfall 3: GitOps Sync Conflicts Causing Data Loss

**What goes wrong:** Simultaneous edits via UI and Git repository cause one set of changes to be silently overwritten.
**Why it happens:** Last-write-wins without conflict detection.
**How to avoid:** Use content hashing (like `content_hash()` in existing `plugin_format.py`) to detect conflicts. When both sides have changed, flag as conflict and require manual resolution rather than auto-merging.
**Warning signs:** Users report configurations reverting after Git sync cycles.

### Pitfall 4: RBAC Bypass via Direct API Calls

**What goes wrong:** Some routes lack the `@require_role()` decorator, allowing unauthorized access.
**Why it happens:** Developer forgets to add decorator when creating new routes.
**How to avoid:** Add a startup check that verifies all non-health, non-public routes have RBAC decorators. Use a deny-by-default approach where undecorated routes return 403.
**Warning signs:** Viewers able to trigger executions or edit bots.

### Pitfall 5: Multi-Repo Campaign Execution Timeout

**What goes wrong:** Running a bot across 10+ repos simultaneously exhausts system resources or hits rate limits.
**Why it happens:** Each repo clone + CLI execution spawns a subprocess. No concurrency limit.
**How to avoid:** Implement a semaphore-based concurrency limit (e.g., max 5 concurrent repos). Use a queue-based approach where repos are processed in batches.
**Warning signs:** System memory exhaustion, rate limit errors cascading across all repos.

### Pitfall 6: Audit Trail Storage Growth

**What goes wrong:** Audit events table grows unbounded, slowing queries and consuming disk.
**Why it happens:** Every configuration change and secret access creates a row.
**How to avoid:** Implement retention policy (configurable, default 90 days). Add periodic cleanup job to APScheduler. Index `created_at` column for efficient range queries and deletion.
**Warning signs:** Slow audit history page loads, growing database file size.

## Experiment Design

### Recommended Experimental Setup

This phase is primarily integration engineering, not ML/research. Experiments focus on correctness, performance, and security validation.

**Independent variables:** Integration type (Slack/Teams/JIRA/Linear), payload size, concurrent execution count (for campaigns), number of secrets in vault
**Dependent variables:** Notification delivery latency, API response time, encryption/decryption throughput, audit query performance
**Controlled variables:** Database state, network conditions (use mocked external APIs for testing)

**Baseline comparison:**
- Method: Current system without integrations (manual notification via log checking)
- Expected performance: Notification delivery time = infinity (manual); audit query = in-memory only (500 events max)
- Our target: Notification delivery <30 seconds; audit query <500ms for 10K events; encryption <10ms per secret

**Ablation plan:**
1. Integrations with vs. without background threading -- tests impact of async notification dispatch on webhook response latency
2. Audit trail with vs. without SQLite persistence -- tests query performance vs. in-memory ring buffer
3. GitOps with webhook-triggered vs. polling-only sync -- tests latency difference

**Statistical rigor:**
- Number of runs: 3 runs per integration test scenario
- Confidence intervals: Mean +/- standard deviation
- Significance testing: Not applicable (pass/fail correctness tests, not statistical comparisons)

### Recommended Metrics

| Metric | Why | How to Compute | Baseline |
|--------|-----|----------------|----------|
| Notification latency | INT-01 requires <30s | Timestamp diff: execution finish to Slack message timestamp | N/A (new feature) |
| JIRA ticket creation time | INT-02 requires <60s | Timestamp diff: execution finish to JIRA issue created_at | N/A (new feature) |
| RBAC enforcement accuracy | INT-04 security | % of unauthorized requests correctly blocked | 100% target |
| Audit query time (10K events) | INT-05 usability | SQLite `EXPLAIN QUERY PLAN` + timing | N/A (currently in-memory only) |
| Secret encrypt/decrypt time | INT-06 performance | `time.perf_counter()` around Fernet ops | <10ms per operation |
| Campaign completion time | INT-07 performance | Wall clock for 3-repo simultaneous execution | Single-repo time x 1.5 (target) |

## Verification Strategy

### Recommended Verification Tiers for This Phase

| Item | Recommended Tier | Rationale |
|------|-----------------|-----------|
| RBAC decorator blocks unauthorized roles | Level 1 (Sanity) | Unit test with mocked request context |
| Secret encryption round-trip (encrypt then decrypt) | Level 1 (Sanity) | Pure function test, no external deps |
| Audit event persisted to SQLite | Level 1 (Sanity) | DB insert + query, no external deps |
| Config YAML export produces valid YAML | Level 1 (Sanity) | Serialize + parse roundtrip |
| Config import recreates identical bot | Level 1 (Sanity) | Export, clear, import, compare |
| Bookmark CRUD operations | Level 1 (Sanity) | Standard DB CRUD test |
| Slack notification sends message | Level 2 (Proxy) | Mock Slack WebClient, verify API call shape |
| JIRA ticket creation from findings | Level 2 (Proxy) | Mock JIRA client, verify issue fields |
| Teams webhook notification | Level 2 (Proxy) | Mock httpx, verify POST payload |
| Multi-repo campaign orchestration | Level 2 (Proxy) | Mock execution service, verify parallel dispatch |
| GitOps sync detects config changes | Level 2 (Proxy) | Mock git operations, verify DB updates |
| Notification delivery <30s end-to-end | Level 3 (Deferred) | Requires live Slack workspace |
| JIRA ticket appears in project | Level 3 (Deferred) | Requires live JIRA instance |
| GitOps full cycle (push to git, auto-apply) | Level 3 (Deferred) | Requires git repository with webhook |
| RBAC with real auth flow | Level 3 (Deferred) | Requires authentication system integration |

**Level 1 checks to always include:**
- Fernet encrypt/decrypt roundtrip with key rotation
- RBAC permission matrix: each role tested against each permission
- Audit event serialization includes all required fields (who, what, when, before/after)
- YAML export/import produces byte-identical trigger configuration
- Bookmark deep-link URL format is valid and resolvable
- Secrets never appear in API response JSON

**Level 2 proxy metrics:**
- Slack adapter called with correct channel and formatted message (mocked)
- JIRA adapter called with correct project, issue type, severity mapping (mocked)
- Campaign service dispatches to N repos and collects N results
- GitOps sync correctly applies YAML changes to DB trigger records

**Level 3 deferred items:**
- End-to-end integration with live Slack workspace
- End-to-end integration with live JIRA/Linear instance
- GitOps with real GitHub/GitLab webhook
- Load testing audit trail queries with 100K+ events
- Multi-repo campaign with 10+ real repositories

## Production Considerations

### Known Failure Modes

- **External API downtime:** Slack, JIRA, or Linear APIs may be temporarily unavailable.
  - Prevention: Implement retry with exponential backoff (pattern already exists in `apiFetch` frontend client and `OrchestrationService` backend)
  - Detection: Health check endpoint that verifies integration connectivity; log warnings on consecutive failures

- **Encryption key loss:** If `AGENTED_VAULT_KEYS` environment variable is lost, all encrypted secrets become unrecoverable.
  - Prevention: Document key backup procedure. Support multiple keys via MultiFernet for rotation without downtime.
  - Detection: Startup check that verifies at least one existing secret can be decrypted. Alert if decryption fails.

- **Audit trail corruption:** SQLite WAL mode can have issues with concurrent writes from multiple threads.
  - Prevention: Use the existing `get_connection()` context manager with `busy_timeout=5000`. Audit writes are low-frequency enough that contention is unlikely.
  - Detection: Periodic integrity check via `PRAGMA integrity_check`.

### Scaling Concerns

- **Audit event volume:** Every config change and secret access creates a row. At high usage, this table grows fast.
  - At current scale: SQLite handles millions of rows with proper indexing. Add `created_at` and `entity_type` indexes.
  - At production scale: Implement retention policy with background cleanup job. Consider archiving old events to compressed files.

- **Multi-repo campaign concurrency:** Each repo execution spawns a subprocess.
  - At current scale: Semaphore limiting to 5 concurrent executions is sufficient.
  - At production scale: Queue-based execution with worker pool. Consider deferring to background job system.

- **GitOps polling frequency:** Polling a git remote every N seconds creates network overhead.
  - At current scale: 60-second polling interval is acceptable for a single-user platform.
  - At production scale: Webhook-triggered sync from GitHub/GitLab with polling as fallback only.

### Common Implementation Traps

- **Blocking the webhook response:** External API calls (Slack, JIRA) in the webhook handler path cause timeouts.
  - Correct approach: Use `threading.Thread` for notification dispatch (consistent with existing `_stream_pipe` pattern in `ExecutionService`).

- **Storing plaintext fallback:** Developers add a "fallback" that stores the unencrypted secret alongside the encrypted version "for debugging."
  - Correct approach: Never store plaintext. Debug by verifying encryption roundtrip in tests, not by exposing secrets.

- **RBAC decorator ordering:** Placing `@require_role()` before the flask-openapi3 route decorator breaks OpenAPI schema generation.
  - Correct approach: Apply `@require_role()` after the route decorator (closer to the function).

## Code Examples

### Slack Notification After Execution

```python
# Source: slack-sdk official docs (https://github.com/slackapi/python-slack-sdk)
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

class SlackAdapter(IntegrationAdapter):
    def __init__(self, token: str):
        self.client = WebClient(token=token)

    def send_notification(self, channel: str, message: str, metadata: dict = None) -> bool:
        try:
            blocks = self._format_execution_summary(message, metadata)
            self.client.chat_postMessage(
                channel=channel,
                text=message,  # Fallback for notifications
                blocks=blocks,
            )
            return True
        except SlackApiError as e:
            logger.warning("Slack notification failed: %s", e.response["error"])
            return False

    def _format_execution_summary(self, message: str, metadata: dict) -> list:
        status_emoji = ":white_check_mark:" if metadata.get("status") == "success" else ":x:"
        return [
            {"type": "section", "text": {"type": "mrkdwn", "text": f"{status_emoji} *{message}*"}},
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*Bot:* {metadata.get('trigger_name', 'Unknown')}"},
                {"type": "mrkdwn", "text": f"*Duration:* {metadata.get('duration_ms', 0)}ms"},
            ]},
        ]
```

### JIRA Issue Creation from Findings

```python
# Source: jira library docs (https://jira.readthedocs.io/examples.html)
from jira import JIRA

class JiraAdapter(IntegrationAdapter):
    def __init__(self, server: str, email: str, api_token: str):
        self.client = JIRA(server=server, basic_auth=(email, api_token))

    def create_ticket(self, project_key: str, finding: dict) -> str:
        severity_to_priority = {
            "critical": "Highest",
            "high": "High",
            "medium": "Medium",
            "low": "Low",
        }
        issue = self.client.create_issue(fields={
            "project": {"key": project_key},
            "summary": finding.get("title", "Bot finding"),
            "description": finding.get("description", ""),
            "issuetype": {"name": "Bug"},
            "priority": {"name": severity_to_priority.get(
                finding.get("severity", "medium"), "Medium"
            )},
            "labels": ["agented", "automated"],
        })
        return issue.key
```

### Teams Incoming Webhook Notification

```python
# Source: Microsoft Teams docs (https://learn.microsoft.com/en-us/microsoftteams/platform/webhooks-and-connectors/how-to/add-incoming-webhook)
import httpx

class TeamsAdapter(IntegrationAdapter):
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send_notification(self, channel: str, message: str, metadata: dict = None) -> bool:
        status = metadata.get("status", "unknown") if metadata else "unknown"
        color = "00FF00" if status == "success" else "FF0000"
        payload = {
            "@type": "MessageCard",
            "themeColor": color,
            "summary": message,
            "sections": [{
                "activityTitle": f"Agented Execution: {message}",
                "facts": [
                    {"name": "Status", "value": status},
                    {"name": "Duration", "value": f"{metadata.get('duration_ms', 0)}ms"},
                ],
            }],
        }
        try:
            resp = httpx.post(self.webhook_url, json=payload, timeout=10)
            return resp.status_code == 200
        except httpx.HTTPError:
            return False
```

### Config Export as YAML

```python
# Source: pyyaml docs + existing SuperAgentExportService pattern
import yaml
from app.database import get_trigger, list_paths_for_trigger

class ConfigExportService:
    @staticmethod
    def export_trigger(trigger_id: str) -> str:
        trigger = get_trigger(trigger_id)
        if not trigger:
            raise ValueError(f"Trigger {trigger_id} not found")
        paths = list_paths_for_trigger(trigger_id)
        config = {
            "version": "1.0",
            "kind": "trigger",
            "metadata": {
                "name": trigger["name"],
                "backend_type": trigger["backend_type"],
                "trigger_source": trigger["trigger_source"],
            },
            "spec": {
                "prompt_template": trigger["prompt_template"],
                "model": trigger.get("model"),
                "execution_mode": trigger.get("execution_mode", "direct"),
                "timeout_seconds": trigger.get("timeout_seconds"),
                "allowed_tools": trigger.get("allowed_tools"),
                "paths": [{"local": p["local_project_path"], "type": p["path_type"]}
                          for p in paths],
            },
        }
        if trigger["trigger_source"] == "scheduled":
            config["spec"]["schedule"] = {
                "type": trigger.get("schedule_type"),
                "time": trigger.get("schedule_time"),
                "day": trigger.get("schedule_day"),
                "timezone": trigger.get("schedule_timezone"),
            }
        return yaml.dump(config, default_flow_style=False, sort_keys=False)
```

### Audit Event Persistence

```python
# Source: Existing AuditLogService pattern + SQLite persistence
from app.db.connection import get_connection

def add_audit_event(
    action: str, entity_type: str, entity_id: str,
    outcome: str, actor: str = "system",
    details: dict = None,
) -> bool:
    """Persist an audit event to SQLite."""
    import json
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO audit_events
               (action, entity_type, entity_id, outcome, actor, details, created_at)
               VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (action, entity_type, entity_id, outcome, actor,
             json.dumps(details) if details else None),
        )
        conn.commit()
        return True
```

### RBAC Decorator

```python
# Source: Flask RBAC community patterns + NIST RBAC0 model
import functools
from http import HTTPStatus
from flask import request

def require_role(*roles):
    """Decorator: restrict route to users with one of the given roles."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            api_key = request.headers.get("X-API-Key", "")
            if not api_key:
                return {"error": "API key required"}, HTTPStatus.UNAUTHORIZED
            from app.db.rbac import get_role_for_api_key
            user_role = get_role_for_api_key(api_key)
            if user_role not in roles:
                AuditLogService.log(
                    action="rbac.denied",
                    entity_type="route",
                    entity_id=request.path,
                    outcome="forbidden",
                    details={"role": user_role, "required": list(roles)},
                )
                return {"error": "Insufficient permissions"}, HTTPStatus.FORBIDDEN
            return func(*args, **kwargs)
        return wrapper
    return decorator
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Slack `slackclient` library | `slack-sdk` v3.x | 2020 | New SDK with better async, Socket Mode, retry handlers |
| JIRA basic auth with password | JIRA PAT (Personal Access Token) or OAuth 2.0 | 2022 | Atlassian deprecated basic auth with passwords for Cloud |
| Teams Office 365 Connectors | Teams Workflows (Power Automate) for webhooks | 2024 | Microsoft deprecated O365 Connectors; Incoming Webhooks via Workflows now standard |
| Custom file polling for GitOps | `watchdog` + webhook-triggered sync | 2019 | watchdog provides cross-platform native event support |
| Application-level AES | Fernet (AES+HMAC) | 2014 | Fernet adds authenticated encryption, preventing tampering |

**Deprecated/outdated:**
- `slackclient` package: Replaced by `slack-sdk`. The old package is no longer maintained.
- JIRA Cloud basic auth with passwords: Atlassian requires API tokens or OAuth 2.0 for Cloud instances.
- Office 365 Connectors for Teams: Microsoft has deprecated these in favor of Power Automate Workflows for incoming webhooks.

## Open Questions

1. **Authentication mechanism for RBAC**
   - What we know: The current app has no user authentication system. RBAC requires knowing who the user is.
   - What's unclear: Should RBAC use API keys, session-based auth, or defer to an external auth provider?
   - Recommendation: Use API-key-based identity for Phase 11 (simplest). Each API key maps to a role. Full auth (login, sessions, OAuth) can be added in a future phase. This matches the existing `X-Webhook-Signature-256` header pattern.

2. **Linear SDK availability**
   - What we know: Linear uses a GraphQL API. There is no official Python SDK.
   - What's unclear: Whether `linear-py` (community package) is stable enough for production use.
   - Recommendation: Use raw `httpx` with GraphQL queries for Linear integration. The API is simple enough (create issue mutation) that a full SDK is unnecessary.

3. **GitOps conflict resolution strategy**
   - What we know: GitOps requires a strategy when both UI and Git changes exist.
   - What's unclear: Should Git always win (standard GitOps), or should conflicts be flagged?
   - Recommendation: Git wins by default (standard GitOps principle), but log a warning audit event when overwriting UI changes. Provide a "dry-run" mode that shows what would change without applying.

4. **Multi-repo campaign result aggregation**
   - What we know: Each repo execution produces independent stdout/stderr logs.
   - What's unclear: How to parse and aggregate findings across repos (output formats vary by bot).
   - Recommendation: Store each repo's execution independently with a shared `campaign_id` foreign key. Aggregation is done at the presentation layer, not the execution layer. Findings can be structured later via post-processing.

5. **Execution bookmark deep-link format**
   - What we know: Need to link to specific log lines within an execution.
   - What's unclear: How to create stable line references when logs are streaming.
   - Recommendation: Use log line sequence numbers (already tracked in `LogLine` dataclass in `ExecutionLogService`). Deep-link format: `/executions/{exec_id}#line-{seq}`. Frontend scrolls to the referenced line on load.

## Sources

### Primary (HIGH confidence)
- [Cryptography.io Fernet documentation](https://cryptography.io/en/latest/fernet/) -- Fernet API, MultiFernet key rotation, encryption semantics
- [Slack Python SDK GitHub](https://github.com/slackapi/python-slack-sdk) -- WebClient API, chat_postMessage, slash commands
- [JIRA Python library docs](https://jira.readthedocs.io/examples.html) -- Issue creation, field mapping, authentication patterns
- [Microsoft Teams Incoming Webhooks](https://learn.microsoft.com/en-us/microsoftteams/platform/webhooks-and-connectors/how-to/add-incoming-webhook) -- Teams webhook payload format, Adaptive Cards
- NIST SP 800-132 -- Key derivation function recommendations for password-based encryption
- Ferraiolo & Kuhn, "Role-Based Access Controls" (1992, NIST) -- Foundational RBAC model
- Sandhu et al., "Role-Based Access Control Models" (IEEE Computer, 1996) -- RBAC0-RBAC3 formalization

### Secondary (MEDIUM confidence)
- [Linear API Developers](https://linear.app/developers/webhooks) -- Webhook setup, GraphQL mutations, HMAC verification
- [Flask RBAC community patterns](https://www.geeksforgeeks.org/python/flask-role-based-access-control/) -- Decorator-based RBAC implementation
- [Atlassian Python API](https://github.com/atlassian-api/atlassian-python-api) -- Alternative JIRA client library
- [GitOps principles](https://www.gitops.tech/) -- Git as source of truth, pull-based reconciliation
- Existing codebase: `AuditLogService`, `SuperAgentExportService`, `PluginFileWatcher`, `TeamMonitorService` patterns

### Tertiary (LOW confidence)
- `linear-py` community package stability -- needs validation before adoption
- Teams Workflows vs. Incoming Webhooks migration timeline -- Microsoft documentation evolving

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All core libraries already in project dependencies; only `slack-sdk` and `jira` are new
- Architecture: HIGH - Adapter pattern, decorator RBAC, and service layer patterns consistent with existing codebase
- Paper recommendations: MEDIUM-HIGH - RBAC and encryption are well-established patterns; integration patterns are industry standard
- Pitfalls: MEDIUM - Based on common integration failure modes and codebase-specific patterns
- Experiment design: MEDIUM - Integration testing requires mocked external services; latency targets from requirements

**Research date:** 2026-03-04
**Valid until:** 2026-04-03 (30 days -- stable domain, library versions unlikely to change significantly)
