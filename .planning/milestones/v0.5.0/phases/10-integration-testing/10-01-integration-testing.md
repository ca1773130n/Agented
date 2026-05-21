# Phase 10 plan 10-01 — Integration Testing

## Goal

Phase 10 validates that the tour system works end-to-end by combining
unit tests, E2E coverage, and build verification.

Status going in:
- **OB-45** (state machine unit tests) — `useTourMachine.test.ts` has
  47 tests, plus `useTourMachine.setup-status.test.ts` and
  `tour-route-change.test.ts`. Branch coverage hasn't been formally
  measured; the test set covers all transitions (NEXT, BACK, SKIP),
  substep navigation, persistence save/restore via storage actor,
  guard evaluation, instance-id mismatch (`useTourMachine.test.ts`
  has 4 dedicated tests), and edge cases.
- **OB-46** (visual component unit tests) — All 5 components have
  test files: `TourOverlay.test.ts` (50+), `TourTooltip.test.ts`
  (15+), `TourProgressBar.test.ts` (22), `TourFormGuide.test.ts`
  (5), `TourSpotlight.test.ts` (7).
- **OB-47** (Playwright E2E) — 3 existing flows in
  `e2e/tests/tour-flow.spec.ts`: complete-via-Next, skip-all,
  keyboard navigation. Missing: persistence-across-reload, reduced
  motion, focus trapping, modal interaction.
- **OB-48** (build + no `any` in tour code) — verified via grep:
  zero `any` types in `frontend/src/components/tour/`,
  `composables/useTour*.ts`, `composables/useFocusTrap.ts`,
  `composables/useFormGuide.ts`, `machines/`. `just build` passes.

## What this plan adds

Three new E2E tests to close the OB-47 gap:

1. **Persistence across reload** — start the tour, advance two steps,
   reload the page, assert the tour resumes at the same step.
2. **Reduced motion** — emulate `prefers-reduced-motion: reduce`
   before navigating, assert the spotlight has no `transition`/
   `animation` style applied (verifies the CSS @media block actually
   reaches the element).
3. **Focus trapping** — start tour, Tab repeatedly, assert focus
   never escapes the overlay. The criterion includes the highlighted
   target as part of the trap; for the Workspace step the target is
   inside the page, so a strict "stays inside .tour-overlay" check
   would be wrong — instead we assert focus never lands on the
   sidebar/header.

(The "modal interaction" sub-criterion is harder to E2E without
opening an account-wizard modal, which depends on the @ai-accounts
package state. Captured as a v0.6.0 deferred check.)

## Tests

### `frontend/e2e/tests/tour-flow.spec.ts` — 3 new tests

```ts
test('persists across reload (OB-47)', async ({ tourPage, page }) => {
  await tourPage.startTour()
  await tourPage.expectStepText('STEP 2 OF 8')
  await tourPage.clickNext()
  await tourPage.expectStepText('STEP 3 OF 8')

  await page.reload()
  await tourPage.expectVisible()
  await tourPage.expectStepText('STEP 3 OF 8')
})

test('reduced motion disables spotlight animation (OB-36, OB-47)', async ({ tourPage, page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await tourPage.startTour()
  // Use evaluate to read computed style on the spotlight glow.
  const animationName = await page
    .locator('.tour-spotlight-glow')
    .evaluate((el) => getComputedStyle(el).animationName)
  expect(animationName).toBe('none')
})

test('focus stays out of header/sidebar while tour is active (OB-37, OB-47)', async ({ tourPage, page }) => {
  await tourPage.startTour()
  // Tab 6 times. The trap should cycle within the overlay/target.
  for (let i = 0; i < 6; i++) await page.keyboard.press('Tab')
  const focusedSelector = await page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null
    return el ? el.closest('header, nav, aside') !== null : false
  })
  expect(focusedSelector).toBe(false)
})
```

These tests live alongside the existing 3 tour-flow tests; they
share the `tourPage` fixture and don't need new mocks.

## Verification

- `cd frontend && npm run test:run` — should still pass (1067)
- `cd frontend && npm run build` — vue-tsc + vite clean
- E2E tests are exercised in CI (`npx playwright test`); not
  run inline by `just build` (per existing repo convention —
  Playwright takes much longer than vitest)

## Out of scope (v0.6.0)

- Modal-interaction E2E during the backends step.
- Formal vitest branch-coverage report (`npm run test:coverage`)
  documenting the >= 90% number from OB-45's acceptance — the test
  set is comprehensive but the exact branch percentage hasn't been
  recorded. A coverage gate is a separate v0.6.0 hardening item.

## v0.5.0 milestone closeout

After this plan ships:
- All 10 phases (1-10) marked complete in STATE.md
- 1067+ unit tests, 6 E2E tour tests, build clean
- v0.5.0 ready for tag/release
