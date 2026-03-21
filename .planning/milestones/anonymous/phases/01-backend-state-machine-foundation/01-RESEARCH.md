# Phase 1: Backend + State Machine Foundation - Research

**Researched:** 2026-03-21
**Domain:** XState v5 state machine + Flask backend instance tracking + Vue 3 integration
**Confidence:** HIGH

## Summary

This phase establishes the tour engine infrastructure: an XState v5 state machine that manages the onboarding flow, localStorage persistence that survives reloads, a backend `instance_id` endpoint for DB reset detection, guard functions that auto-skip completed steps, and a z-index CSS custom property scale in App.vue.

The codebase already has a working tour system (`useTour.ts` + `TourOverlay.vue`) with flat index-based navigation, localStorage persistence, and step definitions. This phase replaces the composable internals with XState v5 while preserving the existing step definitions as migration input. The backend needs a single new endpoint (`/health/instance-id`) that returns a stable identifier generated at DB creation time, accessible without authentication (since the tour runs before auth is configured on first use).

**Primary recommendation:** Use XState v5's `setup()` API with `@xstate/vue`'s `useActor` composable, persist via `getPersistedSnapshot()` on every transition, and validate the persisted `instance_id` against the backend on boot to detect DB resets.

## User Constraints (from prior decisions)

### Locked Decisions
- Drop driver.js, use XState v5 + Floating UI + focus-trap
- Existing WelcomePage.vue is approved -- build on it
- Backend needs `app_meta` table with `instance_id` for DB reset detection
- `app_meta.instance_id` endpoint must be accessible before auth (runs during tour boot)

### Claude's Discretion
- XState machine topology (flat vs. hierarchical states)
- Persistence format and localStorage key naming
- Guard function implementation strategy (parallel vs. sequential API calls)
- z-index scale values and naming conventions

### Deferred Ideas (OUT OF SCOPE)
- Visual overlay components (Phase 2)
- Floating UI tooltip positioning (Phase 2)
- Welcome page flow changes (Phase 3)
- Actual step content definitions (Phase 4)
- Form field guidance (Phase 5)

## Paper-Backed Recommendations

### Recommendation 1: XState v5 `setup()` API with Typed Machine Definition
**Recommendation:** Use the XState v5 `setup()` API pattern for creating the tour machine with full TypeScript types for context, events, guards, and actors.

**Evidence:**
- XState v5 official documentation (stately.ai/docs/machines) -- The `setup()` function is the recommended way to create machines with strong typing. It allows upfront definition of types for context, events, actions, guards, and actors.
- XState v5 repo README (github.com/statelyai/xstate) -- Demonstrates `setup()` + `createMachine()` as the canonical v5 pattern.
- `@xstate/vue` README (github.com/statelyai/xstate/packages/xstate-vue) -- Shows `useActor(machine)` returning `{ snapshot, send, actorRef }` for Vue 3 Composition API integration.

**Confidence:** HIGH -- Official documentation from Stately, verified via Context7.
**Caveats:** XState v5 is a major rewrite from v4. The `interpret()` function is replaced by `createActor()`, and `state` is replaced by `snapshot`. Training data may still reference v4 patterns.

### Recommendation 2: `getPersistedSnapshot()` for localStorage Persistence
**Recommendation:** Use `actor.getPersistedSnapshot()` to serialize state, and pass the deserialized object as `snapshot` option to `createActor()` for restoration.

**Evidence:**
- XState v5 persistence docs (stately.ai/docs/persistence) -- Demonstrates the exact pattern: `getPersistedSnapshot()` returns a JSON-serializable object, `createActor(machine, { snapshot: restored }).start()` restores state.
- Deep persistence docs (stately.ai/docs/persistence) -- Confirms child actors (invoked/spawned) are also persisted and restored recursively.
- XState v5 migration guide (stately.ai/docs/migration) -- Confirms `createActor(machine, { snapshot: state })` replaces the deprecated `interpret(machine).start(state)`.

**Confidence:** HIGH -- Multiple official documentation pages confirm this pattern.
**Expected improvement:** Zero-code serialization/deserialization vs. the current manual `JSON.stringify` of individual fields.

### Recommendation 3: Guard Functions with `fromPromise` Actors for API Checks
**Recommendation:** Use XState v5 guards for synchronous checks (localStorage values) and `invoke` with `fromPromise` actors for async API calls (backend account checks, workspace validation).

