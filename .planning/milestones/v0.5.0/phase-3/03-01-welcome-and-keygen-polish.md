# Plan 03-01: Welcome flow polish — close OB-01/02/03 gaps

**Phase:** 3 — Welcome Flow + Tour Entry
**Requirements:** OB-01 (welcome page no-flash), OB-02 (keygen + copy + warning), OB-03 (smooth transition < 500ms)
**Depends on:** Phase 1, Phase 2
**Verification:** sanity (unit tests for copy + warning + timing)

## Discovery

`frontend/src/views/WelcomePage.vue` already implements the welcome →
keygen → continue flow. The router guard at `frontend/src/router/guards.ts`
already redirects unauthenticated visitors to `/welcome`. Most of OB-01 / 02
/ 03 is in place. Phase 3 closes the remaining gaps:

| Gap | Where | Fix |
|-----|-------|-----|
| Stale version label `v0.4.0` in welcome header | `WelcomePage.vue:96` | bump to `v0.5.0` |
| Phase fade-in 300ms + fade-out 200ms = 500ms — borderline against OB-03's "< 500ms" criterion | `WelcomePage.vue:255-260` | tighten to 250ms / 150ms (= 400ms total) |
| Existing test suite covers welcome → keygen → continue but doesn't assert that the "won't be shown again" warning is visible alongside the generated key (OB-02 acceptance) | `__tests__/WelcomePage.test.ts` | add assertion |
| Existing test suite doesn't exercise the `Copy` button → clipboard path (OB-02 acceptance) | `__tests__/WelcomePage.test.ts` | add test with mocked `navigator.clipboard.writeText` |
| Existing test suite doesn't assert that the keygen `<Transition>` actually runs (OB-03 acceptance) | `__tests__/WelcomePage.test.ts` | add a test that asserts the `phase-fade` transition class is applied |

## Verified satisfied without changes

- **OB-01: welcome page no-flash** — `router/guards.ts:109` checks
  `to.meta.public === true || to.name === 'welcome'`. The bootstrap auth
  status fetch happens once and caches; needs_setup → redirect to welcome
  before any other route renders. No dashboard flash.
- **OB-01: bento grid + value statement + Begin Setup CTA** — all present.
- **OB-02: API key generation** — `healthApi.setup('Admin')` calls
  `POST /health/setup`, returns the key, displayed in `<code class="key-value">`
  monospace. Continue button appears after key shown.
- **OB-03: router transition** — `continueToApp()` calls
  `router.push({ path: '/settings', hash: '#general' })` and triggers
  `tourMachine.nextStep()` so the visual layer engages immediately.

## Files

- `frontend/src/views/WelcomePage.vue` — version label + transition timing.
- `frontend/src/views/__tests__/WelcomePage.test.ts` — 3 new tests
  (warning visible, copy → clipboard, transition class applied).

## Estimated size

~10 lines of code change, ~50 lines of new tests. ~15 minutes.
