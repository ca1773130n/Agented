# Multi-Wave Tracks — Brainstorm

> Plan for executing the 4 deferred multi-week initiatives as multi-wave campaigns in this session, modeled on waves 1–12 already shipped.

**Total session-bounded waves: 13** (waves 13–25)

**Execution order (lowest risk first → highest):**
1. **Track C (TourOverlay redesign)** — most bounded, completable in session.
2. **Track D (Sidebar a11y/responsive)** — small, independent, completable.
3. **Track B (Multi-user schema)** — schema rev only; auth flow deferred.
4. **Track A (Flask → Litestar)** — foundation + 1 route only; bulk migration deferred.

Each wave preserves: red test → impl → green → commit. No half-finished implementations.

---

## Track C — TourOverlay redesign (waves 13–16)

### Goal
Replace `TourOverlay`'s `targetEl: Element | null` holding pattern with an event-driven "show on selector X" architecture, so the overlay survives DOM remounts (route changes, slot re-renders, async content) without losing its anchor.

### Why
The current pattern fails when a route param change (`/backends/claude` → `/backends/codex`) unmounts the target element for a frame. Wave 6's EntityLayout `keepStale` was a workaround. Real fix: the overlay should resolve the selector on every frame, not cache a `ref<Element>`.

### Wave 13 — TourTargetBus + selector resolver
- **Files:** new `src/composables/useTourTargetBus.ts`, new `src/composables/__tests__/useTourTargetBus.test.ts`
- **Scope:** Build the bus that emits `{ selector, options }` events. Build a `resolveSelector(selector)` helper that uses `MutationObserver` to find elements as they're added/removed.
- **TDD:** 6 cases — bus subscribe/emit, resolver finds existing element, resolver waits for late-mounted element, resolver re-emits on remount, resolver cleans up MO on unsubscribe, multi-subscriber fanout.
- **Verification:** `npm run test:run -- src/composables/__tests__/useTourTargetBus`

### Wave 14 — Rewrite TourOverlay to consume the bus
- **Files:** `src/components/tour/TourOverlay.vue`, `src/components/tour/__tests__/TourOverlay.test.ts`
- **Scope:** Drop `targetEl` prop. Take `selector: string` instead. Subscribe to bus on mount, render highlight box from current resolved element. On route change, the resolver re-fires automatically — no parent-side re-mount logic needed.
- **TDD:** Update existing TourOverlay test cases (32 tests). Fix the pre-existing OB-40 retry/spinner failure as a side benefit (the new architecture makes that case trivial: subscribe → wait → render).
- **Verification:** `npm run test:run -- src/components/tour/__tests__/TourOverlay.test.ts` — all 32 green.

### Wave 15 — Migrate consumers
- **Files:** `src/App.vue`, `src/composables/useTourMachine.ts`, all `data-tour="…"` selectors in views.
- **Scope:** App.vue stops looking up elements with `document.querySelector` and `targetEl` — instead emits `{ selector: '[data-tour="add-account-btn"]' }` to the bus when the tour reaches that step. useTourMachine wires step → selector mapping.
- **Verification:** Manual smoke against the existing tour-flow.spec.ts e2e suite (171 lines covering full tour walk).

### Wave 16 — Delete dead code + add bus tests
- **Files:** Delete `targetEl` ref-holding patterns in App.vue, useTourMachine.ts. Add `src/composables/__tests__/tour-route-change.test.ts` — locks in the "tour overlay survives route param change" regression test.
- **Verification:** `just build` clean; full frontend test suite green; e2e tour-flow.spec.ts passes.

### Stopping point
**Ships:** Full event-driven overlay, all consumers migrated, dead code removed, regression test in place.
**Does not ship:** Visual polish on highlight box, focus-trap behavior changes (those are separate aesthetic decisions).

### Risks
- **Bus event ordering** under fast route changes — mitigation: idempotent re-render + `MutationObserver` debouncing.
- **OB-40 pre-existing failure** — mitigation: explicitly include in Wave 14's scope, don't paper over.

---

## Track D — Sidebar a11y/responsive (waves 17–18)

### Goal
Bounded technical fixes only — keyboard navigation, ARIA semantics, responsive breakpoints. **Defer aesthetic redesign** because it requires designer input.

