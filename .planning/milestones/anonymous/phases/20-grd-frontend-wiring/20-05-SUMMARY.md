---
phase: 20-grd-frontend-wiring
plan: 05
subsystem: frontend
tags: [grd, command-bar, manifest, i18n, routing, tdd]
requires: ["20-02", "20-03", "20-04"]
provides:
  - "GRD_COMMAND_MANIFEST (declarative six-group /grd: command source)"
  - "group-aware invoke routing (research/harness/session)"
affects:
  - "frontend/src/components/grd/PlanningCommandBar.vue"
  - "frontend/src/views/ProjectPlanningPage.vue"
tech-stack:
  added: []
  patterns: ["declarative manifest module", "group-keyed invoke routing", "deprecated-command marker"]
key-files:
  created:
    - "frontend/src/components/grd/planningCommands.ts"
    - "frontend/src/components/grd/__tests__/planningCommands.test.ts"
    - "frontend/src/components/grd/__tests__/PlanningCommandBar.test.ts"
  modified:
    - "frontend/src/components/grd/PlanningCommandBar.vue"
    - "frontend/src/views/ProjectPlanningPage.vue"
    - "frontend/src/locales/en.json"
    - "frontend/src/locales/ko.json"
    - "frontend/src/locales/ja.json"
    - "frontend/src/locales/zh.json"
decisions:
  - "Group keys are capitalized (Plan/Execute/Verify/Research/Harness/Misc); the trailing labelKey segment is lowercase to match i18n convention."
  - "invoke now emits (name, {group}); the page strips the routing-only `group` arg before grd_chat handoff so session args stay clean."
  - "Deep-link via router push to project-research / project-harness with ?command=<name> (forward-compatible query the target surfaces can read)."
  - "evolve retained in the Harness group but flagged deprecated (badge + dimmed), non-default."
metrics:
  duration: ~12min
  completed: 2026-06-13
---

# Phase 20 Plan 05: PlanningCommandBar Manifest (REQ-17) Summary

Extracted PlanningCommandBar's inline `commandGroups` into a typed, unit-testable
`planningCommands.ts` manifest exposing the full supported `/grd:` command set,
regrouped into six functional groups, with group-aware invoke routing wiring the
20-03 research and 20-04 harness surfaces into the planning page.

## Tasks Completed

1. **planningCommands.ts manifest (TDD)** — RED test committed first (failed: module
   absent), then GREEN implementation. `GRD_COMMAND_MANIFEST: GrdCommandGroup[]` plus
   `GrdCommand`/`GrdCommandGroup` types and a `GRD_COMMAND_GROUP_BY_NAME` lookup. 9/9 green.
2. **Bar consumes manifest + group-aware invoke** — PlanningCommandBar imports the
   manifest (no inline array remains), emits `invoke(name, {group})`, badges deprecated
   commands. ProjectPlanningPage routes research->`project-research`, harness->
   `project-harness`, all others->grd_chat session. PlanningCommandBar.test.ts 6/6 green.
3. **i18n expansion** — `planningCommandBar.groups.*` + `.cmd.*` for every command,
   key-identical across en/ko/ja/zh (52 keys each), valid JSON.

## The Six Groups + Command Roster

| Group | Commands |
|-------|----------|
| Plan | plan-phase, plan-milestone-gaps, autoplan, discuss-phase |
| Execute | execute-phase, autopilot, quick |
| Verify | verify-phase, verify-work, assess-baseline |
| Research | research, survey, deep-dive, compare-methods, feasibility |
| Harness | harness, evolve *(deprecated)* |
| Misc | settings, sync, map-codebase, progress, help |

22 commands total (21 supported + evolve deprecated).

## Deviations from Plan

**1. [Rule 1 - Bug] Test i18n message cast** — initial PlanningCommandBar.test.ts used
`en as Record<string, unknown>` for vue-i18n `messages`, which tripped TS2769. Fixed to
plain `{ en }`. Files: PlanningCommandBar.test.ts. Folded into the bar commit.

No architectural changes; the bar was already declarative, so this finished it into a
single-source manifest as planned.

## Experiment Results

| Metric | Baseline | Target | Achieved | Status |
|--------|----------|--------|----------|--------|
| planningCommands.test.ts + PlanningCommandBar.test.ts (P6) | inline groups | pass | 15/15 pass | PASS |
| group count | 4 (old) | >= 6 | 6 | PASS |
| full /grd: set represented | partial | full | 21 supported + evolve | PASS |
| i18n parity (en/ko/ja/zh) | n/a | key-identical | 52 keys each, identical | PASS |

## Verification

- **Level 2 (Proxy, P6):** `vitest --run src/components/grd/__tests__/` → 15/15 green.
- **Level 1 (Sanity, S1):** vue-tsc clean for all three touched source files; pre-existing
  16 errors in harness-panels.test.ts (20-04) + AnswerGroundednessCard.vue (PR #212) are
  baseline — confirmed by stashing this plan's edits (still 16). Zero NEW type errors.
- **Level 1 (Sanity, S6):** planningCommandBar present + valid JSON in all 4 locales.
- **Level 3 (Deferred):** real per-group CLI invocation end-to-end (DEFER-20-02 walkthrough).

## Notes for Reviewers

- `?command=<name>` query on the research/harness deep-links is forward-compatible; the
  target surfaces (20-03/20-04) can read it but are not required to yet.
- `handlePhaseCommand` (phase buttons) passes `{ phase }` with no `group`; routing falls
  back to `GRD_COMMAND_GROUP_BY_NAME[command]`, so plan-phase etc. still route to a session.

## Self-Check: PASSED

- All 4 created files exist on disk.
- All 5 task commits present in git history (52f90f9, dd830d5, 7b88f4e, 4c024b1, 35ae33b).
- Manifest + bar tests 15/15 green; i18n parity verified (52 keys × 4 locales, identical).
