# v0.5.4 State

Status: **COMPLETE** — ready for tag/release.

## Shipped

### Translation wrapper (path Z)

`frontend/src/components/ai/AiChatPanel.vue` rebuilt from a 36-line
pass-through into a ~250-line translation wrapper. Accepts the legacy
837-line consumer API; drives `@ai-accounts/vue-styled` subcomponents
(`ChatBubble`, `ChatControls`, `FinalizationBanner`) and
`useSmartChat` / `useAiAccounts` internally. All 11 existing call sites
(SketchChatPage, PluginDesignPage, RuleDesignPage, WorkflowPlaygroundPage,
ProjectManagementPage, HookDesignPage, CommandDesignPage, AIBackendsPage,
SuperAgentPlayground, SkillCreateWizard, AgentCreateWizard) stay
unchanged; their props are now actually consumed instead of silently
dropped through Vue's `inheritAttrs` fallthrough.

Wrapper-owned `<textarea>` for the controlled input contract — vue-
styled's `ChatInput` is uncontrolled (only `placeholder/disabled/
isStreaming` props + a single `send(content)` emit), so the wrapper
renders its own input to honour the legacy `:input-message` prop +
`update:input-message` / `send` / `keydown` event contract.

Backend list built locally via `useAiAccounts().client.listBackends()`
+ lazy `client.listModels(backendId)` per kind, mirroring the upstream
`BaseAiChatPanel` pattern. `useSmartChat` does *not* expose
`backendOptions` (codex review caught that hallucination in an
earlier draft).

### Test coverage

- 31 wrapper-specific unit tests in
  `frontend/src/components/ai/__tests__/AiChatPanel.test.ts`
  - 20 behavior tests (mount, messages, streaming, input, send, keydown,
    backend selector, finalize banner, slots, density, readOnly,
    initStreamingParser, useSmartScroll)
  - 11 call-site smoke tests asserting the wrapper accepts every prop
    each production consumer passes without leaking
    `Extraneous non-props attribute` warnings

### Type re-exports for 0.3.8

`frontend/src/composables/useAiChat.ts` adds
`BackendAccountOption` and `CliproxyLoginStatus` re-exports from
`@ai-accounts/ts-core` for any future call site needing them.

### Pin policy

Stays on `file:` editable per CLAUDE.md convention. Sibling
`~/Developer/Projects/ai-accounts` working tree (post-0.3.8 / 0.3.9-pre
source — package `version` const reads `0.3.9`) consumed via rebuilt
`dist/`. When 0.3.9 cuts to a registry tag, that becomes the
retroactive pin target.

### Test stub

`frontend/src/test/setup.ts` — AiChatPanel stub now declares the full
v0.5.4 consumer prop surface (28 props + 8 emits) so unit tests
mounting consumer pages don't emit Vue warnings.

### Back-migration audit

`.planning/milestones/v0.5.4/AUDIT.md`. **No upstream PRs from
v0.5.4** — the wrapper is the Agented-specific bridge by design.
`useConversation.ts` flagged as a v0.6.0+ candidate for extracting a
generic `useConversationStateMachine<TApi>`.

## Verification

| Gate | Result |
|------|--------|
| `cd frontend && npm run test:run` | **1100 passed** (was 1069 → +31 wrapper tests) |
| `cd frontend && npm run test:coverage` | passes; useTourMachine ≥ 90% threshold holds |
| `cd backend && uv run pytest` | 2196 passed (unchanged) |
| `just build` | vue-tsc + vite clean |
| `npx playwright test … "modal opens during backends step"` | **deferred** — pre-existing E2E infra gap (welcome page never renders in CI; auth/sidecar wiring), unrelated to wrapper |

The E2E gap is documented but not introduced by v0.5.4. Wrapper
behavior is comprehensively unit-covered (31 tests including the 11
call-site smoke set); the deferred E2E is a separate infra
follow-up.

## Deferred

### Path Y — per-page migration to BaseAiChatPanel smart-chat-managed state

The translation wrapper is a bridge, not the long-term shape. Each
of the 11 call sites should eventually migrate to consume
`BaseAiChatPanel` directly with caller code working *with*
`useSmartChat`'s state model rather than maintaining its own. v0.5.5+
track, one or two pages per patch. The wrapper can shrink as call
sites migrate; once all 11 are done, the wrapper becomes a
deletable thin re-export and `useAiChat.ts` re-exports collapse to
direct imports.

### v0.6.0+ candidate

Extract a generic `useConversationStateMachine<TApi>` from
`useConversation.ts` and upstream to `@ai-accounts/vue-headless`.
Audit doc has the design notes.

### E2E modal-during-tour smoke

Fix Playwright config to start the ai-accounts sidecar on `:20001`
and ensure the welcome-page tour activation path is reliable in
test mode. Tracked for v0.5.5 alongside any path-Y page that touches
the modal interaction.

## Next milestone

v0.5.5: pick 1-2 path-Y candidate pages (suggested:
`SketchChatPage` + `PluginDesignPage` since they share the
`useConversation`-based state model). Design pass per page; rewrite
to call `useSmartChat` directly; delete the wrapper-translation
glue for those pages.