### Wave 17 — Sidebar a11y
- **Files:** `src/components/Sidebar.vue` (or wherever main nav lives), test file.
- **Scope:** Add `role="navigation"`, `aria-label="Main navigation"`. Wire `aria-current="page"` on active route. Make collapse toggle a real `<button>` with `aria-expanded` + `aria-controls`. Keyboard nav: Tab moves through items, Enter activates, Esc collapses.
- **TDD:** 4–5 component tests covering the a11y attributes and keyboard handlers.
- **Verification:** `npm run test:run -- <sidebar test>`

### Wave 18 — Sidebar responsive
- **Files:** `src/components/Sidebar.vue` CSS.
- **Scope:** Single breakpoint at 768px → auto-collapse to icon-only. Below 480px → hidden behind a toggle. No layout-shift bugs (tested via the existing `useSidebarCollapse` composable).
- **TDD:** Add 2 cases to `useSidebarCollapse.test.ts` covering breakpoint transitions.
- **Verification:** `just build` clean; manual eyeball at 1024 / 768 / 480 / 320 px widths.

### Stopping point
**Ships:** Real a11y + responsive that actually works.
**Does not ship:** Aesthetic redesign, icon set change, color rebrand, layout reorganization.

### Risks
- **Existing keyboard handlers** — mitigation: read existing `useSidebarCollapse` first, don't fight it.

---

## Track B — Multi-user schema (waves 19–21)

### Goal
Establish the schema foundation for multi-user mode: a `users` table, FK from `user_roles.user_id`, and a `current_user` mechanism. **Auth flow + UI deferred** to a follow-up milestone.

### Wave 19 — `users` table migration
- **Files:** `backend/app/db/migrations.py` (new migration), `backend/app/db/users.py` (new module with CRUD), `backend/tests/test_users_db.py` (new).
- **Scope:** Migration adds `users (id TEXT PRIMARY KEY, email TEXT UNIQUE, display_name TEXT, created_at, updated_at, is_active BOOLEAN)`. CRUD: `create_user`, `get_user`, `get_user_by_email`, `list_users`, `update_user`, `deactivate_user`.
- **TDD:** 8 tests covering CRUD + email uniqueness + soft deactivate.
- **Verification:** `cd backend && uv run pytest tests/test_users_db.py -v`

### Wave 20 — `user_roles.user_id` FK + backfill
- **Files:** `backend/app/db/migrations.py` (next migration), `backend/app/db/rbac.py`, `backend/tests/test_rbac.py`.
- **Scope:** Add `user_id TEXT REFERENCES users(id)` column. Migration creates a synthetic "legacy" user and assigns all existing role rows to it (preserves single-user mode behavior). New `create_user_role` accepts optional `user_id`. `get_role_for_api_key` returns `(role, user_id)` instead of just `role`.
- **TDD:** Update existing rbac tests + add 4 new ones for user_id propagation.
- **Verification:** `cd backend && uv run pytest tests/test_rbac.py -v` — all green.

### Wave 21 — `current_user` request context
- **Files:** `backend/app/middleware.py`, `backend/app/services/rbac_service.py`, `backend/tests/test_request_id.py` (extend).
- **Scope:** Add `current_user_var: ContextVar[str | None]` parallel to `request_id_var`. Middleware sets it from `get_role_for_api_key` lookup. Logging filter includes `user_id` in JSON output. `require_role` decorator can now expose `current_user_id`.
- **TDD:** 5 tests covering var propagation through requests + log line includes user_id.
- **Verification:** `cd backend && uv run pytest tests/test_request_id.py tests/test_rbac.py -v`

