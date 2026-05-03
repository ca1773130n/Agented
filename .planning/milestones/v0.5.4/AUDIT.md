# v0.5.4 back-migration audit (2026-05-03)

Per spec, audit Agented's chat/account-adjacent code for project-
independent logic that should be upstreamed to ai-accounts. Criterion:
*if it doesn't reference Agented domain types (Bot, Agent, Sketch,
Project, Trigger, Conversation entities, Litestar route paths, Vite
proxy paths, Geist theme tokens), it's a back-migration candidate.*

## Findings

| File | LoC | Classification | Action |
|------|-----|---------------|--------|
| `frontend/src/components/ai/AiChatPanel.vue` | ~250 | **Agented-specific (bridge layer)** | Keep. The wrapper is the legacy 837-line consumer API ↔ vue-styled subcomponent bridge — project-specific by design. Deletable in path Y once each call site migrates to use `BaseAiChatPanel` directly. |
| `frontend/src/composables/useAiChat.ts` | ~25 | **Pure re-export** | Keep for now. Deletable in path Y when call sites switch to direct imports from `@ai-accounts/vue-headless` and `@ai-accounts/ts-core`. |
| `frontend/src/composables/useConversation.ts` | 354 | **Mixed (extractable core, big extraction)** | Keep in v0.5.4. Has a generic core (SSE chunk-merging via `safeParseSSE` + `useEventSource`, conversation lifecycle state machine) wrapped around an Agented-specific API contract (`ConversationMessage` from Agented's api types, `start`/`sendMessage`/`finalize`/`abandon`/`list`/`resume` against Agented's `/admin/agents/*/conversations` routes). Extracting a `useConversationStateMachine<TApi>` upstream is genuinely useful but is a non-trivial design pass — out of scope for a patch milestone. **Capture as v0.6.0+ candidate.** |
| `frontend/src/composables/useConversationBranch.ts` | 119 | **Agented-specific** | Keep. Branch navigator depends on Agented's `branchApi` (`getBranches`, `getBranchTree`, `createBranch`). Triggers/branch navigation isn't a concept ai-accounts owns. |

## Upstream PRs opened from this audit

**None.**

The wrapper rebuild itself produced no project-independent code — by
construction it's the bridge that adapts the legacy Agented API to
the upstream subcomponent surface. The other audit candidates either
have no extractable surface in v0.5.4 scope (`useConversation` is a
v0.6.0+ design pass) or are Agented-specific by domain
(`useConversationBranch`).

## Deferred

- **v0.6.0+ candidate:** Extract a generic
  `useConversationStateMachine<TApi>` from `useConversation.ts` and
  upstream to `@ai-accounts/vue-headless`. The extraction needs:
  - A `TApi` type parameter for the conversation client surface
    (`start` / `sendMessage` / `finalize` / `abandon` / `list` /
    `resume` / `stream`)
  - Generic message/streaming-content state independent of Agented's
    `ConversationMessage` shape
  - Identification of which Agented-specific pieces stay in
    `useConversation` (toast, error normalization, entity-coupled
    state)
- **Path Y track (v0.5.5+):** Per-page migration to `BaseAiChatPanel`
  smart-chat-managed state. Once enough call sites migrate, this
  audit's "deletable in path Y" candidates (`AiChatPanel.vue` wrapper
  and `useAiChat.ts` re-exports) actually get deleted.

## Conclusion

v0.5.4 ships path Z (translation wrapper) cleanly with no upstream
PRs from this audit pass. The audit's value is the *catalog of what
to revisit in path Y*: the bridge can shrink as call sites learn the
upstream API.
