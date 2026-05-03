# v0.5.3 State

Patch release closing the remaining silent-failure audit findings and
the modal-interaction E2E carried over from v0.5.0.

**Status:** COMPLETE — ready for tag/release.

## Shipped

### Silent-failure cleanup (audit second pass)

- `leaf_crud_f.py:get_memory_config` (#6, HIGH) — log + return defaults
- `leaf_crud_f.py:update_memory_config` (#7, HIGH) — log + drop corrupt
- `tracing.py:end_trace` `started_at` parse (#9, MEDIUM) — try/except + log + null duration
- `tracing.py:end_span` `started_at` parse (#10, MEDIUM) — identical fix

### Modal-interaction E2E (OB-44 / OB-47, v0.5.0 carryover)

The carryover I had originally deferred for "fixture engineering"
turned out to need none of that. AccountWizard exposes
`data-tour="account-wizard"` and the existing tour fixture already
mocks the relevant backend endpoints. New E2E in
`tour-flow.spec.ts` opens the wizard mid-tour and asserts (a) it
renders, (b) its close button is pointer-event-clickable, and (c)
either `tour-spotlight--reduced` or `tour-dim-fallback.modal-open`
appears — proving the `modalOpenDuringTour` provide/inject path.

## Audit findings now fully closed

After v0.5.2 + v0.5.3, the audit has the following status:

| # | Severity | Status |
|---|----------|--------|
| 1 | CRITICAL (text) → fixed | v0.5.2 |
| 2 | CRITICAL (text) → already had log | regression test in v0.5.2 |
| 3 | CRITICAL | v0.5.2 |
| 4 | CRITICAL | v0.5.2 |
| 5 | HIGH | already wrapped (predates audit), no work needed |
| 6 | HIGH | v0.5.3 |
| 7 | HIGH | v0.5.3 |
| 8 | HIGH | v0.5.2 |
| 9 | MEDIUM | v0.5.3 |
| 10 | MEDIUM | v0.5.3 |
| 11 | MEDIUM | stale — Litestar `Exception` handler covers |
| 12 | MEDIUM | stale — same as #11 |
| 13 | MEDIUM | semantic, out of scope |
| 14 | LOW | semantic, out of scope |

## Verification

- `cd backend && uv run pytest` — **2196 passed** (+4 over v0.5.2)
- `cd frontend && npm run test:run` — 1069 passed (unchanged)
- `cd frontend && npm run build` — vue-tsc + vite clean
- `npx playwright test --list` — 7 tour E2E tests (was 6)
