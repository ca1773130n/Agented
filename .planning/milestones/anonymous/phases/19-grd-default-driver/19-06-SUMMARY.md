---
phase: 19-grd-default-driver
plan: 06
subsystem: frontend
tags: [driver, i18n, super-agents, project-settings, transcript, grd]
requires:
  - "projects.default_driver"
  - "project_sa_instances.driver"
provides:
  - "frontend/src/components/super-agents/SuperAgentDriverSelector.vue:SuperAgentDriverSelector"
  - "Project.default_driver / SuperAgent.driver / ExecutionDriver types"
  - "ProjectTeamLeaderChat GRD-session link"
affects:
  - "frontend/src/views/ProjectSettingsPage.vue"
  - "frontend/src/views/SuperAgentsPage.vue"
  - "frontend/src/components/projects/ProjectTeamLeaderChat.vue"
tech-stack:
  patterns:
    - "reusable v-model <select> component"
    - "config_json merge-on-write (preserve other keys)"
    - "defensive multi-field SSE binding (grd_session_id|psm_session_id|session_id)"
    - "4-locale key-identical i18n namespace"
key-files:
  created:
    - "frontend/src/components/super-agents/SuperAgentDriverSelector.vue"
    - "frontend/src/components/projects/__tests__/DriverSelector.test.ts"
  modified:
    - "frontend/src/views/ProjectSettingsPage.vue"
    - "frontend/src/views/SuperAgentsPage.vue"
    - "frontend/src/components/projects/ProjectTeamLeaderChat.vue"
    - "frontend/src/services/api/projects.ts"
    - "frontend/src/services/api/types/projects.ts"
    - "frontend/src/services/api/types/agents.ts"
    - "frontend/src/services/api/types/super-agents.ts"
    - "frontend/src/services/api/index.ts"
    - "frontend/src/locales/en.json"
    - "frontend/src/locales/ko.json"
    - "frontend/src/locales/ja.json"
    - "frontend/src/locales/zh.json"
decisions:
  - "ExecutionDriver enum defined once in types/projects.ts, imported by super-agents/agents types and the top-level barrel"
  - "SA driver persisted into config_json.driver via merge-on-write so other config keys survive"
  - "GRD-session link binds defensively to grd_session_id|psm_session_id|session_id on the finish delta (backend not yet emitting it — forward-compatible per 19-RESEARCH risk 2)"
  - "Session link targets the existing project-management route with ?session=<psess-id> (no new route added)"
  - "Selector mounted per-SA-card on SuperAgentsPage (router-link card) with @click.stop.prevent so the inline change does not trigger navigation"
metrics:
  duration_min: 19
  tasks: 3
  files: 13
  completed: 2026-06-13
---

# Phase 19 Plan 06: GRD Default Driver — Operator Frontend Cap Summary

Driver selectors (default GRD) on project + super-agent settings, the api/types/4-locale-i18n plumbing to persist them to `projects.default_driver` / `config_json.driver`, and a chat-transcript "View GRD session" link for grd-driver turns — the thin operator-facing slice of REQ-13 (success criterion 5), green under the no-NEW-failures house gate.

## What Shipped