**Evidence:**
- XState v5 guard docs -- Guards are synchronous functions `({ context, event }) => boolean`. They cannot be async.
- XState v5 invoke docs (stately.ai/docs/invoke) -- `fromPromise` actors handle async operations. Use `invoke.src` + `onDone`/`onError` for API calls.
- Stately docs -- Demonstrates `setup({ actors: { fetchUser: fromPromise(...) } })` pattern for typed async operations.

**Confidence:** HIGH -- Official documentation.
**Caveats:** Guards themselves must be synchronous. For async "should I skip this step?" logic, the machine must enter a transient "checking" state that invokes a promise and auto-transitions based on the result.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `xstate` | ^5.20 | State machine definition, actors, guards | Official XState v5 -- the standard for finite state machines in JS/TS. Actor model, snapshot persistence, typed guards. |
| `@xstate/vue` | ^3.1 | Vue 3 Composition API integration | Official XState-Vue binding. Provides `useActor()` and `useMachine()` composables. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| (none needed) | - | - | All other dependencies already exist in the project |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| XState v5 | Hand-rolled state machine (current approach) | Current `useTour.ts` is 287 lines of imperative index-tracking. XState provides formal state definitions, impossible invalid states, and built-in persistence. Locked decision: use XState. |
| `@xstate/vue` `useActor` | Manual `createActor` + Vue `shallowRef` | `useActor` handles reactive snapshot updates automatically. Manual approach adds boilerplate for no benefit. |

**Installation:**
```bash
cd frontend && npm install xstate@^5.20 @xstate/vue@^3.1
```

## Architecture Patterns

### Recommended Project Structure
```
frontend/src/
├── composables/
│   └── useTourMachine.ts      # XState machine + persistence + instance_id validation
├── machines/
│   └── tourMachine.ts         # Machine definition (setup + createMachine)
├── components/tour/
│   └── TourOverlay.vue        # (existing, modified in Phase 2)
└── App.vue                    # z-index CSS custom properties

backend/app/
├── db/
│   └── app_meta.py            # app_meta table CRUD (get_instance_id)
├── routes/
│   └── health.py              # Add /health/instance-id endpoint (no auth required)
└── db/
    ├── schema.py              # Add app_meta CREATE TABLE
    └── migrations.py          # Migration 96: create app_meta + seed instance_id
```

### Pattern 1: Hierarchical State Machine for Tour Flow
**What:** Use nested (hierarchical) states to model the tour's step/substep structure. The top-level states represent major phases (idle, welcome, workspace, backends, monitoring, harness, product, project, teams, complete). The `backends` state contains child states for each backend substep (claude, codex, gemini, opencode).

**When to use:** When steps have substeps (backends has 4 substeps).

**Example:**
```typescript
// Source: XState v5 docs (stately.ai/docs/machines) + project step definitions from useTour.ts
import { setup, createMachine, assign, fromPromise } from 'xstate';

interface TourContext {
  instanceId: string | null;
  completedSteps: string[];
  currentSubstep: number;
}

type TourEvent =
  | { type: 'START' }
  | { type: 'NEXT' }
  | { type: 'BACK' }
  | { type: 'SKIP' }
  | { type: 'COMPLETE' }
  | { type: 'RESET' };

const tourMachine = setup({
  types: {
    context: {} as TourContext,
    events: {} as TourEvent,
  },
  guards: {
    isWorkspaceSet: ({ context }) => context.completedSteps.includes('workspace'),
    hasAnyBackend: ({ context }) => context.completedSteps.includes('backends'),
  },
  actors: {
    checkWorkspace: fromPromise(async () => {
      const res = await fetch('/api/settings/workspace_root');
      const data = await res.json();
      return !!data.value;
    }),
    checkBackendAccounts: fromPromise(async () => {
      const res = await fetch('/admin/backends');
      const data = await res.json();
      return data.backends?.some((b: any) => b.account_count > 0) ?? false;
    }),
  },
}).createMachine({
  id: 'tour',
  initial: 'idle',
  context: {
    instanceId: null,
    completedSteps: [],
    currentSubstep: 0,
  },
  states: {
    idle: { on: { START: 'welcome' } },
    welcome: { on: { NEXT: 'workspace' } },
    workspace: {
      initial: 'checking',
      states: {
        checking: {
          invoke: {
            src: 'checkWorkspace',
            onDone: [
              { guard: ({ event }) => event.output === true, target: '#tour.backends' },
              { target: 'active' },
            ],
            onError: { target: 'active' },
          },
        },
        active: {
          on: {
            NEXT: '#tour.backends',
            SKIP: '#tour.backends',
          },
        },
      },
    },
    backends: {
      initial: 'claude',
      states: {
        claude: { on: { NEXT: 'codex', SKIP: 'codex' } },
        codex: { on: { NEXT: 'gemini', SKIP: 'gemini' } },
        gemini: { on: { NEXT: 'opencode', SKIP: 'opencode' } },
        opencode: { on: { NEXT: '#tour.monitoring', SKIP: '#tour.monitoring' } },
      },
    },
    monitoring: { on: { NEXT: 'harness' } },
    harness: { on: { NEXT: 'product' } },
    product: { on: { NEXT: 'project', SKIP: 'project' } },
    project: { on: { NEXT: 'teams', SKIP: 'teams' } },
    teams: { on: { NEXT: 'complete', SKIP: 'complete' } },
    complete: { type: 'final' },
  },
});
```

