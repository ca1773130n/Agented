---
phase: 20-grd-frontend-wiring
plan: 03
subsystem: frontend
tags: [research, grd, sse, i18n, vue]
requires: ["20-01", "20-02"]
provides:
  - "ProjectResearchPage.vue (route project-research)"
  - "useResearchSession composable (SSE)"
  - "5 research components (QuestionIntake/ThreadList/HypothesisLedger/ReportViewer/PortfolioRuns)"
  - "surface.research.* i18n namespace (en/ko/ja/zh, key-identical)"
affects:
  - "frontend/src/router/routes/projects.ts"
  - "frontend/src/locales/*.json"
tech-stack:
  added: []
  patterns:
    - "renderMarkdown from useMarkdown.ts (DOMPurify-sanitized GREEN renderer) for markdown bodies"
    - "createI18n with real surface.research messages in component tests (DriverSelector house pattern)"
key-files:
  created:
    - frontend/src/views/ProjectResearchPage.vue
    - frontend/src/composables/useResearchSession.ts
    - frontend/src/components/grd/research/QuestionIntake.vue
    - frontend/src/components/grd/research/ThreadList.vue
    - frontend/src/components/grd/research/HypothesisLedger.vue
    - frontend/src/components/grd/research/ReportViewer.vue
    - frontend/src/components/grd/research/PortfolioRuns.vue
    - frontend/src/views/__tests__/ProjectResearchPage.test.ts
    - frontend/src/components/grd/research/__tests__/research-components.test.ts
    - frontend/src/composables/__tests__/useResearchSession.test.ts
  modified:
    - frontend/src/router/routes/projects.ts
    - frontend/src/locales/en.json
    - frontend/src/locales/ko.json
    - frontend/src/locales/ja.json
    - frontend/src/locales/zh.json
decisions:
  - "Markdown renderer = renderMarkdown() from composables/useMarkdown.ts (DOMPurify-sanitized, used by chat/PlanningSessionPanel) — NOT the baseline-broken MarkdownContent component"
  - "Route name 'project-research' at /projects/:projectId/research (for 20-05 deep-link)"
  - "Reused PlanningSessionPanel for the live SSE output panel (ResearchQuestion shape matches PlanningQuestion)"
metrics:
  duration_min: 14
  tasks: 3
  files: 15
  completed: 2026-06-13
---

# Phase 20 Plan 03: Research Page (REQ-15) Summary

A `ProjectResearchPage` mirroring `ProjectPlanningPage` — composing `QuestionIntake`,
`PortfolioRuns`, `ThreadList`, `HypothesisLedger`, and `ReportViewer` over a new
`useResearchSession` SSE composable and the 20-02 `researchApi` — makes the GRD
autoresearch loop fully operable from the frontend, with all strings localized
key-identical across en/ko/ja/zh.

## What shipped

- **useResearchSession** (`composables/useResearchSession.ts`): mirrors `usePlanningSession`
  — `createAuthenticatedEventSource` via `researchApi.streamResearch` + `output`/`question`/
  `complete`/`error` listeners + `onUnmounted` cleanup. `start(question, opts)` calls
  `researchApi.startResearch`; `resume(threadId, opts)` calls `researchApi.resumeThread`;
  both then subscribe to the session SSE.
- **Route**: `project-research` at `/projects/:projectId/research` (lazy import, `props: true`,
  `meta.requiresEntity: 'projectId'`), mirroring the planning entry.
- **ProjectResearchPage**: `EntityLayout` + `PageHeader` + intake + portfolio + thread list +
  selected-thread (`getThread`) ledger/report + a live `PlanningSessionPanel` (reused) on submit.
  Refreshes threads + selected bundle on the `complete` status watch.
- **5 components**, all `t('surface.research.*')` only:
  - `QuestionIntake` — question textarea + max-iterations/no-gates knobs, emits `submit`.
  - `ThreadList` — status/iteration rows from `listThreads`, emits `select`.
  - `HypothesisLedger` — HYPOTHESES.md via `renderMarkdown`.
  - `ReportViewer` — FINDING.md via `renderMarkdown`.
  - `PortfolioRuns` — total/running/completed/iteration aggregate.
- **i18n**: new top-level `surface.research.*` namespace in all four catalogs, key-identical
  (parity verified by script), translated per locale.

## Markdown renderer choice (for 20-05 deep-link / future ref)

Per the RESEARCH house rule, `MarkdownContent.vue` (in the 7-failure baseline) was avoided.
`HypothesisLedger` and `ReportViewer` use **`renderMarkdown()` from `composables/useMarkdown.ts`**
— a `marked` + `DOMPurify`-sanitized renderer already in green use by chat / `PlanningSessionPanel`.
Output is bound via `v-html` on a sanitized string (XSS-safe; comment-documented in both components).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Benign i18n `[Vue warn]` false-positive in tests**
- **Found during:** Task 2 (running page + component tests).
- **Issue:** Creating a fresh `createI18n` per test re-registers global i18n components
  (`i18n-t`, `I18nT`, `i18n-n`, …) → "already been registered" `[Vue warn]`, which is not a
  component-mount defect but tripped the strict no-Vue-warn assertion.
- **Fix:** The no-Vue-warn assertion filters out `... already been registered` lines while still
  failing on any real mount warning.
- **Files modified:** the two new test files. **Commit:** 262ced7787.

**2. [Rule 3 - Blocking] Strict vue-i18n locale-name typing in test `createI18n`**
- **Found during:** Task 2 (vue-tsc build includes `src/**/*.test.ts`).
- **Issue:** vue-i18n's augmented schema narrows the locale key (`"en-US"`); passing
  `{ en: { surface } }` from imported JSON failed type inference.
- **Fix:** `messages: { en: { surface: enLocale.surface } } as never` (test-only cast) + explicit
  `(c: unknown[])` typing on the warn filter. Matches the tolerated DriverSelector test pattern.

## Experiment Results

| Metric | Baseline | Target | Achieved | Status |
|--------|----------|--------|----------|--------|
| P4: research tests pass | usePlanningSession streams | 0 new failures, no Vue warn | 17/17 pass (6 composable + 9 component + 2 page) | PASS |
| S6: surface.research.* in 4 locales | — | key-identical en/ko/ja/zh | present, parity OK | PASS |
| S1: vue-tsc build | only pre-existing AnswerGroundednessCard err | no new TS errors | only AnswerGroundednessCard remains | PASS |

## Verification

- **Level 1 (Sanity):** route `project-research` resolves; `surface.research.*` in all 4 locales
  (S6 script → all `true`); `vue-tsc -b` → 1 error, the pre-existing AnswerGroundednessCard (S1).
- **Level 2 (Proxy):** P4 — all 17 research tests green; no new failures.
- **Level 3 (Deferred):** live SSE incremental hypothesis render in a real browser (DEFER-20-01);
  locale visual review (DEFER-20-03).

## Self-Check: PASSED