- **`SuperAgentDriverSelector.vue`** — reusable `v-model` `<select>` over `cliproxy | cli_agent | grd`, defaulting to `grd`. NULL/undefined `modelValue` ("inherit") surfaces as the `grd` default so the control is never blank. Labels from the `driver.options.*` i18n namespace; enum literals never translated.
- **Project settings** (`ProjectSettingsPage.vue`) — an Execution Driver card mounts the selector; on save, a changed driver is sent as `default_driver` through `projectApi.update`.
- **Super-agent settings** (`SuperAgentsPage.vue`) — per-SA-card selector reads the SA's driver back from `config_json.driver` (falling back to `grd`) and persists a change via merge-on-write into `config_json` (other keys preserved), through `superAgentApi.update`. `@click.stop.prevent` keeps the inline control from triggering the card's router-link navigation.
- **Types** — `ExecutionDriver` enum + `Project.default_driver`, `SuperAgent.driver`, `Agent.driver`; re-exported through the api barrel. `projectApi.update` now accepts `default_driver` (and `manager_super_agent_id`, which the view already sent).
- **Transcript linkage** (`ProjectTeamLeaderChat.vue`) — when a `finish` delta carries a session id (`grd_session_id` / `psm_session_id` / `session_id`, bound defensively), the active assistant turn renders a "View GRD session" `RouterLink` to `project-management?session=<psess-id>`.
- **i18n** — `driver.*` namespace added key-identical to en/ko/ja/zh (selector title, project title/description, change hint, saved toast, SA label, `viewGrdSession`, and `options.{grd,cli_agent,cliproxy}`).

## Tasks

| Task | Name | Commit | Key files |
| ---- | ---- | ------ | --------- |
| 1 | Driver selector component + settings wiring + api/types | `6ea95ef8a0` | SuperAgentDriverSelector.vue, ProjectSettingsPage.vue, SuperAgentsPage.vue, projects.ts (api+types), agents.ts, super-agents.ts, index.ts |
| 2 | Transcript GRD-session linkage + 4-locale i18n | `60e8aa56d6` | ProjectTeamLeaderChat.vue, en/ko/ja/zh.json |
| 3 | Component test (default GRD + transcript linkage) | `52bc91c7d8` | __tests__/DriverSelector.test.ts |

## Verification

- **Level 1 (Sanity):** `vue-tsc --noEmit` clean (zero type errors across all touched files). Locale-parity check: `driver.*` and `driver.options.*` keys identical across en/ko/ja/zh. New test: 5/5 green.
- **Full frontend suite:** 1485 passed / 7 failed / 1492 total. All 7 failures are the documented pre-existing baseline (MarkdownContent ×4, WorkingMemoryView ×1, RateLimitGauge ×1, useTourMachine ×1). **0 NEW failures** — house gate (criterion 6) satisfied.
- **`npm run build`:** fails ONLY on the pre-existing unrelated `AnswerGroundednessCard.vue` TS2345 error (documented in STATE.md from phase 17; this plan touches zero lines of that file). No other build errors introduced.

## Deviations from Plan

**1. [Rule 2 - Missing critical functionality] `projectApi.update` type omitted `manager_super_agent_id`.**
- **Found during:** Task 1
- **Issue:** `ProjectSettingsPage.saveSettings` already sent `manager_super_agent_id` but the `projectApi.update` param type didn't declare it — adding `default_driver` to the same union surfaced the gap.
- **Fix:** Added both `manager_super_agent_id` and `default_driver` to the `update` param type.
- **Files modified:** frontend/src/services/api/projects.ts
- **Commit:** `6ea95ef8a0`

**2. [Plan interpretation] Super-agent settings surface.** The plan named "SuperAgentInspectorPage / super-agents config editor." There is no dedicated config-editor form; the live SA settings surface is the per-card control on `SuperAgentsPage.vue`. Mounted the selector there (persisting `config_json.driver`), which is the operator's actual SA management surface.

## Integration Notes (Level 3 — deferred)

The transcript link binds to a session-id field on the `finish` delta that the backend `grd_chat_bridge.bridge_psm_to_chat` does **not** emit today (it sends only `finish_reason`). The binding is forward-compatible (19-RESEARCH §7/risk 2): the link appears the moment the bridge starts surfacing `grd_session_id` on finish. A follow-up backend change (out of this frontend-cap plan's scope) should add the PSM session id to the finish payload so the link renders live. Backend `resolve_execution_driver` precedence (19-01) already consumes `projects.default_driver` and `project_sa_instances.driver`, so persisted selections take effect on the next turn.

## Self-Check: PASSED
