# v0.5.4 — ai-accounts 0.3.8 migration

Spec: `docs/superpowers/specs/2026-05-03-v0.5.4-ai-accounts-0.3.8-migration-design.md`
Plan: `docs/superpowers/plans/2026-05-03-v0.5.4-ai-accounts-0.3.8-migration.md`
Audit: `.planning/milestones/v0.5.4/AUDIT.md`

Path: **Z (fat translation wrapper)**. The previous WIP (commit
`b2ee00d`, 2026-04-14) collapsed `frontend/src/components/ai/AiChatPanel.vue`
from 837 → 36 lines as a pass-through and left 11 call sites silently
broken (caller-managed `messages` / `streamingContent` / `inputMessage`
/ backend selector props were dropped via Vue's `inheritAttrs`).

v0.5.4 rebuilds the wrapper as a translation layer: accepts the legacy
837-line consumer API, drives `@ai-accounts/vue-styled` subcomponents
(`ChatBubble`, `ChatControls`, `FinalizationBanner`) and `useSmartChat`
internally. Each of the 11 call sites stays unchanged.

Deferred: **path Y** — per-call-site migration to `BaseAiChatPanel`'s
smart-chat-managed state model. Tracked for v0.5.5+, one or two pages
per patch.
