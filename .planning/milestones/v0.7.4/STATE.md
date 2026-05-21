# v0.7.4 State

Status: COMPLETE — shipped 2026-05-09.

## Shipped

Split 860-line frontend/src/router/routes/misc.ts (123 routes) into
15 domain-scoped route modules to match the existing per-domain
pattern (agents.ts, dashboard.ts, etc.). misc.ts is now a 30-line
residual catch-all for redirects + 2 stragglers.

## Key files touched

- `frontend/src/router/index.ts`
- `frontend/src/router/routes/agentsExt.ts`
- `frontend/src/router/routes/aiBackends.ts`
- `frontend/src/router/routes/auth.ts`
- `frontend/src/router/routes/bots.ts`
- `frontend/src/router/routes/codeBlocks.ts`

## Reference

- Commit: `2d840c30`
