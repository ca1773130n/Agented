# Phase 9 plan 09-01 — Post-Tour Experience

## Goal

Phase 9 the user feature is largely already shipped — TourCompletionScreen
(OB-34) renders configured/skipped lists and is unit-tested; the
sidebar setup checklist (OB-35) is wired via `useTourChecklist` +
`AppSidebar.vue:1213-1230`; the Restart button (OB-35a) is in
GeneralSettings.vue:332-346 with `restartTour()` covered in
useTourMachine.test.ts:544; and the product/project/team steps
(OB-22, OB-23, OB-24) have data-tour targets in production code.

What's missing is the test coverage that proves these requirements
won't silently regress.

## Acceptance criteria with current status

| ID | Requirement | Status | This plan |
|----|-------------|--------|-----------|
| OB-22 | Product creation step (skippable) | ✓ ProductsPage.vue:180 has `data-tour="create-product"`; tourSteps.ts:128 wires step | **add target presence test** |
| OB-23 | Project creation step (skippable) | ✓ ProductDashboard.vue:239 has `data-tour="create-project"`; tourSteps.ts:139 wires step | **add target presence test** |
| OB-24 | Team assignment step (skippable) | ⚠ ProjectSettingsPage.vue:404 has `data-tour="assign-teams"`, but the tour step's route is `/projects` (list page) — target won't resolve until user navigates into a project. The 3s element-not-found fallback handles this gracefully. The criterion only requires "tour navigates to projects page", not target resolution; deferred UX polish noted. | **add target presence test (no fix)** |
| OB-34 | Completion celebration | ✓ TourCompletionScreen + tested | — |
| OB-35 | Sidebar setup checklist | ✓ wired (`useTourChecklist` + `AppSidebar.vue`); **no tests** | **add composable tests** |
| OB-35a | Restart tour option | ✓ GeneralSettings.vue:342 button + restartTour() tested | **add wiring guard** |

## Test additions

### `frontend/src/composables/__tests__/useTourChecklist.test.ts` (new)

5 tests:

- `checklistItems` length matches `TOUR_STEP_DEFINITIONS.length`
- `checklistItems[i].completed` mirrors
  `tour.context.completedSteps.includes(def.key)` for completed and
  uncompleted steps
- `completedCount` reflects the number of `completed: true` items
- `totalCount === TOUR_STEP_DEFINITIONS.length`
- `showChecklist` is true when state is `'complete'` OR
  `completedSteps.length > 0`, false otherwise

The composable depends on `useTourMachine`, which the existing
useTourMachine tests already exercise — mock the machine return
shape so this test runs without the real XState actor.

### Tour step target presence — 3 tests in tourSteps.test.ts (existing or new)

Use `readFileSync` over the production view files and assert each
`data-tour=` selector is present. Same pattern used by Phase 8's
reduced-motion presence tests.

- `[data-tour="create-product"]` exists in `views/ProductsPage.vue`
- `[data-tour="create-project"]` exists in `views/ProductDashboard.vue`
- `[data-tour="assign-teams"]` exists in `views/ProjectSettingsPage.vue`

### `frontend/src/components/settings/__tests__/GeneralSettings.test.ts` (new) — restart guard

The full GeneralSettings component is large (form state,
DirectoryBrowser, etc.). For OB-35a we just need a regression guard
asserting the restart button + handler are present in source. Use
the source-string pattern:

- import of `tourMachine` (the composable wiring)
- `handleRestartTour` function present
- `restart-tour-btn` class with `@click="handleRestartTour"`

(A full component-render test is out of scope; the rest of
GeneralSettings is intentionally untested at the component level.)

## Out of scope (future / Phase 10)

- E2E test that completes all steps and verifies the completion
  screen content (OB-34).
- E2E test verifying the sidebar checklist after partial tour
  completion (OB-35).
- E2E test restarting the tour from settings (OB-35a).
- UX polish for OB-24: the team-assignment target lives on
  `/projects/:projectId/settings` while the tour step's route is
  `/projects` (list page), so the spotlight relies on the
  element-not-found fallback. Captured here as a known limitation
  for v0.6.0 to address (e.g. add a per-project assign-teams entry
  point on the projects list, or change the step route to navigate
  into the user's most recent project).

## Verification

- `cd frontend && npm run test:run` — expect +9 (1064 total)
- `cd frontend && npm run build` — vue-tsc + vite clean