### Stopping point
**Ships:** Schema rev + FK + ContextVar plumbing. The system runs in single-user mode by default (legacy user) but is now ready for the next phase.
**Does not ship:** Login UI, signup flow, password storage, session tokens, multi-tenant data isolation in routes (each route still queries without user filter — that's the next milestone).

### Risks
- **Migration ordering** — mitigation: idempotent migrations with `IF NOT EXISTS` guards (existing convention).
- **Backwards compat** — mitigation: legacy user FK ensures no existing API caller breaks.
- **Per-route data filtering** is a separate huge undertaking — explicitly out of scope.

---

## Track A — Flask → Litestar foundation (waves 22–25)

### Goal
Establish the Litestar collapse foundation inside `backend/`: a Litestar app skeleton mounted alongside Flask, the auth dependency wired, and **3 routes** migrated as the proof-of-pattern. **77 routes deferred** to the milestone after this session.

### Why "deferred"
80 routes × (route impl + Pydantic schema audit + test rewrite) = 16+ hours of mechanical work even with the pattern locked. Trying to do it all in this session would produce a half-migrated repo with two parallel auth systems. Lock the pattern, migrate a sample, document the rest.

### Wave 22 — Litestar app skeleton
- **Files:** `backend/app_litestar/__init__.py` (new), `backend/app_litestar/auth.py` (new), `backend/tests/test_litestar_skeleton.py` (new), `backend/scripts/run_litestar.py` (new).
- **Scope:** Create a Litestar `Litestar()` app that shares `agented.db` access through a startup hook. Auth `dependency` that reuses `get_role_for_api_key` from `app/db/rbac.py`. Run on a separate port (20002) for now — collapse onto :20000 happens in the eventual completion milestone.
- **TDD:** 4 tests — health route returns 200, auth dependency rejects missing key, auth accepts valid key, auth threading is async-safe.
- **Verification:** `cd backend && uv run pytest tests/test_litestar_skeleton.py -v`

### Wave 23 — Migrate `GET /admin/rbac/permissions` (read-only)
- **Files:** `backend/app_litestar/routes/rbac.py` (new), `backend/tests/test_litestar_rbac.py` (new).
- **Scope:** Pick the simplest read-only Flask route (`/admin/rbac/permissions` returns the permission matrix). Re-implement as Litestar handler with msgspec Struct (Litestar's native, no Pydantic dep). Both apps now serve the route — verify both return identical JSON.
- **TDD:** 3 tests — Litestar version returns identical body to Flask version, requires admin, returns matrix.
- **Verification:** Both pytest suites pass; manual `curl` shows byte-identical responses.

### Wave 24 — Migrate `POST /admin/rbac/roles/{id}/rotate` (write)
- **Files:** `backend/app_litestar/routes/rbac.py`, `backend/tests/test_litestar_rbac.py`.
- **Scope:** Migrate the Wave 8 rotate endpoint. Validates the write-path pattern (DB transaction, response shape, error 404/403 mapping).
- **TDD:** Re-run the 3 existing rotate tests against the Litestar route.
- **Verification:** Side-by-side response check against Flask.

### Wave 25 — Document migration playbook + retire 1 Flask route
- **Files:** `docs/superpowers/specs/2026-05-01-flask-litestar-migration.md` (new playbook), `backend/app/routes/rbac.py` (delete the 2 migrated routes), `frontend/vite.config.ts` (add :20002 proxy for `/litestar/*` prefix during transition).
- **Scope:** Playbook covers: Pydantic→msgspec conversion, `flask-openapi3` decorator → Litestar `@get`/`@post` mapping, error response shape preservation, test migration. Retire the two routes from Flask so we have one source of truth — at this point /admin/rbac/permissions and /admin/rbac/roles/{id}/rotate are Litestar-only.
- **Verification:** `just build` clean; backend test suite green; frontend e2e tests confirm rotate still works.

### Stopping point
**Ships:** Litestar skeleton + auth + 2 routes + playbook + retirement of 2 Flask routes.
**Does not ship:** Migration of the other ~78 routes. They keep working unchanged.

### Risks
- **Two-port confusion in dev** — mitigation: vite.config.ts proxies `/litestar/*` to :20002 so frontend code uses one origin.
- **Auth dependency divergence** — mitigation: both apps import `get_role_for_api_key` from the same module.
- **Playbook bitrot** — mitigation: write the playbook AS we migrate (not after); test it against the second route migration.

---

## Cumulative session map

| Track | Waves | Net effect |
|-------|-------|------------|
| C — TourOverlay | 13–16 | Full redesign + consumer migration shipped |
| D — Sidebar | 17–18 | a11y + responsive shipped; aesthetic deferred |
| B — Multi-user | 19–21 | Schema + ContextVar shipped; auth/UI deferred |
| A — Litestar | 22–25 | Skeleton + 2 routes + playbook shipped; ~78 routes deferred |

**Total: 13 waves (waves 13–25)**

## What this session honestly produces

- 4 measurable foundations laid (one per track).
- Track C goes end-to-end (no deferral).
- Track D ships the testable parts (no deferral within bounded scope).
- Tracks A and B ship the foundation + a worked example each — explicitly NOT a complete migration, but the pattern + tests are locked so a follow-up session can mechanically continue.

## What this session does NOT produce

- Multi-user login flow / signup UI (Track B).
- Per-route data isolation (Track B).
- 78 remaining route migrations (Track A).
- Sidebar aesthetic redesign (Track D).

These four items remain genuine multi-week milestones after this session — but with the foundations in place, each becomes mechanical work with no architectural unknowns.
