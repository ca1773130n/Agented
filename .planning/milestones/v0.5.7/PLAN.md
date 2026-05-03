# v0.5.7 — PR-8 + path-Y first cluster (4 design wizards)

Two-part milestone:

1. **PR-8 — AiChatPanelManaged upstream** (was deferred from v0.5.6).
   Adds the caller-managed sibling component to `@ai-accounts/vue-styled`
   so consumers can pick between self-managed (`AiChatPanel`, existing)
   and caller-managed (`AiChatPanelManaged`, new) patterns. Released
   as ai-accounts 0.3.11.

2. **Path-Y first cluster** — 4 design wizards (Plugin / Rule / Hook /
   Command) migrate from Agented's local restored `AiChatPanel.vue`
   to consuming `AiChatPanelManaged` from `@ai-accounts/vue-styled`.
   Single-line import change per page; template prop bindings
   unchanged.

Remaining 7 path-Y candidates (SketchChatPage, WorkflowPlaygroundPage,
ProjectManagementPage, AIBackendsPage, SuperAgentPlayground,
SkillCreateWizard, AgentCreateWizard) deferred to v0.5.8+. Once all
11 migrate, Agented's local `frontend/src/components/ai/*.vue` copies
become deletable.
