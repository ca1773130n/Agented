# Plan 01-02: Persistence layer + guard system + z-index scale

**Phase:** 1 — Backend + State Machine Foundation
**Requirements:** OB-05 (persistence), OB-06 (instance_id invalidation), OB-08 (resume from incomplete), OB-43 (z-index scale)
**Depends on:** 01-01 (needs the machine and `/health/setup-status`)
**Verification:** sanity (unit tests for composable + persistence)

## What this plan delivers

1. `frontend/src/tour/persistence.ts` — load/save helpers using XState's `getPersistedSnapshot` / `createActor({snapshot})` round-trip, with stale-instance invalidation.
2. `frontend/src/tour/useTour.ts` — Vue composable replacing the current ref-based flat-index `useTour.ts`. Wraps `useActor(tourMachine, …)` with hydration + persistence. The OLD `useTour.ts` is deleted in this plan.
3. `frontend/src/tour/setupStatus.ts` — `fetchSetupStatus()` API client (calls `/health/setup-status`, returns typed result).
4. `frontend/src/App.vue` — z-index CSS custom properties (OB-43).
5. Unit tests covering persistence + guard prefetch + resume-from-incomplete.

## Out of scope (Phase 2+)

- Visual layer (overlay, spotlight, tooltip, progress bar) — Phase 2.
- Form-field guidance — Phase 5.
- Welcome page integration — Phase 3.
- E2E tour flow — Phase 10.

## Persistence design

### Storage shape

```ts
interface PersistedTour {
  version: 1
  instanceId: string | null
  snapshot: unknown  // XState's getPersistedSnapshot() output
}
```

`localStorage[agented-tour-state]` holds the JSON-serialized `PersistedTour`. The `version` field lets us migrate format if we ever change shape; for v1 there's no migration logic — older shapes are dropped silently.

### Load sequence

```ts
async function bootTour() {
  const status = await fetchSetupStatus()  // /health/setup-status

  // OB-06: invalidate persistence on instance_id mismatch.
  const persisted = readLocalStorage()
  const stale = persisted && persisted.instanceId !== status.instance_id
  if (stale) {
    localStorage.removeItem(STORAGE_KEY)
  }
  const useSnapshot = !stale && persisted?.snapshot

  const actor = createActor(tourMachine, {
    snapshot: useSnapshot,
    input: {
      instanceId: status.instance_id,
      completed: deriveCompleted(status),
    },
  })

  // OB-08: re-evaluate guards after restore. The actor may land on a state
  // the user already completed manually (e.g. set workspace in /settings).
  // EVALUATE re-fires SKIP for any completed step at-or-after the current
  // state, walking the actor forward to the first incomplete step.
  actor.start()
  actor.send({ type: 'EVALUATE' })

  // Save snapshot on every transition.
  actor.subscribe(() => persist(actor, status.instance_id))

  return actor
}
```

`deriveCompleted(status)` maps the API's `has_*` booleans to the StepId-keyed object the machine context expects.

### Stale-state failure modes

- `/health/setup-status` returns 500 / network error → treat as fresh (no persistence load), let user run the tour. Don't block on it.
- `localStorage.getItem(STORAGE_KEY)` returns malformed JSON → catch, drop, treat as fresh.
- `persisted.version !== 1` → drop, treat as fresh.
- `persisted.instanceId === null && status.instance_id !== null` → fresh DB → drop, treat as fresh (covers the case where the user used a previous DB-less version of the app).

## Guard system

### Adding to the machine

01-01's machine already has the topology. 01-02 extends it with:

1. A new `EVALUATE` event with a transient action that walks completed steps:
   ```ts
   on: {
     EVALUATE: {
       actions: 'autoSkipCompleted',
     },
   }
   ```

2. The `autoSkipCompleted` action reads `context.completed` and `state.value`, then sends one or more `SKIP` events to advance past completed steps. Implementation lives outside the machine (in the actor wrapper) so the action can self-`send` via `actor.send`.

3. Per-step guards on the entry transitions:
   ```ts
   workspace: {
     entry: [{ type: 'autoSkipIfDone', params: { stepId: 'workspace' } }],
     ...
   }
   ```

   This handles the rare case where a user resumes mid-tour and the step they're on was completed *while the tour was suspended* — without `EVALUATE`, they'd land on the stored state and only skip past on next transition.

