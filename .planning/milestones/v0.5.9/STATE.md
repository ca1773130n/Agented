# v0.5.9 State

Status: **COMPLETE** — ready for tag/release.

**Path Y is done.** All 11 chat-bearing pages consume `@ai-accounts/vue-styled` directly.

## Shipped

### Last 2 path-Y migrations

| Page | Upstream component | Pattern |
|------|--------------------|---------|
| `AIBackendsPage.vue` | `AiChatPanel` (self-managed) | smart-chat fallback |
| `SuperAgentPlayground.vue` | `AiChatPanel` (self-managed) | smart-chat fallback |

Both pages pass only the small self-managed prop set (`density / welcomeTitle / placeholder / entityLabel`); they don't drive their own state. Upstream's self-managed `AiChatPanel` handles the LLM chat internally via `useSmartChat`. Per-page design call resolved cleanly.

### Cleanup tail — ~2080 LoC deleted

| File | Lines |
|------|-------|
| `frontend/src/components/ai/AiChatPanel.vue` | 830 |
| `frontend/src/components/ai/AiChatSelector.vue` | 269 |
| `frontend/src/components/ai/AllModeResponse.vue` | 262 |
| `frontend/src/components/ai/ChatModeSelector.vue` | 62 |
| `frontend/src/components/ai/CompoundSynthesis.vue` | 103 |
| `frontend/src/components/ai/MessageActions.vue` | 170 |
| `frontend/src/components/ai/MessageBubble.vue` | 162 |
| `frontend/src/components/ai/ProcessGroup.vue` | 226 |
| `frontend/src/components/ai/__tests__/AiChatPanel.smoke.test.ts` | ~250 |
| `frontend/src/composables/useAllMode.ts` | ~10 (shim) |
| `frontend/src/composables/useProcessGroups.ts` | ~8 (shim) |

Agented now consumes the chat layer as a library user — it doesn't maintain a local copy. The roundtrip is complete: Agented's better implementation went up to ai-accounts (v0.5.6 PRs #7-#13 + v0.5.7 PR #14), then Agented adopted those upgraded upstream components and deleted its locals.

## Test stub adjustment

`frontend/src/test/setup.ts` registers the same stub under both `AiChatPanel` (upstream self-managed) and `AiChatPanelManaged` (upstream caller-managed). Both keys point at the same shared stub object. The prop list is the union of both upstream surfaces.

## Verification

| Gate | Result |
|------|--------|
| `cd frontend && npm run test:run` | **1069 passed** (was 1080; -11 from the deleted v0.5.5 smoke test for the now-removed local AiChatPanel; zero failures) |
| `cd frontend && npm run test:coverage` | passes; useTourMachine ≥ 90% threshold holds |
| `cd backend && uv run pytest` | 2196 passed (unchanged) |
| `just build` | vue-tsc + vite clean |

## Path Y journey — closed

| Milestone | What shipped |
|-----------|--------------|
| v0.5.4 | Translation wrapper restoring broken integration |
| v0.5.5 | Restored 8 components from b2ee00d~1; deleted v0.5.4 wrapper |
| v0.5.6 | 7 upstream PRs back-migrating components → ai-accounts 0.3.10 |
| v0.5.7 | PR-8 (AiChatPanelManaged) → 0.3.11; first path-Y cluster (4 wizards) |
| v0.5.8 | Path-Y second cluster (5 more wizards) |
| **v0.5.9** | Path-Y last 2 (smart-chat fallback) + cleanup tail |

Total Agented LoC delta across the journey: net **~+0** (restored ~2080, deleted ~2080 in v0.5.9). Upstream `~/Developer/Projects/ai-accounts` gained the better implementation as merged PRs.

## Next: E (production hardening)

The Agented↔ai-accounts chat surface has converged. The original B → D → E sequencing put production hardening at the end. v0.5.10+ owns it.

Suggested E scope:
- Auth depth (RBAC roles, session lifecycle, OAuth refresh)
- Deploy story (production gunicorn config, env var hygiene, secrets management)
- Operator-facing observability for `agent_memory` + `tracing` tables (UI surfaces for the data the silent-failure-cleanup milestones already collect)
- Rate limiting / abuse mitigation review
- Backup / restore runbook

That's a real milestone-scale conversation. Worth its own brainstorming pass when you're ready.
