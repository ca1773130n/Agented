# Plan 01-01: Backend setup-status endpoint + XState v5 machine

**Phase:** 1 — Backend + State Machine Foundation
**Requirements:** OB-04 (state machine), OB-06 (instance_id check), OB-07 (guard prefetch)
**Depends on:** Nothing
**Verification:** sanity (unit tests for machine + endpoint)

## What this plan delivers

1. `GET /health/setup-status` — aggregate endpoint returning `{instance_id, has_workspace, has_claude_account, has_codex_account, has_gemini_account, has_opencode_account, has_harness_synced, has_first_product}`. One round-trip lets the tour prefetch every guard at boot (OB-07: "Guards are prefetched at tour start to avoid loading spinners mid-tour"). Public; no auth.
2. `frontend/src/tour/machine.ts` — XState v5 hierarchical state machine with the topology:
   - `idle → welcome → setup → complete`
   - `setup` is a compound state with children: `workspace, backends, monitoring, harness, product`
   - `setup.backends` is a compound state with children: `claude, codex, gemini, opencode`
3. Unit tests for both (`tests/test_litestar_health.py::test_setup_status_*`, `frontend/src/tour/__tests__/machine.test.ts`).

## Out of scope (in 01-02)

- Persistence layer (`localStorage` round-trip via `getPersistedSnapshot`).
- Guard prefetching in a Vue composable.
- Auto-skip-completed-steps via `EVALUATE` event.
- Z-index CSS custom properties.

## Backend design

### `/health/setup-status`

Path: `/health/setup-status`. GET. Public (no auth — same scope as the existing `/health/instance-id`).

```json
{
  "instance_id": "uuid-from-app_meta",
  "has_workspace": true,
  "has_claude_account": false,
  "has_codex_account": false,
  "has_gemini_account": true,
  "has_opencode_account": false,
  "has_harness_synced": false,
  "has_first_product": false
}
```

Implementation: read each from existing DB tables / services.

| Field | Source |
|-------|--------|
| `instance_id` | `app_meta.instance_id` (same as `/health/instance-id`) |
| `has_workspace` | `settings.workspace_root` is set to a non-empty path |
| `has_claude_account` | row in `backend_accounts` where `backend_type='claude'` and not soft-deleted |
| `has_codex_account` | same with `backend_type='codex'` |
| `has_gemini_account` | same with `backend_type='gemini'` |
| `has_opencode_account` | same with `backend_type='opencode'` |
| `has_harness_synced` | `app_meta.harness_synced_at` is set (writes a marker on first sync) |
| `has_first_product` | at least one row in `products` |

Errors are returned as `false` for the boolean field so the tour can still advance — only `instance_id` is mandatory. If the DB is unreadable the endpoint should still 200 with `instance_id: null` so the frontend can detect "fresh install" without erroring.

### Test plan

- `test_setup_status_fresh_db` — empty DB, all booleans false, instance_id is a UUID string.
- `test_setup_status_with_workspace` — `settings.workspace_root` populated → `has_workspace: true`.
- `test_setup_status_with_claude_account` — one row in `backend_accounts` with `backend_type='claude'` → `has_claude_account: true`, others false.
- `test_setup_status_no_auth_required` — endpoint returns 200 without `X-API-Key` header.

## Frontend design

### Machine topology

```ts
import { setup, assign } from 'xstate'

export const tourMachine = setup({
  types: {
    context: {} as TourContext,
    events: {} as TourEvent,
  },
}).createMachine({
  id: 'tour',
  initial: 'idle',
  context: { /* see below */ },
  states: {
    idle: { on: { START: 'welcome' } },
    welcome: { on: { NEXT: 'setup', SKIP_TOUR: 'complete' } },
    setup: {
      initial: 'workspace',
      states: {
        workspace: {
          on: { NEXT: 'backends', BACK: '#tour.welcome', SKIP: 'backends' },
        },
        backends: {
          initial: 'claude',
          states: {
            claude:   { on: { NEXT: 'codex',     BACK: '#tour.setup.workspace', SKIP: 'codex' } },
            codex:    { on: { NEXT: 'gemini',    BACK: 'claude',                  SKIP: 'gemini' } },
            gemini:   { on: { NEXT: 'opencode',  BACK: 'codex',                   SKIP: 'opencode' } },
            opencode: { on: { NEXT: '#tour.setup.monitoring', BACK: 'gemini',     SKIP: '#tour.setup.monitoring' } },
          },
        },
        monitoring: {
          on: { NEXT: 'harness', BACK: '#tour.setup.backends.opencode', SKIP: 'harness' },
        },
        harness: {
          on: { NEXT: 'product', BACK: 'monitoring', SKIP: 'product' },
        },
        product: {
          on: { NEXT: '#tour.complete', BACK: 'harness', SKIP: '#tour.complete' },
        },
      },
    },
    complete: { type: 'final' },
  },
})
```

### Context shape

```ts
type TourContext = {
  // Populated by 01-02's prefetch step. Empty in 01-01.
  completed: Record<StepId, boolean>
  // Also populated in 01-02; tracks whether the user explicitly skipped this step
  // (vs. auto-skipped because guard returned true).
  skipped: Record<StepId, boolean>
  // Stored on welcome → setup transition; lets the persistence layer detect a
  // DB reset.
  instanceId: string | null
}

type StepId =
  | 'workspace'
  | 'claude' | 'codex' | 'gemini' | 'opencode'
  | 'monitoring'
  | 'harness'
  | 'product'
```

In 01-01 the context is only the type; 01-02 fills in real values.

### Event shape

```ts
type TourEvent =
  | { type: 'START' }
  | { type: 'NEXT' }
  | { type: 'BACK' }
  | { type: 'SKIP' }
  | { type: 'SKIP_TOUR' }
  // 01-02 adds: EVALUATE (re-run guards on resume), HYDRATE (load context from prefetch)
```

### Test plan

`frontend/src/tour/__tests__/machine.test.ts` — pure-functional tests:

- `forward through every step lands on complete`
- `BACK from each step returns to the previous step (and BACK from welcome stays on welcome)`
- `BACK from setup.backends.claude returns to setup.workspace, not setup`
- `BACK from setup.backends.codex returns to setup.backends.claude`
- `SKIP_TOUR from welcome jumps to complete`
- `SKIP from each step lands on the same target as NEXT`
- `cannot send NEXT from idle (no transition)`
- `cannot send NEXT from complete (final)`

No DOM, no API. Run with `vitest`.

## Files

- `backend/app_litestar/routes/health.py` — add `setup_status` handler
- `backend/tests/test_litestar_health.py` — add 4 setup-status tests
- `frontend/src/tour/machine.ts` — new
- `frontend/src/tour/__tests__/machine.test.ts` — new

## Estimated size

~250 lines new code, ~150 lines new tests. ~30 minutes of focused work.
