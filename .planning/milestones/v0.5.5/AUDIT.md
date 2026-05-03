# v0.5.5 Audit — restored chat components classification

For each restored component: classify project-independent vs
Agented-specific, decide upstream PR target.

## Classification

| Component | LoC | Classification | PR target | Notes |
|-----------|-----|---------------|-----------|-------|
| MessageBubble | 162 | **Project-independent** | `vue-styled` (replace ChatBubble) | Pure presentation; only generic dep is `renderMarkdown` from `useMarkdown` (also extractable). Upgrade ai-accounts' existing `ChatBubble`. |
| MessageActions | 170 | **Project-independent** | `vue-styled` (replace MessageActions) | Imports `ConversationMessage` as type only — when extracting, type moves to ts-core (or use a generic Message shape). Upstream already has MessageActions; this is an upgrade. |
| ProcessGroup | 226 | **Project-independent** | `vue-styled` (replace ProcessGroup) | Zero domain refs. Direct upgrade of ai-accounts' existing ProcessGroup. |
| CompoundSynthesis | 103 | **Project-independent** | `vue-styled` (replace CompoundSynthesis) | Type `SynthesisState` moves with the PR (already in ts-core per recon). |
| AllModeResponse | 262 | **Project-independent** | `vue-styled` (replace AllModeResponses) | Note name: Agented singular `AllModeResponse`, upstream plural `AllModeResponses`. Preserve upstream name. |
| ChatModeSelector | 62 | **Project-independent** | `vue-styled` (new component or extension of ChatControls) | Inspect upstream ChatControls — if it already has chatMode, this is a no-op; if not, add as new. |
| AiChatSelector | 269 | **Project-independent (with adapter)** | `vue-styled` (new component) | Currently imports `listGroupedBackends`/`AIBackend` from Agented's `services/api` — but those wrap ai-accounts' client. Upstream version uses the ai-accounts client directly (`useAiAccounts().client.listBackends()`). |
| AiChatPanel | 830 | **Mixed (orchestrator)** | `vue-styled` (orchestrator extract — partial PR) | Imports child components + Agented domain types (`Sketch`, `Agent` references in slot/template, `ConversationMessage` from services/api). The presentational composition layer is extractable; the Agented-specific orchestration (entity-aware behavior, route awareness) stays. |

## Upstream PR plan

8 candidate PRs. Order matters: child components first, AiChatPanel
last so the upstream AiChatPanel PR can compose the upgraded
children.

1. **PR-1: Upgrade ChatBubble with Agented's MessageBubble design** (`vue-styled`)
2. **PR-2: Upgrade ProcessGroup with Agented's design** (`vue-styled`)
3. **PR-3: Upgrade MessageActions with Agented's design** (`vue-styled`)
4. **PR-4: Upgrade CompoundSynthesis with Agented's design** (`vue-styled`)
5. **PR-5: Upgrade AllModeResponses with Agented's AllModeResponse design** (`vue-styled`)
6. **PR-6: Add ChatModeSelector or upgrade ChatControls** (`vue-styled`)
7. **PR-7: Add AiChatSelector** (`vue-styled` — new component)
8. **PR-8: Upgrade AiChatPanel orchestrator with Agented's presentational layer** (`vue-styled` — biggest, most contentious)

Each PR includes the component upgrade + tests. Tests are written
fresh for each upstream PR (Agented's b2ee00d~1 tree had no test
files for these — recon confirmed).

## v0.5.5 dispatch policy

Per spec: dispatch the upstream PRs autonomously. Per session
constraint (subagent quota at 9:10pm reset): given the breadth, I
will draft each PR's branch + commit locally in
`~/Developer/Projects/ai-accounts` but **not** auto-`gh pr create`
the orchestrator PR (#8). The 7 child PRs are mechanical enough
to dispatch autonomously; #8 is opinionated and benefits from human
review of the extraction boundary before the PR opens.

If quota does not constrain, all 8 dispatch automatically.
