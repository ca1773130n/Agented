# v0.5.5 Phase 0 Recon Report (2026-05-03)

Scope: assess whether restoring the 8 chat components deleted in
`b2ee00d` (2026-04-14) is feasible **without** reverting backend
commit `3d69ac2` and **without** large-scale rewrites.

## Files recovered from b2ee00d~1

| Component | Source LOC | Test recovered |
|---|---:|---|
| `AiChatPanel.vue` | 808 | none |
| `AiChatSelector.vue` | 269 | none |
| `AllModeResponse.vue` | 262 | none |
| `ChatModeSelector.vue` | 62 | none |
| `CompoundSynthesis.vue` | 103 | none |
| `MessageActions.vue` | 170 | none |
| `MessageBubble.vue` | 162 | none |
| `ProcessGroup.vue` | 226 | none |

`b2ee00d~1:frontend/src/components/ai/__tests__/<name>.test.ts` is
absent for all 8. No restorable per-component test fixtures.

## useAiChat composable evolution

- **Pre-`06f6cdd`** (commit `2c765d2`): 462-line full composable —
  exported `useAiChat(superAgentId)` returning chat state +
  `useAllMode`, `useProcessGroups`, `useStreamingParser` siblings.
- **`b2ee00d~1`**: already reduced to a 14-line re-export shim
  (`06f6cdd` ran just before `b2ee00d`). The 8 deleted components
  predate `06f6cdd` and were authored against the **462-line full
  composable**, importing types like `ChatMode`, `BackendResponse`,
  `SynthesisState` from `'../../composables/useAllMode'`.
- **Current (v0.5.4, `27e5510`)**: 23-line shim that re-exports
  `useSmartChat`, `useProcessGroups`, `useStreamingParser` from
  `@ai-accounts/vue-headless` plus 0.3.8 type re-exports.

**Decision: extend (additive).** The current shim already re-exports
the runtime hooks the components need. The components import
**type-only** symbols (`ChatMode`, `BackendResponse`, `SynthesisState`,
`ProcessGroup`) from local composables — those types now live in
`@ai-accounts/ts-core` and `@ai-accounts/vue-headless` and are
already export-confirmed in their `index.d.ts`. The fix is to either
(a) add a small `composables/useAllMode.ts` re-export shim that
re-publishes those names from `@ai-accounts/ts-core`, or
(b) edit the restored components to import from `@ai-accounts/ts-core`
directly. (a) is the lower-drift path. Restoring the 462-line
composable is **not** required.

## Drift inventory (per component)

### AiChatPanel.vue (808 LOC)
- Missing imports:
  - `'../../services/api'` → must become `'../../services/api/index'`
    (the file moved to a directory; `ConversationMessage` still exists
    in `api/types/common.ts` and is re-exported from the index).
  - `'../../composables/useProcessGroups'` (deleted) — type
    `ProcessGroupType` now in `@ai-accounts/ts-core` /
    `vue-headless` (`ProcessGroup` interface).
  - `'../../composables/useAllMode'` (deleted) — types `ChatMode`,
    `BackendResponse`, `SynthesisState` now in `@ai-accounts/ts-core`.
- Possibly-missing endpoints: 0 (no fetch URLs in template/script).
- Type-drift hot spots: ~3 import-source rewrites; the
  `ProcessGroup` re-export type field-set (`type`, `isExpanded`)
  matches.
- Deleted-helper stubs needed: 0 if we add `useAllMode` re-export
  shim; else 3 import edits inside this file.
- **Effort: medium** (largest file; 5 child component imports must
  also resolve once those are restored).

### AiChatSelector.vue (269 LOC)
- Missing imports: `listGroupedBackends` and `AIBackend` — both still
  exported by current `services/api/index.ts` (line 24-29 of
  `frontend/src/services/api/index.ts`); just need `'../../services/api'`
  → `'../../services/api/index'`. `ChatMode` from `useAllMode` →
  `@ai-accounts/ts-core`.