### Pattern 2: Persistence on Every Transition via Subscription
**What:** Subscribe to the actor's state changes and persist on every transition. On boot, load persisted snapshot, validate `instance_id` against backend, and restore or reset.

**When to use:** Always -- this is the core persistence pattern.

**Example:**
```typescript
// Source: XState v5 persistence docs (stately.ai/docs/persistence)
import { createActor } from 'xstate';
import { tourMachine } from '../machines/tourMachine';

const STORAGE_KEY = 'agented-tour-state';

function loadPersistedState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function createTourActor(restoredSnapshot?: any) {
  const actor = createActor(tourMachine, {
    ...(restoredSnapshot ? { snapshot: restoredSnapshot } : {}),
  });

  // Persist on every transition
  actor.subscribe((snapshot) => {
    const persisted = actor.getPersistedSnapshot();
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      ...persisted,
      _instanceId: snapshot.context.instanceId,
    }));
  });

  actor.start();
  return actor;
}
```

### Pattern 3: Backend instance_id Endpoint
**What:** A simple `/health/instance-id` endpoint that returns a UUID generated when the DB was first created. Stored in an `app_meta` table. No authentication required.

**When to use:** Called once on frontend boot to validate persisted tour state.

**Example:**
```python
# Source: Existing health.py pattern in backend/app/routes/health.py
# No auth required -- mirrors /health/auth-status pattern
@health_bp.get("/instance-id")
def instance_id():
    """Public endpoint: returns the backend instance ID.

    Used by the frontend tour system to detect DB resets.
    When the instance_id changes, the frontend clears stale tour state.
    """
    from ..db.app_meta import get_instance_id
    return {"instance_id": get_instance_id()}, 200
```

```python
# backend/app/db/app_meta.py
import uuid
from .connection import get_connection

def get_instance_id() -> str:
    """Get or create the instance_id for this database."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM app_meta WHERE key = 'instance_id'"
        ).fetchone()
        if row:
            return row["value"]
        # Should have been seeded by migration, but handle gracefully
        new_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO app_meta (key, value) VALUES ('instance_id', ?)",
            (new_id,),
        )
        conn.commit()
        return new_id
```

### Anti-Patterns to Avoid
- **Using XState v4 API in v5:** Do NOT use `interpret()`, `machine.transition()`, or `state.matches()` on the old State class. XState v5 uses `createActor()`, `actor.getSnapshot()`, and `snapshot.matches()`.
- **Async guards:** Guards in XState are synchronous. Do NOT try to `await` inside a guard function. Use `invoke` with `fromPromise` for async checks, transitioning based on `onDone`/`onError`.
- **Storing derived state in context:** Do NOT duplicate `snapshot.value` (current state name) into context. The snapshot already contains the state value.
- **Manual snapshot serialization:** Do NOT manually pick fields from the snapshot. Use `getPersistedSnapshot()` which handles the correct serialization format including child actor states.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| State machine | Manual index tracking (current `useTour.ts`) | XState v5 `createMachine` | Formal state definitions prevent invalid states. Built-in persistence, guards, hierarchical states. |
| Snapshot serialization | Manual `JSON.stringify` of individual fields | `actor.getPersistedSnapshot()` | Handles nested actors, action queues, and internal state correctly. |
| Vue reactivity bridge | Manual `shallowRef` + `subscribe` | `@xstate/vue` `useActor()` | Handles Vue reactivity lifecycle, cleanup, and SSR correctly. |
| UUID generation (backend) | Manual random string | Python `uuid.uuid4()` | Cryptographically random, RFC 4122 compliant, zero dependencies. |

