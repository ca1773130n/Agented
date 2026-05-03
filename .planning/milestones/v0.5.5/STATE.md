# v0.5.5 State

Status: **COMPLETE** — ready for tag/release.

## Shipped

### 8 chat components restored from `b2ee00d~1`

| Component | LoC | Drift fix |
|-----------|-----|-----------|
| `MessageBubble.vue` | 162 | imports OK after shim |
| `MessageActions.vue` | 170 | imports OK after shim |
| `ProcessGroup.vue` | 226 | none |
| `CompoundSynthesis.vue` | 103 | imports OK after shim |
| `AllModeResponse.vue` | 262 | imports OK after shim |
| `ChatModeSelector.vue` | 62 | imports OK after shim |
| `AiChatSelector.vue` | 269 | imports OK after shim |
| `AiChatPanel.vue` | 808 + 22-line opt-prop adaptation = 830 | state props made optional with empty defaults so two stripped-down "smart-chat fallback" callers (AIBackendsPage, SuperAgentPlayground) keep working |

Total restored: **2055 LoC** of better implementation that the
b2ee00d migration push had deleted in error.

### v0.5.4 translation wrapper deleted

- `frontend/src/components/ai/AiChatPanel.vue`: replaced (266 lines
  v0.5.4 wrapper → 830 lines restored implementation, +564 net)
- `frontend/src/components/ai/__tests__/AiChatPanel.test.ts`:
  deleted (480 lines wrapper test set)
- New `frontend/src/components/ai/__tests__/AiChatPanel.smoke.test.ts`:
  11 call-site smoke tests against the restored panel (replaces
  the 31 v0.5.4 wrapper tests; smoke parity, not behavior parity)

### Type re-export shims for restored components

- `frontend/src/composables/useAllMode.ts`: re-exports `ChatMode`,
  `BackendResponse`, `SynthesisState` from `@ai-accounts/ts-core` so
  restored components keep their legacy import path without
  recreating the deleted 462-line `useAllMode` composable.
- `frontend/src/composables/useProcessGroups.ts`: re-exports
  `useProcessGroups`, `ProcessGroup` from `@ai-accounts/vue-headless`
  + inline-defines `ProcessGroupType` discriminator.

### Test stub updated

- `frontend/src/test/setup.ts` — AiChatPanel global stub prop list
  expanded for the restored 808-line surface (adds `processGroups`,
  `backendResponses`, `synthesisState`, `isAllModeActive`, plus
  legacy "smart-chat fallback" pass-throughs).

### Audit

- `.planning/milestones/v0.5.5/RECON.md`: Phase 0 viability decision
  (GO with low drift)
- `.planning/milestones/v0.5.5/AUDIT.md`: per-component classification
  + 8-PR upstream plan

## Verification

| Gate | Result |
|------|--------|
| `cd frontend && npm run test:run` | **1080 passed** (was 1100; -31 wrapper tests deleted with v0.5.4 wrapper, +11 new smoke tests) |
| `cd frontend && npm run test:coverage` | passes; useTourMachine ≥ 90% threshold holds |
| `cd backend && uv run pytest` | 2196 passed (unchanged) |
| `just build` | vue-tsc + vite clean |

## Deferred to v0.5.6

**8 upstream PRs against `~/Developer/Projects/ai-accounts`.** Per
audit doc, each restored component (with one exception — AiChatPanel
orchestrator extraction) is project-independent and should upgrade
its upstream `vue-styled` counterpart. PR dispatch is a focused
cross-repo effort; v0.5.6 milestone owns it.

Order:
1. ChatBubble (upgrade from MessageBubble)
2. ProcessGroup (upgrade from Agented design)
3. MessageActions (upgrade from Agented design)
4. CompoundSynthesis (upgrade from Agented design)
5. AllModeResponses (upgrade from Agented AllModeResponse)
6. ChatModeSelector (new component or ChatControls extension)
7. AiChatSelector (new component)
8. AiChatPanel orchestrator (presentational extraction; opinionated)

Each PR includes code + tests + ai-accounts CI green.

## Deferred to v0.5.7+ (Path Y)

Per-call-site migration of the 11 chat-bearing pages to consume the
upgraded ai-accounts components directly (once v0.5.6 PRs release).
Wrapper file becomes deletable as call sites migrate.

## Next milestone

**v0.5.6 = upstream PR dispatch.** Focused cross-repo effort, no
local Agented changes. Each PR is its own dedicated work; can be
parallelized across sessions. v0.5.7+ then consumes the released
upstream and starts deleting Agented's local copies as redundant.
