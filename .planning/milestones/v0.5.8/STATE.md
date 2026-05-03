# v0.5.8 State

Status: **COMPLETE** — ready for tag/release.

## Shipped

5 more wizards migrated to `AiChatPanelManaged` from upstream:

- `SketchChatPage.vue`
- `WorkflowPlaygroundPage.vue`
- `ProjectManagementPage.vue`
- `SkillCreateWizard.vue`
- `AgentCreateWizard.vue`

Single-line `import { AiChatPanelManaged as AiChatPanel } from '@ai-accounts/vue-styled'` swap per file. Templates unchanged.

Test infrastructure adjusted:
- `frontend/src/test/setup.ts` — AiChatPanel stub factored into a shared object registered under BOTH `AiChatPanel` and `AiChatPanelManaged`. Same prop/emit/slot surface. Once cleanup-tail removes Agented's local component, the `AiChatPanel` key drops.
- `frontend/src/views/__tests__/SketchChatPage.test.ts` — replaced brittle `findComponent({name:'AiChatPanel'})` with stable class selector `.stub-ai-chat-panel`.

## Path-Y status after v0.5.8

| Page | Status |
|------|--------|
| PluginDesignPage | migrated v0.5.7 |
| RuleDesignPage | migrated v0.5.7 |
| HookDesignPage | migrated v0.5.7 |
| CommandDesignPage | migrated v0.5.7 |
| SketchChatPage | migrated v0.5.8 |
| WorkflowPlaygroundPage | migrated v0.5.8 |
| ProjectManagementPage | migrated v0.5.8 |
| SkillCreateWizard | migrated v0.5.8 |
| AgentCreateWizard | migrated v0.5.8 |
| AIBackendsPage | **deferred to v0.5.9** — smart-chat fallback caller |
| SuperAgentPlayground | **deferred to v0.5.9** — smart-chat fallback caller |

9 of 11 chat-bearing pages migrated. Local Agented `AiChatPanel.vue` still in use by 2 callers, plus its sibling components (AiChatSelector, AllModeResponse, ChatModeSelector, CompoundSynthesis, MessageActions, MessageBubble, ProcessGroup) still imported by the local AiChatPanel.

## Verification

| Gate | Result |
|------|--------|
| `cd frontend && npm run test:run` | **1080 passed** (unchanged) |
| `cd frontend && npm run test:coverage` | passes |
| `cd backend && uv run pytest` | 2196 passed (unchanged) |
| `just build` | vue-tsc + vite clean |

## Next milestone

**v0.5.9 — finish path-Y + cleanup tail.** Two parts:

1. AIBackendsPage + SuperAgentPlayground design call. Both pass a thin prop set (`density`, `welcomeTitle`, `placeholder`, etc.) and skip the caller-managed state pattern. Likely answer: switch them to upstream's self-managed `AiChatPanel` (not `AiChatPanelManaged`). They lose Agented's "smart-chat fallback" affordances and gain the upstream LLM-chat experience.

2. Cleanup tail. After the 2 remaining migrations, delete:
   - `frontend/src/components/ai/AiChatPanel.vue` (830 LoC)
   - 7 sibling components (~1450 LoC)
   - `frontend/src/composables/useAllMode.ts` + `useProcessGroups.ts` shims
   - The `AiChatPanel` key from `setup.ts` global stubs
   - Total: ~2080 LoC reduction

Then **E (production hardening)** as originally sequenced.
