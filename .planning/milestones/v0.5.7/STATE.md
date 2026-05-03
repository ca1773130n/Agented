# v0.5.7 State

Status: **COMPLETE** — ready for tag/release.

## Shipped

### Part 1 — PR-8: AiChatPanelManaged upstream (ai-accounts#14)

Caller-managed sibling to upstream's existing self-managed
`AiChatPanel`. ~600 LoC ported from Agented's restored 830-line
panel; composes existing vue-styled subcomponents
(`ChatBubble`, `AiChatSelector`, `AllModeResponses`,
`CompoundSynthesis`, `ProcessGroup`, `MessageActions`).

Design simplifications during the port:
- `synthesisState` prop dropped from `AllModeResponses` binding
  (separate `CompoundSynthesis` already covers it upstream)
- `initStreamingParser` (smd.js parser hook) dropped — `ChatBubble`
  owns its own markdown rendering via `marked`
- `useSmartScroll` legacy non-smart-scroll branch collapsed; smart-
  scroll behavior preserved
- Inline finalize banner kept (Agented gradient + assistant-icon
  SVG that upstream `FinalizationBanner` doesn't expose)

15 new tests in `packages/vue-styled/tests/AiChatPanelManaged.test.ts`.
Released as ai-accounts 0.3.11.

### Part 2 — Path-Y first cluster: 4 design wizards

| Page | Migration |
|------|-----------|
| `frontend/src/views/PluginDesignPage.vue` | local AiChatPanel → `AiChatPanelManaged` |
| `frontend/src/views/RuleDesignPage.vue` | local AiChatPanel → `AiChatPanelManaged` |
| `frontend/src/views/HookDesignPage.vue` | local AiChatPanel → `AiChatPanelManaged` |
| `frontend/src/views/CommandDesignPage.vue` | local AiChatPanel → `AiChatPanelManaged` |

Each migration is a single-line import swap:

```ts
// before
import AiChatPanel from '../components/ai/AiChatPanel.vue';
// after
import { AiChatPanelManaged as AiChatPanel } from '@ai-accounts/vue-styled';
```

Template prop bindings unchanged — `AiChatPanelManaged`'s caller-
managed API matches Agented's restored panel surface for the prop
set these 4 wizards use.

## Verification

| Gate | Result |
|------|--------|
| `cd frontend && npm run test:run` | **1080 passed** (unchanged from v0.5.5/v0.5.6) |
| `cd frontend && npm run test:coverage` | passes |
| `cd backend && uv run pytest` | 2196 passed (unchanged) |
| `just build` | vue-tsc + vite clean |
| ai-accounts 0.3.11 | dist rebuilt; Agented consumes via file: pin |

## Deferred to v0.5.8+

**7 remaining path-Y migrations.** Pages still consuming Agented's
local `AiChatPanel.vue`:

- `SketchChatPage.vue` — sketch ideation flow with extra sidebars
- `WorkflowPlaygroundPage.vue` — workflow design + chat
- `ProjectManagementPage.vue` — kanban + chat helper
- `AIBackendsPage.vue` — "smart-chat fallback" caller (3-prop subset)
- `SuperAgentPlayground.vue` — same fallback pattern (5-prop subset)
- `SkillCreateWizard.vue` — wizard with chat
- `AgentCreateWizard.vue` — wizard with chat

The 2 "smart-chat fallback" callers (AIBackendsPage,
SuperAgentPlayground) might want the upstream **self-managed**
`AiChatPanel` (not `Managed`), since they don't drive their own state.
Per-page design call needed for those two; the other 5 are mechanical
import swaps like the v0.5.7 cluster.

## Cleanup tail (v0.5.9 or later)

Once all 11 pages migrate, delete:
- `frontend/src/components/ai/AiChatPanel.vue` (830 lines)
- `frontend/src/components/ai/AiChatSelector.vue` (269)
- `frontend/src/components/ai/AllModeResponse.vue` (262)
- `frontend/src/components/ai/ChatModeSelector.vue` (62)
- `frontend/src/components/ai/CompoundSynthesis.vue` (103)
- `frontend/src/components/ai/MessageActions.vue` (170)
- `frontend/src/components/ai/MessageBubble.vue` (162)
- `frontend/src/components/ai/ProcessGroup.vue` (226)
- `frontend/src/composables/useAllMode.ts` (type shim)
- `frontend/src/composables/useProcessGroups.ts` (type shim)

Total: ~2080 LoC reduction. The components are no longer the canonical
implementation — that lives upstream now.

## Next milestone

**v0.5.8: path-Y second cluster** — most likely SketchChatPage +
WorkflowPlaygroundPage + ProjectManagementPage + 2 create wizards.
Mechanical import swaps for 5 of them; 2 (AIBackends/SuperAgent) need
a separate design call between self-managed vs caller-managed.

After path-Y completes (v0.5.9 / v0.5.10), then **E (production
hardening)** as originally sequenced.
