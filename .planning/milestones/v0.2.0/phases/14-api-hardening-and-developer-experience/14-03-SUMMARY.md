---
phase: 14-api-hardening-and-developer-experience
plan: 03
subsystem: trigger-management
tags: [dry-run, cost-estimation, cron, scheduling, api-hardening]
dependency_graph:
  requires: [trigger-service, budget-service, scheduler-service, execution-service]
  provides: [dry-run-dispatch, cost-estimation, cron-expression-support, cron-validation]
  affects: [triggers-api, scheduler]
tech_stack:
  added: []
  patterns: [CronTrigger.from_crontab, BudgetService.estimate_cost]
key_files:
  created:
    - backend/tests/test_dry_run.py
    - backend/tests/test_cron_support.py
  modified:
    - backend/app/routes/triggers.py
    - backend/app/services/trigger_service.py
    - backend/app/services/scheduler_service.py
    - backend/app/models/trigger.py
    - backend/app/db/schema.py
    - backend/app/db/migrations.py
decisions:
  - "Dry-run reuses existing preview_prompt + ExecutionService.build_command + BudgetService.estimate_cost"
  - "cron_expression takes precedence over legacy schedule_type/schedule_time/schedule_day"
  - "validate-cron returns next 5 fire times using CronTrigger.get_next_fire_time()"
  - "Timezone always explicitly passed to CronTrigger.from_crontab() (never silent UTC default)"
metrics:
  duration: "7m 39s"
  completed: "2026-03-06"
---

# Phase 14 Plan 03: Dry-Run Dispatch, Cost Estimation, and Cron Expression Support Summary

Dry-run dispatch endpoint renders prompt, builds CLI command, and returns cost estimate without subprocess; cron validation endpoint parses standard 5-field expressions via CronTrigger.from_crontab() with timezone-aware scheduling.

## Completed Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Dry-run dispatch and cost estimation endpoints | 3823d31 | triggers.py, trigger_service.py, test_dry_run.py |
| 2 | Standard 5-field cron expression support | 7f67866 | scheduler_service.py, triggers.py, trigger.py, schema.py, migrations.py, test_cron_support.py |

## Implementation Details

### Task 1: Dry-Run Dispatch and Cost Estimation

- Added `TriggerService.dry_run()` static method that chains `preview_prompt()` -> `ExecutionService.build_command()` -> `BudgetService.estimate_cost()` without spawning any subprocess
- Added `POST /admin/triggers/<trigger_id>/dry-run` endpoint returning rendered_prompt, cli_command, backend_type, model, estimated_tokens, trigger_id, and trigger_name
- Added `POST /admin/triggers/<trigger_id>/estimate-cost` endpoint returning trigger_id, model, and cost estimate with token counts
- 7 tests covering full preview, placeholder rendering, 404 handling, no-subprocess guarantee, and cost estimation

### Task 2: Standard 5-Field Cron Expression Support

- Added `cron_expression` TEXT column to triggers table (migration v75) for standard 5-field cron syntax
- Extended `_build_cron_trigger()` to check `cron_expression` first -- if present, uses `CronTrigger.from_crontab(expr, timezone=tz)`, otherwise falls back to legacy structured fields
- Added `POST /admin/triggers/validate-cron` endpoint that validates expression, returns next 5 fire times, and enforces timezone
- Added `cron_expression` field to Trigger, CreateTriggerRequest, and UpdateTriggerRequest Pydantic models
- 18 tests covering CronTrigger parsing, invalid expressions, precedence over legacy fields, timezone handling, and endpoint validation

## Decisions Made

1. **Dry-run composition**: Reuses existing `preview_prompt()` for rendering, `ExecutionService.build_command()` for CLI preview, and `BudgetService.estimate_cost()` for cost -- no new rendering logic needed
2. **Cron precedence**: `cron_expression` takes precedence over `schedule_type`/`schedule_time`/`schedule_day` when present, preserving full backward compatibility
3. **Timezone enforcement**: Always passes timezone parameter to `CronTrigger.from_crontab()` to prevent silent UTC default (per 14-RESEARCH.md Pitfall 5)
4. **Validation preview**: `validate-cron` endpoint returns next 5 fire times so users can verify their expression matches expectations before saving

## Deviations from Plan

None -- plan executed exactly as written.

## Verification

- `cd backend && uv run pytest tests/test_dry_run.py -v` -- 7/7 passed
- `cd backend && uv run pytest tests/test_cron_support.py -v` -- 18/18 passed
- `cd backend && uv run pytest` -- 1399 passed, 1 pre-existing failure (test_post_execution_hooks unrelated)

## Self-Check: PASSED

All files verified present, all commits verified in history.