- Possibly-missing endpoints: 0 (uses helper, not raw URL).
- Type-drift: trivial (1 import path, 1 type source swap).
- Deleted-helper stubs: 0 (covered by `useAllMode` re-shim).
- **Effort: small.**

### AllModeResponse.vue (262 LOC)
- Missing imports: `BackendResponse`, `SynthesisState` from
  `useAllMode` → ts-core; `renderMarkdown` from
  `'../../composables/useMarkdown'` (still EXISTS, OK).
- Possibly-missing endpoints: 0.
- Type-drift: 1 import source swap.
- Deleted-helper stubs: 0.
- **Effort: small.**

### ChatModeSelector.vue (62 LOC)
- Missing imports: `ChatMode` from `useAllMode` → ts-core.
- Possibly-missing endpoints: 0.
- Type-drift: trivial (1 swap).
- **Effort: trivial.**

### CompoundSynthesis.vue (103 LOC)
- Missing imports: `SynthesisState` from `useAllMode` → ts-core;
  `renderMarkdown` from `useMarkdown` (EXISTS, OK).
- Possibly-missing endpoints: 0.
- **Effort: trivial.**

### MessageActions.vue (170 LOC)
- Missing imports: `ConversationMessage` from
  `'../../services/api'` → `'../../services/api/index'` (still
  re-exported).
- Possibly-missing endpoints: 0.
- **Effort: trivial.**

### MessageBubble.vue (162 LOC)
- Missing imports: `renderMarkdown`, `attachCodeCopyHandlers` from
  `useMarkdown` (both EXIST and are exported, OK).
- Possibly-missing endpoints: 0.
- **Effort: trivial.**

### ProcessGroup.vue (226 LOC)
- Missing imports: only `vue` runtime (no local imports).
- Possibly-missing endpoints: 0.
- **Effort: trivial.**

**Total cross-component import fixes**: ~10 import-source rewrites
(well below the 30-fix-per-component NO-GO threshold; total fits in
one shim file plus path adjustments inside `AiChatPanel.vue`).

## Backend endpoint impact

| Endpoint | Status | Notes |
|---|---|---|
| (none in restored .vue files) | n/a | All HTTP calls go through `services/api` helpers, not URL literals |

`grep -hE "['\"]/(api|admin|api/v1|health)/"` over all 8 restored
files returns **zero matches**. The components are presentational +
event-driven; the original 462-line `useAiChat` composable owned the
fetch/SSE logic.

`3d69ac2` removed `backend/app/services/all_mode_service.py` and the
`mode='all'/'compound'` dispatch branch in `super_agent_chat.py`.
None of the restored components call those endpoints directly. The
462-line `useAiChat` did — but **we are not restoring that
composable**; we route all-mode/compound via `useSmartChat` from
`@ai-accounts/vue-headless`, which posts to the sidecar at `:20001`,
exactly per `3d69ac2`'s migration intent.

**No backend revert is required.** The deletion in `3d69ac2` is
orthogonal to this restoration.

## Upstream PR scope preview

| Restored | Upstream pair (vue-styled) | Notes |
|---|---|---|
| `AiChatPanel` (808) | `AiChatPanel.vue` (upstream) | Both are panel composers; the Agented restored version is caller-managed (messages/streaming as props); upstream vue-styled is `useSmartChat`-driven. **Large** behavioural diff; upstream PR will be a feature backport (caller-managed mode + finalization banner already partly present in v0.5.4 wrapper). |
| `MessageBubble` ↔ `ChatBubble` | renamed equivalent in upstream | **Medium** — markdown render + code-copy handlers; upstream version supports streaming overlay. |
| `ChatModeSelector` ↔ `ChatControls` | `ChatControls` is broader (includes chat input). | **Small** for the mode-radio subset; upstream may already cover. |
| `MessageActions` ↔ `MessageActions` | same name | **Small/medium** — copy/regenerate/edit/delete actions. |
| `ProcessGroup` ↔ `ProcessGroup` | same name | **Small** — collapsible group UI. |
| `CompoundSynthesis` ↔ `CompoundSynthesis` | same name | **Small** — synthesis card. |
| `AllModeResponse` (singular) ↔ `AllModeResponses` (plural) | upstream is a list container; Agented's was single-row | **Small** — the upstream "Responses" list internally renders one of these per backend. |
| `AiChatSelector` ↔ **no direct equivalent** | upstream has `BackendPicker` + `ChatControls` | **Medium** — Agented's selector groups backends by kind via `listGroupedBackends`; upstream `BackendPicker` operates on flat `BackendDTO[]`. Likely the most novel upstream PR. |