**Key insight:** The current `useTour.ts` is 287 lines of hand-rolled state management with flat index tracking. XState replaces this with a formal machine definition where invalid states are structurally impossible, persistence is built-in, and guards provide declarative skip logic.

## Common Pitfalls

### Pitfall 1: Stale localStorage After DB Reset
**What goes wrong:** User completes tour, admin resets the database (deletes `agented.db`), user returns and sees "tour complete" because localStorage still has the old state.
**Why it happens:** localStorage persists across backend lifecycles. The tour state references entities that no longer exist.
**How to avoid:** Store the backend `instance_id` alongside tour state. On boot, fetch `/health/instance-id` and compare. If different, clear all tour localStorage and start fresh.
**Warning signs:** User reports "stuck" tour or cannot re-enter tour after fresh install.

### Pitfall 2: XState v4 vs v5 API Confusion
**What goes wrong:** Code uses `interpret()`, `machine.withContext()`, or `state.matches('foo')` on a State object -- all v4 patterns that don't exist in v5.
**Why it happens:** Training data and many tutorials still reference XState v4. The v5 API is fundamentally different.
**How to avoid:** Use only: `setup()`, `createMachine()`, `createActor()`, `actor.getSnapshot()`, `actor.getPersistedSnapshot()`, `snapshot.matches()`, `snapshot.value`, `snapshot.context`.
**Warning signs:** TypeScript errors about missing methods, runtime "is not a function" errors.

### Pitfall 3: Guard Functions Cannot Be Async
**What goes wrong:** Developer writes `guard: async ({ context }) => { const res = await fetch(...); return res.ok; }` -- this silently returns a truthy Promise object, always passing the guard.
**Why it happens:** Guards look like they should support async operations for API checks.
**How to avoid:** Use a transient "checking" state with `invoke: { src: fromPromise(...), onDone: [...], onError: [...] }`. The machine enters the checking state, invokes the promise, and transitions based on the result.
**Warning signs:** Steps are never skipped even when they should be, or always skipped.

### Pitfall 4: z-index Collisions with Existing App Components
**What goes wrong:** Tour overlay appears behind modals, toasts, or sidebar elements that have high z-index values.
**Why it happens:** The codebase already uses z-index values scattered across components: 100 (sidebar), 200 (header), 1000 (toast), 9999 (unknown), 10000 (current tour overlay). No systematic scale exists.
**How to avoid:** Define CSS custom properties in App.vue with a clear hierarchy. Tour components MUST use these properties, never raw numbers. The current TourOverlay uses 10000-10003 -- preserve this range.
**Warning signs:** Visual layering bugs where tour elements appear behind app UI.

### Pitfall 5: `useActor` vs `useMachine` in @xstate/vue
**What goes wrong:** Developer uses `useMachine` when `useActor` is the correct choice, or vice versa.
**Why it happens:** Both exist in `@xstate/vue`. The naming is confusing.
**How to avoid:** Use `useActor(machine)` -- it creates and manages the actor lifecycle within the Vue component. `useMachine` is an alias that does the same thing. For our case where we need custom actor creation (with restored snapshot), create the actor manually and use `useActor(existingActor)` or access `actorRef` from the composable.
**Warning signs:** Multiple actor instances, state not syncing.

### Pitfall 6: Persistence Snapshot Includes Machine Definition Hash
**What goes wrong:** After updating the machine definition (adding/removing states), the restored snapshot references states that no longer exist, causing runtime errors.
**Why it happens:** `getPersistedSnapshot()` serializes the current state value and context. If the machine topology changes, the persisted state name may not match.
**How to avoid:** Version the persisted state. Include a `_schemaVersion` field alongside the snapshot. When the schema version changes, discard the old snapshot and start fresh. This is analogous to the `instance_id` check but for frontend machine changes.
**Warning signs:** "Unknown state" errors after deploying machine updates.

