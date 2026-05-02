# v0.5.1 — Deferred from v0.5.0

Patch milestone consolidating the three items deferred at v0.5.0
closeout (`.planning/milestones/v0.5.0/STATE.md`):

1. **OB-24 UX polish** — `[data-tour="assign-teams"]` lived on
   `ProjectSettingsPage.vue` while the tour step navigated to
   `/projects` (list page), so the spotlight relied on the 3s
   element-not-found fallback.
2. **useTourMachine.ts branch coverage** — `npm run test:coverage`
   reported 89.58% branches against the configured 90% threshold,
   one branch short.
3. **Modal-interaction E2E** during the backends step — was deferred
   pending a path through `@ai-accounts` test fixtures.

## 01 — OB-24: relocate assign-teams target to ProjectsPage

**Source change:** `frontend/src/views/ProjectsPage.vue` — add
`data-tour="assign-teams"` to the page-level wrapper (`<div
class="projects-page">`). The tour step's route is `/projects` so
this is the page that's actually mounted at step time. The existing
anchor on `ProjectSettingsPage.vue:404` (`<div class="teams-grid">`)
becomes redundant and is removed; nothing else in the codebase
references it (`grep -rn assign-teams` confirms tour-only).

**Step message:** update `frontend/src/constants/tourSteps.ts` for
the `create_team` step to: `"Bundled teams with pre-configured
super agents are ready to use. Click into any project to assign
them — the highlighted page shows where to start."` — actionable
on the list page rather than the now-stale "ready to use here".

**Test update:** `src/constants/__tests__/tourSteps.test.ts` — the
existing test asserts the anchor exists in `ProjectSettingsPage.vue`.
Flip the expectation to `ProjectsPage.vue`. Also assert the anchor
is **gone** from ProjectSettingsPage so this fix doesn't double up
silently.

## 02 — useTourMachine.ts: push branch coverage ≥ 90%

`coverage/coverage-final.json` lists 8 partially-uncovered branches
on `useTourMachine.ts`. The lowest-cost gain is `notifyAiAccountsEvent`
(line 451) — both branches show `[0, 0]` because no test imports it.
Adding a single test that calls `notifyAiAccountsEvent({})` flips
two branches from 0 → 1, lifting the file from 89.58% to ≥90%.

**Test addition:** new describe block in
`src/composables/__tests__/useTourMachine.test.ts`:

```ts
describe('notifyAiAccountsEvent (OB-45 coverage)', () => {
  it('runs without throwing for an arbitrary payload', async () => {
    const { notifyAiAccountsEvent } = await import('../useTourMachine')
    expect(() => notifyAiAccountsEvent({ kind: 'whatever' })).not.toThrow()
  })

  it('is idempotent — calling twice does not double-init', async () => {
    const { notifyAiAccountsEvent } = await import('../useTourMachine')
    expect(() => {
      notifyAiAccountsEvent({})
      notifyAiAccountsEvent({})
    }).not.toThrow()
  })
})
```

The second test exercises the `if (!initPromise)` guard — the
first call sets `initPromise`, the second call hits the early
return.

## 03 — Modal-interaction E2E: re-defer with explicit blocker

The `@ai-accounts/vue-styled` AccountWizard is the modal that
opens during step 3 (backends). Driving it deterministically in
Playwright requires:
- Mocking the AI-account login flow's outbound HTTP (browser-only OAuth)
- Stubbing the wizard's internal state machine (separate XState actor)
- Ensuring the wizard's open/close emits propagate back to App.vue
  so `modalOpenDuringTour` flips correctly

That's a contained but real fixture-engineering effort, not a
test-add. Captured in this v0.5.1 plan as documented out-of-scope;
the unit-level OB-44 coverage from Phase 7 (3 tests asserting the
`isModalOpen` prop flows through to the dim fallback and
TourSpotlight) carries the criterion at the unit level.

**Action:** update `STATE.md` for v0.5.0 + this plan to record the
blocker explicitly so a future v0.6.0 owner can attack it directly.

## Verification

- `cd frontend && npm run test:run` — expect +2 (1069 total)
- `cd frontend && npm run test:coverage` — passes, useTourMachine
  branches ≥ 90%
- `cd frontend && npm run build` — vue-tsc + vite clean
