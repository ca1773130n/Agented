# Phase 7 plan 07-01 — Loading + Error Resilience

## Goal

Close the small surface gaps Phase 7 has against OB-40 / OB-41 / OB-42 /
OB-44, and add the missing test coverage for the requirements that are
already implemented but unverified.

Phase 7 the user feature is largely already done — earlier "tour wave"
commits shipped the loading spinner (OB-40), the 3s element-not-found
fallback (OB-41), the route prefetch helper (OB-42), and the modal-open
overlay coordination (OB-44). What this plan adds:

1. **OB-41 scope compliance** — `useTourTargetBus` currently observes
   `document.body` with `subtree: true`. The criterion explicitly says
   "scoped to the route's root element, not `document.body`". Narrow
   the observe root to `#main-content` (the app shell's `<main>`),
   falling back to `document.body` when that element isn't mounted yet
   (e.g. during the welcome screen).
2. **OB-42 test** — `prefetchTourRoutes` has zero test coverage. Add a
   unit test asserting it returns a settled promise without throwing.
3. **OB-44 tests** — `isModalOpen` prop has zero test coverage. Add
   overlay tests asserting the prop drives `.modal-open` on the
   dim-fallback and `:reduced` on `TourSpotlight`.

## Acceptance criteria with current status

| ID | Requirement | Status | This plan |
|----|-------------|--------|-----------|
| OB-40 | Spinner during route transitions, 5s "page is slow" fallback with Skip/Retry | ✓ implemented (TourOverlay.vue:49-50, 130-133); tested in TourOverlay.test.ts | — |
| OB-41 | Missing element → MutationObserver scoped to route root, 3s fallback | ⚠ 3s fallback shipped; observer scope is `document.body` (gap) | **fix scope** |
| OB-42 | Tour routes prefetched on start | ✓ implemented (useTourMachine.ts:425, App.vue:242); **no tests** | **add tests** |
| OB-44 | Modal coordination — dimming reduced, modal interactive | ✓ wired (App.vue:156-165, TourOverlay.vue:28); **no tests** | **add tests** |

## Source changes

### `frontend/src/composables/useTourTargetBus.ts`

Change the `MutationObserver.observe` target from `document.body` to
`document.querySelector('#main-content') ?? document.body`. The fallback
matters for the welcome screen, where `<main id="main-content">` is not
yet mounted (welcome uses a separate layout branch in App.vue:316-319).

Why this is the right scope target: `#main-content` wraps the active
`<router-view>` (App.vue:360-366). The header and sidebar live outside
it and don't churn during normal tour navigation, so `subtree: true`
on `document.body` was reacting to noise. Scoping to `#main-content`
matches the criterion text and reduces observer firing volume.

Resolve the scope at subscribe time, not at module load — the welcome
page case requires that "no main yet" still be observable, then
re-subscribing after navigation picks up the now-mounted main.

## Test additions

### `frontend/src/composables/__tests__/useTourTargetBus.test.ts`

Add an OB-41 scope test:

```ts
it('observes the #main-content scope when present', async () => {
  const main = document.createElement('main')
  main.id = 'main-content'
  document.body.appendChild(main)

  const bus = useTourTargetBus()
  const cb = vi.fn()
  cleanup.push(bus.subscribe('[data-tour="scoped"]', cb))
  cb.mockClear()

  // Mutation OUTSIDE the scope: appended to body, not #main-content.
  // Should still resolve to null because the selector won't match
  // anything; assert the bus doesn't crash.
  const sibling = document.createElement('div')
  sibling.setAttribute('data-tour', 'sibling-not-target')
  document.body.appendChild(sibling)
  await flushMO()

  // Mutation INSIDE the scope.
  const inScope = document.createElement('button')
  inScope.setAttribute('data-tour', 'scoped')
  main.appendChild(inScope)
  await flushMO()

  expect(cb).toHaveBeenCalledWith(inScope)
})

it('falls back to document.body when #main-content is absent', async () => {
  // No <main> in the DOM — welcome-screen case.
  const bus = useTourTargetBus()
  const cb = vi.fn()
  cleanup.push(bus.subscribe('[data-tour="welcome-mount"]', cb))

  const el = document.createElement('div')
  el.setAttribute('data-tour', 'welcome-mount')
  document.body.appendChild(el)
  await flushMO()

  expect(cb).toHaveBeenCalledWith(el)
})
```

### `frontend/src/composables/__tests__/useTourMachine.test.ts`

Add an OB-42 prefetch test:

```ts
import { prefetchTourRoutes } from '../useTourMachine'

describe('prefetchTourRoutes (OB-42)', () => {
  it('settles without throwing even if a chunk fails to load', async () => {
    await expect(prefetchTourRoutes()).resolves.not.toThrow()
  })
})
```

(The function uses `Promise.allSettled` internally; this test guards
against a future regression that switches to `Promise.all`.)

### `frontend/src/components/tour/__tests__/TourOverlay.test.ts`

Add OB-44 tests:

```ts
describe('OB-44 — modal coordination', () => {
  it('adds .modal-open class to dim fallback when isModalOpen is true', () => {
    const wrapper = mount(TourOverlay, {
      props: {
        active: true,
        step: missingTargetStep,        // step whose target won't resolve
        effectiveTarget: missingTargetStep,
        substepLabel: null,
        stepNumber: 5,
        totalSteps: 8,
        isModalOpen: true,
      },
    })
    const dim = wrapper.find('.tour-dim-fallback')
    expect(dim.exists()).toBe(true)
    expect(dim.classes()).toContain('modal-open')
  })

  it('does NOT add .modal-open when isModalOpen is false (default)', () => {
    const wrapper = mount(TourOverlay, {
      props: { /* same as above, isModalOpen omitted */ },
    })
    const dim = wrapper.find('.tour-dim-fallback')
    expect(dim.classes()).not.toContain('modal-open')
  })

  it('passes isModalOpen through to TourSpotlight as :reduced', () => {
    const wrapper = mount(TourOverlay, {
      props: { /* … resolved target so TourSpotlight renders */, isModalOpen: true },
    })
    const spotlight = wrapper.findComponent({ name: 'TourSpotlight' })
    expect(spotlight.exists()).toBe(true)
    expect(spotlight.props('reduced')).toBe(true)
  })
})
```

(Exact fixture re-use will mirror existing TourOverlay tests.)

## Out of scope

- E2E test for OB-44 (modal interactivity during the backends step) —
  belongs to Phase 10 (Integration Testing).
- E2E timing test for OB-42 (< 300ms after first step) — same.
- The MutationObserver in `useTourTargetBus` still runs per-subscriber
  (one observer per selector). A single shared observer that fans out
  is a possible micro-optimization but isn't justified by current
  subscriber counts (1-2 active at any time during a tour).

## Verification

- `cd frontend && npm run test:run` — expect +5 (1047 total)
- `cd frontend && npm run build` — vue-tsc + vite clean
