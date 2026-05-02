# Phase 8 plan 08-01 — Accessibility

## Goal

Close OB-36 (reduced motion), OB-37 (focus trap), OB-38 (ARIA live),
and OB-39 (keyboard-only completion) with unit-level coverage.

OB-38 is already satisfied and tested (TourOverlay aria-live region,
TourOverlay.test.ts:284-326). Most of Phase 8 was wired by earlier
tour-wave commits — what this plan adds:

1. **OB-36 spinner gap** — `TourOverlay.vue:350` has `animation: spin
   1.2s linear infinite` for the loading spinner with no
   `prefers-reduced-motion: reduce` guard. Add the guard so reduced
   motion truly disables ALL tour animations, not just the major
   ones (spotlight movement, tooltip transitions, glow, completion
   icon — those already have guards).
2. **OB-36 tests** — reduced-motion CSS presence is currently
   unverified. Add presence tests across TourSpotlight, TourTooltip,
   TourCompletionScreen, and TourOverlay using the same regex-
   over-`<style>`-block pattern already used for the "no hardcoded
   colors" tests in TourProgressBar.test.ts:75-87.
3. **OB-37 wiring test** — `TourTooltip.vue:118` calls
   `useFocusTrap(floating, isTrapActive)` but no test verifies the
   wiring. Add a mocked-composable test asserting it's invoked with
   the floating element ref and that the active flag flips with
   step visibility.
4. **OB-39 keyboard reachability** — the criterion "tested by E2E"
   is Phase 10's job, but we can prove the unit foundation: assert
   that no `tabindex="-1"` exists on the actual interactive controls
   (skip/next/dismiss/confirm-skip/cancel-skip) in the progress bar.

## Acceptance criteria with current status

| ID | Requirement | Status | This plan |
|----|-------------|--------|-----------|
| OB-36 | Reduced motion disables all tour animations | ⚠ guards on spotlight/tooltip/completion/glow; spinner has no guard | **fix spinner + add presence tests** |
| OB-37 | Focus trapped within tooltip + target | ✓ wired (TourTooltip.vue:118); **no tests** | **add wiring test** |
| OB-38 | ARIA live updates on every step change | ✓ implemented + tested | — |
| OB-39 | Keyboard-only completion | ✓ Enter/Escape in TourOverlay; existing tests cover keyboard nav. E2E deferred | **add tabindex sanity test** |

## Source changes

### `frontend/src/components/tour/TourOverlay.vue`

Append a `prefers-reduced-motion` block before `</style>`:

```css
@media (prefers-reduced-motion: reduce) {
  .spinner-icon { animation: none; }
  .tour-dim-fallback { transition: none; }
}
```

The `.tour-dim-fallback` has a `transition: opacity 0.2s ease` (line
325) that's also unguarded; including it is consistent with the
"all animations" criterion.

## Test additions

### Reduced-motion presence — 4 new tests (one per component)

Pattern: read the `.vue` file's `<style>` block as a string and
assert it contains the `@media (prefers-reduced-motion: reduce)`
at-rule. Same shape as the existing color-presence tests.

- `frontend/src/components/tour/__tests__/TourSpotlight.test.ts` —
  asserts `prefers-reduced-motion` block exists with `animation: none`
  on `.tour-spotlight-glow` and `transition: none` on `.tour-spotlight`.
- `frontend/src/components/tour/__tests__/TourTooltip.test.ts` —
  asserts the block exists and disables `.tour-tooltip` transition.
- `frontend/src/components/tour/__tests__/TourCompletionScreen.test.ts` —
  asserts the block exists and disables `.completion-icon` animation.
- `frontend/src/components/tour/__tests__/TourOverlay.test.ts` —
  asserts the (newly added) block exists and disables `.spinner-icon`
  animation.

### OB-37 — focus trap wiring test

Mock `useFocusTrap` and assert TourTooltip calls it with the floating
ref + a reactive active flag.

```ts
vi.mock('../../../composables/useFocusTrap', () => ({
  useFocusTrap: vi.fn(),
}))
```

Then mount TourTooltip with `visible=true` and assert
`useFocusTrap` was called.

### OB-39 — interactive controls reachable

Assert that `.tour-skip-btn`, `.tour-next-btn`, and `.tour-dismiss-btn`
in TourProgressBar have no `tabindex="-1"` (the only way to make a
button keyboard-unreachable). They're `<button>` elements by default
keyboard-reachable, so this is a regression guard.

## Out of scope (Phase 10)

- E2E test that emulates `prefers-reduced-motion: reduce` and
  observes that no animations fire (Playwright `emulateMedia`).
- E2E test that completes the entire tour via keyboard only.
- E2E test that tabs through the tooltip + target and verifies focus
  containment.

## Verification

- `cd frontend && npm run test:run` — expect +7 (1055 total)
- `cd frontend && npm run build` — vue-tsc + vite clean
