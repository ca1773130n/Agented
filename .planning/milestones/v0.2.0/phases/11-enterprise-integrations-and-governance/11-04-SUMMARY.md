---
phase: 11-enterprise-integrations-governance
plan: 04
subsystem: integrations
tags: [adapters, notifications, slack, teams, jira, linear, webhooks]
dependency_graph:
  requires: [11-01, 11-02, 11-03]
  provides: [integration-adapters, notification-service, slash-commands]
  affects: [execution-service, audit-log]
tech_stack:
  added: [slack-sdk, jira]
  patterns: [adapter-pattern, background-threading, hmac-verification]
key_files:
  created:
    - backend/app/services/integrations/__init__.py
    - backend/app/services/integrations/slack_adapter.py
    - backend/app/services/integrations/teams_adapter.py
    - backend/app/services/integrations/jira_adapter.py
    - backend/app/services/integrations/linear_adapter.py
    - backend/app/services/notification_service.py
    - backend/app/services/integration_config_service.py
    - backend/app/routes/integrations.py
    - backend/app/db/integrations.py
    - backend/app/models/integration.py
    - backend/tests/test_integrations.py
    - backend/tests/test_slack_command.py
  modified:
    - backend/app/db/schema.py
    - backend/app/db/migrations.py
    - backend/app/db/ids.py
    - backend/app/db/__init__.py
    - backend/app/routes/__init__.py
    - backend/pyproject.toml
decisions:
  - Skip credential validation at integration creation time (credentials come from vault at runtime)
  - Use threading.Thread for notification dispatch to avoid blocking webhook responses
  - Separate APIBlueprint for /api/integrations/slack/command (public webhook) vs /admin/integrations (CRUD)
metrics:
  duration: 14min
  completed: 2026-03-05
---

# Phase 11 Plan 04: Integration Adapters & Notification Service Summary

Pluggable integration adapter framework with Slack, Teams, JIRA, and Linear adapters, unified notification dispatch, and Slack slash command endpoint for triggering bot executions from Slack.

## What Was Built

### Adapter Framework
- **IntegrationAdapter** base class with `send_notification()`, `create_ticket()`, and `validate_config()` abstract methods
- **ADAPTER_REGISTRY** with `register_adapter()` / `get_adapter()` for dynamic adapter lookup
- Self-registration pattern: each adapter module registers itself at import time

### Four Adapter Implementations
1. **SlackAdapter** -- Block Kit notifications via `slack_sdk.WebClient.chat_postMessage()`, HMAC-SHA256 signature verification for inbound slash commands
2. **TeamsAdapter** -- MessageCard JSON via `httpx.post()` to webhook URL with 10s timeout
3. **JiraAdapter** -- Issue creation via `jira.JIRA.create_issue()` with severity-to-priority mapping (critical->Highest, high->High, medium->Medium, low->Low), labels `["agented", "automated"]`
4. **LinearAdapter** -- GraphQL `issueCreate` mutation via `httpx.post()` to `https://api.linear.app/graphql`

### Notification Service
- `NotificationService.on_execution_complete()` dispatches to all enabled integrations for a trigger via background `threading.Thread`
- `create_tickets_from_findings()` creates tickets via JIRA/Linear adapters
- `dispatch_notification()` for single-integration manual sends
- Notification delivery completes within 30 seconds (timing-asserted in test)

### Slack Slash Command Endpoint
- `POST /api/integrations/slack/command` -- inbound Slack slash command webhook
- HMAC-SHA256 signature verification with 5-minute replay protection
- Parses `run <trigger-name> on <target>` syntax
- Dispatches execution via `ExecutionService.run_trigger()` in background thread
- Returns immediate ephemeral response within 3 seconds (Slack requirement)
- Posts delayed response to `response_url` on completion

### Integration Management Routes
- `POST /admin/integrations` -- create integration config
- `GET /admin/integrations` -- list with type/trigger_id filters
- `GET /admin/integrations/<id>` -- get detail
- `PUT /admin/integrations/<id>` -- update
- `DELETE /admin/integrations/<id>` -- delete
- `POST /admin/integrations/<id>/test` -- send test notification
- `GET /admin/triggers/<trigger_id>/integrations` -- list for trigger

### Database Layer
- `integrations` table with type, config (JSON), trigger_id FK, enabled flag
- Migration v60: `add_integrations_table`
- ID generation: `intg-` prefix, 6-char random suffix
- CRUD: create, get, list (with filters), update, delete, list_for_trigger

## Test Results

- **46 tests pass** across `test_integrations.py` (27 tests) and `test_slack_command.py` (19 tests, including 11 in endpoint tests)
- **1115 total backend tests pass** (no regressions)
- **Frontend build succeeds** (`just build`)

### Test Coverage
- Adapter registry: all 4 registered, correct types, IntegrationAdapter subclass check
- Slack: Block Kit format verified, no-token returns False, validate_config checks
- Teams: MessageCard payload format, HTTPS validation
- JIRA: severity-to-priority mapping (critical->Highest), labels, project key
- Linear: GraphQL mutation format, authorization header
- DB CRUD: create, list, update, delete, list_for_trigger (global + specific)
- Routes: all 6 CRUD endpoints + 404 handling
- Notification timing: <30s dispatch assertion
- Signature verification: valid passes, invalid rejected, expired rejected, bad format
- Command parsing: valid syntax, spaces in trigger, empty text, missing keywords
- Slash endpoint: 401 on bad sig, 401 on expired, ephemeral error on unknown trigger, dispatch on valid

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Skip credential validation at integration creation time**
- **Found during:** Task 3
- **Issue:** `validate_config()` was rejecting integrations without credentials in the config dict, but credentials should come from SecretVaultService at runtime
- **Fix:** Only validate integration type at creation; credential validation happens when adapter is instantiated at runtime
- **Files modified:** `backend/app/services/integration_config_service.py`

**2. [Rule 3 - Blocking] Merge dependency branches**
- **Found during:** Task 1
- **Issue:** Plan 04 depends on Plan 01 (RBAC), Plan 02 (SecretVaultService), and Plan 03 (bookmarks) which were on separate worktree branches
- **Fix:** Merged all three dependency branches with conflict resolution; renumbered migrations (v57=RBAC, v58=secrets, v59=bookmarks, v60=integrations)
- **Commits:** 5940959, d732673

## Decisions Made

1. **Skip credential validation at creation** -- Credentials come from the vault at runtime; only validate integration type at creation time
2. **Background threading for notifications** -- Uses `threading.Thread(daemon=True)` following existing `TeamExecutionService` pattern to avoid blocking webhook responses
3. **Separate blueprints** -- `/api/integrations/slack/command` (public webhook) uses separate APIBlueprint from `/admin/integrations` (CRUD) for distinct rate limiting (30/min vs 120/min)

## Self-Check: PASSED