vue-styled does ship all of `ChatBubble`, `ChatControls`, `MessageActions`,
`ProcessGroup`, `CompoundSynthesis`, `AllModeResponses`, `AiChatPanel`,
`FinalizationBanner` (verified in
`frontend/node_modules/@ai-accounts/vue-styled/dist/index.d.ts`).

## Viability decision

GO criteria — all met:
- No required backend endpoints are missing (zero raw URLs in the 8
  files; the all-mode/compound chat path now lives in the sidecar via
  `useSmartChat`, not in deleted backend services).
- Per-component drift is bounded: 7 of 8 are trivial/small (1-3
  import-source rewrites each); only `AiChatPanel.vue` is medium
  (~3 imports + 5 child component imports to re-resolve).
- `useAiChat` decision is straightforward: extend the existing 23-line
  shim with a `composables/useAllMode.ts` re-export shim that
  re-publishes `ChatMode`, `BackendResponse`, `SynthesisState` from
  `@ai-accounts/ts-core`, and add a tiny `useProcessGroups` type
  re-export if any restored component imports the local type
  (`ProcessGroup`) — easily covered.

NO-GO triggers — none fired:
- Restored components do not depend on endpoints removed by `3d69ac2`.
- Total import fixes ≈ 10 across 8 components — far below the 30/comp
  threshold.
- `useAiChat` change is additive; no rewrite of the v0.5.4 wrapper.

## Recommendation

**GO.** Concrete drift expectations:

1. Add `frontend/src/composables/useAllMode.ts` (≈8 lines) that
   re-exports `ChatMode`, `BackendResponse`, `SynthesisState` from
   `@ai-accounts/ts-core` and `ProcessGroup` from
   `@ai-accounts/vue-headless`. This single shim resolves the
   majority of imports across 6 of 8 components.
2. In `AiChatPanel.vue` and `AiChatSelector.vue` and
   `MessageActions.vue`, change `'../../services/api'` →
   `'../../services/api/index'` (3 edits total).
3. Keep `useMarkdown` references — file still exists; no change.
4. Keep current 23-line `useAiChat.ts` shim as-is — restored
   components don't import the runtime composable, only type-symbols.
5. Update `frontend/src/test/setup.ts` global stub to re-add the
   restored prop surface for `AiChatPanel` (test stub is currently
   wired for the 266-line v0.5.4 wrapper; restoration restores the
   837-LOC prop surface).
6. `b2ee00d` deleted these from `frontend/src/components/ai/`. The
   current dir holds `AiChatPanel.vue` (266-line wrapper) — the
   restoration plan must decide: replace it (keeps API parity with
   pre-deletion) or rename it. Phase 0 cannot decide this without the
   v0.5.5 product owner; flag as a Phase 1 input.

**No blocker for v0.5.5.** Proceed with Tasks 2-9 as planned.
Surprises:
- The pre-deletion `useAiChat` was already a 14-line shim, not the
  462-line composable. The restored components depend on the
  462-line composable's *type exports*, not its runtime — covered by
  ai-accounts type re-export.
- The current `AiChatPanel.vue` (266 lines, v0.5.4 rebuild) is **not**
  the file that was deleted — it was added afterwards as a wrapper.
  Restoration overwrites or sidelines this wrapper; that decision
  belongs to Phase 1 planning.
- All 8 components were untested at deletion time (no `__tests__/`
  fixtures recovered). Task 11's "update test stub" is the only
  test-surface work; new per-component tests would be additive.
