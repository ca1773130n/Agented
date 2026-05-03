# v0.5.11 State

Status: **COMPLETE** — ready for tag/release.

## Shipped

### Frontend
- `services/api/agentMemory.ts` — typed REST client (4 endpoints + 7 types).
  Coexists with the pre-existing `services/api/agent-memory.ts` (hyphen)
  which retained extra methods (`createThread`, `deleteThread`,
  `getConfig`, etc.) for the existing memory-config tests.
- `composables/useFocusRefresh.ts` — visibilitychange-driven re-fetch composable
- `components/memory/WorkingMemoryView.vue` — markdown viewer with empty/loading/error states
- `components/memory/RecallSearch.vue` — FTS5 search input + top_k selector + result rows
- `components/memory/ThreadList.vue` — paginated thread rows + `refresh()` exposed
- `components/memory/MessageList.vue` — `ChatBubble` per message via @ai-accounts/vue-styled
- `views/MemoryPage.vue` — `/agents/:id/memory` 3-region stacked page with parallel fetch + focus refresh
- `views/ThreadDetailPage.vue` — `/agents/:id/memory/threads/:thread_id` deep-linkable detail
- `router/routes/observability.ts` — extended with 2 memory routes

### Tests added
- 36 new frontend tests across composable + 4 components + 2 views

## Drift from plan (handled inline by implementing subagent)

1. **Pre-existing `agent-memory.ts` (hyphen)** — coexists with the new
   `agentMemory.ts` (camelCase). `index.ts` re-exports the canonical
   v0.5.11 surface from `./agentMemory` and keeps the legacy types
   (`MemoryConfig`, `SaveMessagesRequest`, etc.) from `./agent-memory`
   for the existing memory-config tests.
2. **RouterLink stub** — `vi.mock('vue-router', ...)` doesn't intercept
   global component resolution; tests register the stub via
   `global.components: { RouterLink: RouterLinkStub }` per-mount, same
   pattern as v0.5.10 TraceListItem fix.
3. **ChatBubble role type** — `MemoryMessage.role` is loose `string`
   but `ChatBubble` expects a strict union; inline cast in
   `MessageList.vue`.

## Verification

| Gate | Result |
|------|--------|
| `cd frontend && npm run test:run` | **1125 passed** (was 1089; +36) |
| `cd frontend && npm run test:coverage` | passes; useTourMachine ≥ 90% threshold holds |
| `cd backend && uv run pytest` | 2199 passed (unchanged) |
| `just build` | vue-tsc + vite clean |

## Deferred

- Edit / delete affordances → out of scope by design
- Cross-agent search / standalone /memory → future
- SSE live updates → focus refresh sufficient for memory
- Vector / hybrid recall → v0.5.11.x candidate
- Thread creation UI → not user-facing
- Memory config page → separate concern

## E-C piece status: COMPLETE

| Milestone | Sub-piece | Surface |
|-----------|-----------|---------|
| v0.5.10 | E-C-1 | Traces (list + detail + SSE) |
| v0.5.11 | E-C-2 | Agent memory (working / recall / threads + detail) |

## Next milestone

**v0.5.12 — A (auth depth).** RBAC roles, session lifecycle hardening,
OAuth token refresh. Different surface from observability; the
template that v0.5.10/v0.5.11 established (list-then-detail + REST
client + composable) doesn't directly transfer. Fresh brainstorming
pass when ready.

After A: B (deploy story), D (rate limiting), E (backups). Per the
original B → D → E sequencing.