## Experiment Design

### Recommended Experimental Setup

**Independent variables:**
- Machine topology: flat states vs. hierarchical (nested) states for substeps
- Persistence strategy: persist on every transition vs. persist on specific events only

**Dependent variables:**
- Snapshot size (bytes in localStorage)
- Restore fidelity (does the machine resume at the exact step/substep?)
- Guard evaluation time (how long to check backend APIs?)

**Baseline comparison:**
- Current `useTour.ts`: 287 lines, flat index tracking, manual persistence, no guard system
- Target: formal state machine with zero invalid states, automatic persistence, async guard evaluation

**Validation approach:**
1. Create machine definition with all tour states
2. Write unit test: transition through all states forward, verify no invalid states
3. Write unit test: persist snapshot, create new actor with snapshot, verify state matches
4. Write unit test: change instance_id in persisted state, verify machine resets to idle
5. Write unit test: guard auto-skip when workspace already set

**Statistical rigor:** Not applicable (deterministic state machine, not stochastic).

### Recommended Metrics

| Metric | Why | How to Compute | Target |
|--------|-----|----------------|--------|
| Invalid state transitions | Core correctness | Unit test all event+state combinations | 0 |
| Restore fidelity | Persistence correctness | Persist, restore, compare `snapshot.value` and `snapshot.context` | 100% match |
| Guard evaluation latency | UX impact | Measure time from tour boot to first step render | < 500ms |
| Snapshot size | localStorage budget | `JSON.stringify(getPersistedSnapshot()).length` | < 2KB |

## Verification Strategy

### Recommended Verification Tiers for This Phase

| Item | Recommended Tier | Rationale |
|------|-----------------|-----------|
| XState machine handles all transitions without errors | Level 1 (Sanity) | Deterministic -- unit testable immediately |
| Persistence survives reload | Level 1 (Sanity) | Can test with mock localStorage |
| instance_id endpoint returns valid UUID | Level 1 (Sanity) | Simple API test |
| instance_id change clears tour state | Level 1 (Sanity) | Unit testable with mocked fetch |
| Guards auto-skip completed steps | Level 2 (Proxy) | Needs mock backend responses |
| z-index scale prevents layering conflicts | Level 3 (Deferred) | Needs visual components (Phase 2) to validate |
| Full tour flow with real backend | Level 3 (Deferred) | Needs all phases integrated (Phase 10) |

**Level 1 checks to always include:**
- Machine transitions from idle -> welcome -> workspace -> ... -> complete without errors
- Machine transitions backward (BACK event) correctly
- SKIP event only works on skippable steps
- `getPersistedSnapshot()` produces valid JSON
- Restored actor resumes at persisted state
- `/health/instance-id` returns `{ instance_id: string }` with UUID format
- Migration 96 creates `app_meta` table and seeds `instance_id`

**Level 2 proxy metrics:**
- Mock workspace API returning `{ value: "/some/path" }` -> guard skips workspace step
- Mock backends API returning accounts -> guard skips backends step
- Mock empty responses -> guard does NOT skip steps

**Level 3 deferred items:**
- Visual z-index layering validation (needs Phase 2 components)
- Full E2E tour flow (needs Phase 10)
- Persistence across actual browser reload (needs running app)

## Production Considerations

