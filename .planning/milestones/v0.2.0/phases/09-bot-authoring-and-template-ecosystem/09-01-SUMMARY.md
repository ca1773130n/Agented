---
phase: 09-bot-authoring-template-ecosystem
plan: 01
title: "Bot Template Marketplace & NL Bot Creator Backend"
subsystem: backend
tags: [bot-templates, marketplace, nl-generation, sse, crud]
dependency_graph:
  requires: [triggers-crud, base-generation-service]
  provides: [bot-template-api, trigger-generation-service]
  affects: [routes, schema, migrations, seeds, app-init]
tech_stack:
  added: [bot_templates-table, tpl-id-prefix]
  patterns: [BaseGenerationService-subclass, curated-seed-data, deploy-via-add_trigger]
key_files:
  created:
    - backend/app/db/bot_templates.py
    - backend/app/models/bot_template.py
    - backend/app/routes/bot_templates.py
    - backend/app/services/trigger_generation_service.py
  modified:
    - backend/app/db/schema.py
    - backend/app/db/migrations.py
    - backend/app/db/seeds.py
    - backend/app/db/__init__.py
    - backend/app/db/ids.py
    - backend/app/__init__.py
    - backend/app/routes/__init__.py
    - backend/app/routes/triggers.py
decisions:
  - "Deploy uses add_trigger() directly (not TriggerService) to avoid circular imports"
  - "Unique name handling via counter suffix: 'PR Reviewer (2)', 'PR Reviewer (3)'"
  - "5 curated templates seeded on startup with slug-based idempotency"
  - "TriggerGenerationService follows exact BaseGenerationService subclass pattern"
metrics:
  duration: "16min"
  completed: "2026-03-05"
---

# Phase 09 Plan 01: Bot Template Marketplace & NL Bot Creator Backend Summary

Bot template marketplace with 5 curated templates (PR reviewer, dependency updater, security scanner, changelog generator, test writer) plus NL trigger generation via Claude CLI SSE streaming.

## What Was Built

### Task 1: Bot Template Marketplace Backend

Created a complete bot template system with database table, seed data, CRUD operations, and deploy-to-trigger functionality.

**Database layer:**
- `bot_templates` table with id, slug, name, description, category, icon, config_json, sort_order, source, is_published columns
- Migration v69 for existing databases
- Fresh schema includes the table for new installations
- `tpl-` prefixed ID generation following existing per-entity pattern

**Seed data (5 curated templates):**
1. **PR Reviewer** (github trigger) -- reviews PRs for bugs, style, security, performance, test gaps
2. **Dependency Updater** (scheduled trigger, weekly) -- checks dependencies for updates and vulnerabilities
3. **Security Scanner** (webhook trigger) -- comprehensive security audit with severity ratings
4. **Changelog Generator** (webhook trigger) -- generates Keep a Changelog formatted changelogs
5. **Test Writer** (webhook trigger) -- generates unit tests for untested code paths

**API endpoints:**
- `GET /admin/bot-templates` -- list all published templates sorted by sort_order
- `GET /admin/bot-templates/<id>` -- get single template
- `POST /admin/bot-templates/<id>/deploy` -- deploy template as a real trigger

**Deploy mechanism:** Loads template config_json, checks for name conflicts via `get_trigger_by_name()`, appends numeric suffix if needed (e.g. "PR Reviewer (2)"), calls `add_trigger()` directly.

### Task 2: Natural Language Bot Creator

Created TriggerGenerationService extending BaseGenerationService, plus SSE streaming endpoint.

**TriggerGenerationService methods:**
- `_gather_context()` -- returns existing triggers, valid backends/sources, and placeholder variables by source type
- `_build_prompt()` -- constructs detailed generation prompt with JSON schema, placeholder documentation, and generation guidelines
- `_validate()` -- validates required fields, backend/source validity, schedule fields; adds warnings for issues but does not reject
- `_extract_progress()` -- extracts name, trigger_source, backend_type, and prompt_template preview from growing JSON

**SSE endpoint:**
- `POST /admin/triggers/generate/stream` -- accepts JSON with `description` field (min 10 chars)
- Returns SSE event stream via `BaseGenerationService.generate_streaming()`
- Follows exact pattern from commands.py generate/stream endpoint

## Deviations from Plan

None -- plan executed exactly as written.

## Decisions Made

1. **Deploy uses add_trigger() directly** -- avoids TriggerService circular imports per plan guidance
2. **Unique name via counter suffix** -- matches plan spec: "PR Reviewer (2)", increments until unique
3. **Slug-based idempotent seeding** -- checks by slug before insert, updates existing on re-seed
4. **BaseGenerationService subclass pattern** -- exactly mirrors PluginGenerationService/CommandGenerationService

## Task Commits

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Bot template marketplace backend | 4d2e2c2 | bot_templates.py, schema.py, migrations.py, seeds.py, bot_template.py (model), bot_templates.py (route) |
| 2 | NL bot creator TriggerGenerationService + SSE | 94bcb8b | trigger_generation_service.py, triggers.py (route) |

## Verification

- All 1188 tests pass (1 pre-existing failure in test_post_execution_hooks.py excluded)
- 5 templates defined and importable
- CRUD functions import correctly
- TriggerGenerationService._gather_context() returns expected keys (existing_triggers, backends, trigger_sources, placeholders)

## Self-Check: PASSED
