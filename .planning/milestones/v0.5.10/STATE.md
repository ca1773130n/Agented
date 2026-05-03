# v0.5.10 State

Status: **COMPLETE** — ready for tag/release.

## Shipped

### Backend
- New SSE route: `GET /admin/traces/:id/stream` (polling-loop variant)
  on `tracing_router` in `app_litestar/routes/agents_and_tracing.py`
- 3 new pytest tests in `class TestStreamTrace` (happy / not-found /
  already-completed)

### Frontend
- `frontend/src/services/api/tracing.ts` — typed REST + SSE client.
  Augmented existing wave-60 file: added `list` / `get` / `stats` /
  `stream` methods + `Trace`, `TraceSpan`, `TraceWithSpans`,
  `TraceStats`, `ListTracesParams`, `ListTracesResponse` types.
  Widened `entity_type` / `status` / `span_type` from strict literal
  unions to `... | string` to accept arbitrary backend values.
- `frontend/src/composables/useTraceStream.ts` — reactive SSE consumer
  exposing `events`, `status`, `start()`, `stop()`. Auto-stops on
  `trace_ended`; tolerates non-JSON frames; closes on unmount.
- `frontend/src/components/tracing/SpanTreeNode.vue` — recursive
  collapsible tree node. `defineOptions({ name: 'SpanTreeNode' })`
  for self-recursion.
- `frontend/src/components/tracing/TraceListItem.vue` — list row with
  status badge, duration, entity ref, navigates via RouterLink.
- `frontend/src/views/TracesPage.vue` — list page with filter bar
  (status, entity type, search), pagination (offset/limit 100),
  aggregate stats header.
- `frontend/src/views/TraceDetailPage.vue` — header + recursive span
  tree built from `parent_span_id`; opens SSE only when trace status
  is `running`; patches tree on each event.
- `frontend/src/router/routes/observability.ts` — `/traces` list +
  `/traces/:id` detail routes; named-export pattern matching
  existing aggregator convention.

## Drift from plan (handled inline by implementing subagent)

1. Router variable name: plan said `trace_router`; actual was
   `tracing_router`.
2. `tracing.ts` already existed (wave-60) with different method
   names — augmented additively rather than created.
3. SpanTreeNode `findAllComponents` test expectation: VTU 2.4.6
   excludes the mounted root, so parent+1 child = 1 nested
   component. Test reflects the correct count + has a comment.
4. TraceListItem click test used a real RouterLink stub with
   `app.use(router)`-equivalent global registration to make
   `<RouterLink>` resolve.
5. Router aggregator pattern was named-export (e.g.,
   `observabilityRoutes`), not default-export — matched existing.
6. `type Readonly` import from `vue` removed (Vue doesn't export
   that name; the global TS utility is in scope via `lib`).
7. TracesPage `computed` import consolidated into the top `vue`
   import line.

## Verification

| Gate | Result |
|------|--------|
| `cd frontend && npm run test:run` | **1089 passed** (was 1069; +20) |
| `cd frontend && npm run test:coverage` | passes; useTourMachine ≥ 90% threshold holds |
| `cd backend && uv run pytest` | **2199 passed** (was 2196; +3) |
| `just build` | vue-tsc + vite clean |

## Deferred

- **Server-side full-text search across span content** → v0.5.11
- **Per-entity tabs on `/agents/:id`** → additive cross-link, post-v0.5.10
- **Trace deletion UI** → operator cleanup tool, not observability surface
- **Waterfall timeline** → v0.5.10.x or later

## Next milestone

**v0.5.11 — agent_memory observability.** Threads + Working Memory +
FTS5 search. Same standalone-list-then-detail pattern as v0.5.10
(template reuse). After v0.5.11, the C piece of E is done; v0.5.12
moves to A (auth depth) per the original sequencing.