### Known Failure Modes
- **localStorage full:** If localStorage quota is exceeded, `setItem` throws. The persistence subscription should catch this silently and continue (tour still works, just won't persist).
  - Prevention: Keep snapshot size under 2KB. Monitor with `JSON.stringify().length`.
  - Detection: `try/catch` around `localStorage.setItem`.

- **Backend unavailable during guard check:** If `/health/instance-id` or guard API calls fail (network error, backend not started), the tour should not block.
  - Prevention: `fromPromise` actors use `onError` transitions that fall through to "active" state (assume step is not completed, let user proceed).
  - Detection: Console warning when guard API fails.

### Scaling Concerns
- **Not applicable:** Tour system is single-user, client-side only. Backend endpoint is a single-row SELECT. No scaling concerns.

### Common Implementation Traps
- **Trap: Importing driver.js alongside XState:** driver.js (`^1.4.0`) is still in `package.json`. It should NOT be imported anywhere in tour code. It can be removed from dependencies in a later phase.
  - Correct approach: Use XState only. Remove driver.js import if it exists anywhere.

- **Trap: Using `/admin/*` endpoints for guard checks without auth:** The settings API is at `/api/settings/*` (no auth middleware visible). The backends API is at `/admin/backends/*` which may require auth. Guard functions must handle 401/403 gracefully.
  - Correct approach: Check if API key is stored (from WelcomePage keygen) before making authenticated requests. Fall through on auth failure.

- **Trap: Mutating context directly:** In XState v5, context is immutable. Use `assign()` action to update context.
  - Correct approach: `actions: assign({ completedSteps: ({ context }) => [...context.completedSteps, 'workspace'] })`

## Code Examples

### Creating the Tour Machine with XState v5 setup() API
```typescript
// Source: XState v5 docs (stately.ai/docs/machines) + @xstate/vue README
import { setup, createMachine, assign, fromPromise } from 'xstate';

// Define the machine with setup() for full type safety
export const tourMachine = setup({
  types: {
    context: {} as {
      instanceId: string | null;
      completedSteps: string[];
      schemaVersion: number;
    },
    events: {} as
      | { type: 'START' }
      | { type: 'NEXT' }
      | { type: 'BACK' }
      | { type: 'SKIP' }
      | { type: 'RESET' },
  },
  guards: {
    isStepCompleted: ({ context }, params: { step: string }) =>
      context.completedSteps.includes(params.step),
  },
  actors: {
    checkInstanceId: fromPromise(async () => {
      const res = await fetch('/health/instance-id');
      const data = await res.json();
      return data.instance_id as string;
    }),
  },
  actions: {
    markStepComplete: assign({
      completedSteps: ({ context, event }, params: { step: string }) =>
        [...context.completedSteps, params.step],
    }),
  },
}).createMachine({
  id: 'tour',
  initial: 'idle',
  context: {
    instanceId: null,
    completedSteps: [],
    schemaVersion: 1,
  },
  states: {
    idle: {
      on: { START: 'welcome' },
    },
    welcome: {
      on: { NEXT: 'workspace' },
    },
    // ... remaining states
    complete: {
      type: 'final',
    },
  },
});
```

### Using the Machine in Vue 3 with @xstate/vue
```typescript
// Source: @xstate/vue README (github.com/statelyai/xstate/packages/xstate-vue)
import { useActor } from '@xstate/vue';
import { tourMachine } from '../machines/tourMachine';
import { createActor } from 'xstate';

export function useTourMachine() {
  // Restore from localStorage if available
  const persisted = loadPersistedState();

  const actor = createActor(tourMachine, {
    ...(persisted ? { snapshot: persisted.snapshot } : {}),
  });

  // Persist on every transition
  actor.subscribe((snapshot) => {
    try {
      localStorage.setItem('agented-tour-state', JSON.stringify({
        snapshot: actor.getPersistedSnapshot(),
        instanceId: snapshot.context.instanceId,
        schemaVersion: snapshot.context.schemaVersion,
      }));
    } catch { /* localStorage full -- continue without persistence */ }
  });

  actor.start();

  // Use useActor for Vue reactivity (pass existing actor)
  const { snapshot, send } = useActor(actor);

  return { snapshot, send, actorRef: actor };
}
```

### Backend instance_id Migration
```python
# Source: Existing migration pattern from backend/app/db/migrations.py
import uuid

def _migrate_96_app_meta(conn):
    """Create app_meta table and seed instance_id."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Seed instance_id for this database instance
    conn.execute(
        "INSERT OR IGNORE INTO app_meta (key, value) VALUES ('instance_id', ?)",
        (str(uuid.uuid4()),),
    )

# Add to VERSIONED_MIGRATIONS list:
# (96, "app_meta", _migrate_96_app_meta),
```

### z-index CSS Custom Properties in App.vue
```css
/* Source: Existing App.vue z-index analysis + tour overlay requirements */
:root {
  /* Application layers */
  --z-sidebar: 100;
  --z-header: 100;
  --z-dropdown: 200;
  --z-modal-backdrop: 199;
  --z-modal: 200;

  /* Toast notification */
  --z-toast: 1000;

  /* Tour layers (must be above all app UI) */
  --z-tour-overlay: 10000;
  --z-tour-spotlight: 10001;
  --z-tour-spinner: 10002;
  --z-tour-tooltip: 10003;
  --z-tour-progress: 10004;
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| XState v4 `interpret()` | XState v5 `createActor()` | XState v5 (2023-12) | Complete API redesign. `interpret` -> `createActor`, `state` -> `snapshot`, `machine.withContext` removed |
| XState v4 `createMachine` (standalone) | XState v5 `setup().createMachine()` | XState v5 (2023-12) | Type-safe machine creation with upfront type definitions |
| XState v4 `@xstate/vue` `useMachine` | XState v5 `@xstate/vue` `useActor` | @xstate/vue v3 | `useActor` is the primary API; `useMachine` is a compat alias |

**Deprecated/outdated:**
- `interpret()`: Replaced by `createActor()` in v5.
- `machine.withContext()`: Removed. Pass context directly in `createMachine({ context: ... })`.
- `state.matches()`: Still works but called on `snapshot` not `state`. The object is now called a snapshot.
- `@xstate/vue` v2 (for XState v4): Incompatible with XState v5. Must use `@xstate/vue` v3+.

## Open Questions

1. **`useActor` with pre-created actor for persistence restoration**
   - What we know: `useActor(machine)` creates a new actor internally. We need to pass a pre-created actor (with restored snapshot) instead.
   - What's unclear: Whether `useActor` accepts an existing `ActorRef` or only a machine definition. The docs show both patterns.
   - Recommendation: Create the actor manually with `createActor(machine, { snapshot })`, then check if `useActor` can accept the actorRef. If not, use `shallowRef` + `subscribe` for Vue reactivity (fallback). Test during implementation.

2. **Schema version handling for machine topology changes**
   - What we know: Persisted snapshots include state names. If machine states change between versions, restoration fails.
   - What's unclear: Does XState v5 handle unknown states gracefully (fallback to initial) or throw?
   - Recommendation: Include a `schemaVersion` in persisted data. On version mismatch, discard and start fresh. Test by persisting a snapshot, modifying the machine, and attempting restore.

3. **RBAC middleware on guard API calls**
   - What we know: Settings API is at `/api/settings/*`. Backends API is at `/admin/backends/*`. The `/admin/*` prefix may have RBAC middleware (`require_role` decorators visible on onboarding routes).
   - What's unclear: Whether `/admin/backends` requires auth when no keys are configured (first-run scenario).
   - Recommendation: Guards should include the API key from localStorage (set during WelcomePage keygen) in request headers. Fall through silently on 401/403 (assume step not completed).

## Sources

### Primary (HIGH confidence)
- XState v5 official documentation (stately.ai/docs/machines) -- Machine creation with `setup()` API, verified via Context7 `/websites/stately_ai`
- XState v5 persistence documentation (stately.ai/docs/persistence) -- `getPersistedSnapshot()` + `createActor({ snapshot })` pattern, verified via Context7
- XState v5 invoke documentation (stately.ai/docs/invoke) -- `fromPromise` actor pattern for async operations, verified via Context7
- `@xstate/vue` README (github.com/statelyai/xstate/packages/xstate-vue) -- `useActor` and `useMachine` composables for Vue 3, verified via Context7 `/statelyai/xstate`
- XState v5 migration guide (stately.ai/docs/migration) -- v4 -> v5 API changes, verified via Context7
- Existing codebase analysis -- `useTour.ts`, `TourOverlay.vue`, `health.py`, `migrations.py`, `schema.py`, `settings.py`, `backends.ts` examined directly

### Secondary (MEDIUM confidence)
- XState v5 guard documentation -- Guards are synchronous; async checks require `invoke` pattern. Confirmed across multiple Context7 results.

### Tertiary (LOW confidence)
- `useActor` accepting existing actor reference -- Documented in snippets but needs runtime validation during implementation.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- XState v5 and @xstate/vue are the official libraries, versions confirmed via Context7
- Architecture: HIGH -- Machine topology, persistence pattern, and backend endpoint all follow established patterns from official docs
- Paper recommendations: HIGH -- All recommendations cite official XState v5 documentation verified via Context7
- Pitfalls: HIGH -- Derived from direct codebase analysis (z-index values, API patterns, existing tour code) and official XState v4->v5 migration guide

**Research date:** 2026-03-21
**Valid until:** 2026-04-21 (XState v5 is stable; 30-day validity)