### Guard list (matches `/health/setup-status` fields)

| Step | Guard |
|------|-------|
| `workspace` | `status.has_workspace` |
| `setup.backends.claude` | `status.has_claude_account` |
| `setup.backends.codex` | `status.has_codex_account` |
| `setup.backends.gemini` | `status.has_gemini_account` |
| `setup.backends.opencode` | `status.has_opencode_account` |
| `monitoring` | always show (read-only step) |
| `harness` | `status.has_harness_synced` |
| `product` | `status.has_first_product` |

`monitoring` has no guard — it's a "look at this dashboard" step that doesn't have a completion criterion, so it always shows.

## Z-index scale (OB-43)

Add to `frontend/src/App.vue` `<style>` block:

```css
:root {
  --z-dropdown: 1000;
  --z-modal: 2000;
  --z-toast: 3000;
  --z-tour-overlay: 4000;
  --z-tour-spotlight: 4001;
  --z-tour-tooltip: 4002;
  --z-tour-progress: 4003;
}
```

Tour components (Phase 2+) consume these via `z-index: var(--z-tour-overlay)`. Existing app modals/dropdowns/toasts may already use hardcoded values; auditing them is out of scope here — Phase 7's "modal coordination during tour" plan handles cross-cutting fixes.

## Migration from the old `useTour.ts` — DEFERRED to Phase 2

**Decision (during execution):** the old `frontend/src/composables/useTour.ts`
stays in place alongside the new `frontend/src/tour/useTour.ts`. Both
co-exist until Phase 2 rewrites the visual layer (TourOverlay, TourTooltip,
TourSpotlight, etc.) — at that point it's natural to switch the rewritten
components to import from `@/tour/useTour`.

Reason: the new composable's public surface differs from the old one
(`snapshot.value` / `currentStepId` instead of the old `currentStep` /
`currentStepIndex`). Forcing 9 existing consumers (App.vue, main.ts,
WelcomePage, ProductsPage, ProductDashboard, GeneralSettings, AppSidebar,
TourOverlay, plus the existing tour tests) to migrate in this plan would
either (a) duplicate the old surface on the new composable just to keep
them working, or (b) require touching every consumer for a Phase 2 rewrite
anyway.

The new files live under `frontend/src/tour/` so import paths don't
collide. Phase 2's first plan should explicitly include the consumer
migration + the deletion of `frontend/src/composables/useTour.ts`.

## Test plan

`frontend/src/tour/__tests__/persistence.test.ts`:
- `roundtrips snapshot through localStorage`
- `drops persisted state when instanceId mismatches`
- `drops persisted state when version mismatches`
- `drops persisted state when JSON is malformed`
- `falls back to fresh start when /health/setup-status is unreachable`

`frontend/src/tour/__tests__/guards.test.ts`:
- `EVALUATE auto-skips completed workspace step`
- `EVALUATE auto-skips completed claude account step inside backends compound state`
- `EVALUATE walks past multiple completed steps to first incomplete`
- `EVALUATE on a state where current step is incomplete is a no-op`
- `manual SKIP on workspace lands on backends.claude even if claude is also done — user explicit skip respected per-step`

`frontend/src/tour/__tests__/setupStatus.test.ts`:
- `fetchSetupStatus parses the JSON response into typed shape`
- `fetchSetupStatus returns a sentinel "unknown" object on network error (caller treats as fresh)`

## Files

- `frontend/src/tour/persistence.ts` — new (~80 lines)
- `frontend/src/tour/setupStatus.ts` — new (~40 lines)
- `frontend/src/tour/useTour.ts` — new (~120 lines)
- `frontend/src/tour/__tests__/persistence.test.ts` — new
- `frontend/src/tour/__tests__/guards.test.ts` — new
- `frontend/src/tour/__tests__/setupStatus.test.ts` — new
- `frontend/src/composables/useTour.ts` — deleted
- `frontend/src/App.vue` — add z-index custom properties (~10 lines)
- Any callsites importing from `@/composables/useTour` — update path.

## Estimated size

~350 lines new code, ~250 lines new tests. ~60 minutes of focused work.
