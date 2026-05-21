# v0.7.96 State

Status: COMPLETE — shipped PR #143 (2026-05-20).

## Shipped

``useTourMachine.test.ts > prefetchTourRoutes (OB-42) > settles
without throwing`` was timing out under the full suite at ~5027ms
(default 5s per-test cap). Standalone the test ran in ~2.2s —
the difference was Vite's transform pipeline being saturated by
parallel workers during the full suite run.

## Key files touched

- `frontend/src/composables/__tests__/useTourMachine.test.ts`

## Reference

- PR: #143
- Commit: `c32095a3`
