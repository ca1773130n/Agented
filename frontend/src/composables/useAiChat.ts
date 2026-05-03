/**
 * Re-export ai-accounts smart chat composable as useAiChat
 * for backward compatibility with existing Agented views during migration.
 *
 * The return-type contract differs from the original (see @ai-accounts/vue-headless
 * UseSmartChatReturn). Consumer views will be migrated one at a time in
 * subsequent tasks (path Y, v0.5.5+).
 *
 * v0.5.4 also re-exports the new 0.3.8 types — `BackendAccountOption`
 * (accounts dropdown shape) and `CliproxyLoginStatus` (cliproxy install
 * status) — for any future call site that needs them.
 */
export { useSmartChat as useAiChat } from '@ai-accounts/vue-headless'
export type { UseSmartChatReturn as UseAiChatReturn } from '@ai-accounts/vue-headless'
export { useProcessGroups } from '@ai-accounts/vue-headless'
export type { ProcessGroup } from '@ai-accounts/vue-headless'
export { useStreamingParser } from '@ai-accounts/vue-headless'
export type { UseStreamingParserReturn, UseStreamingParserOptions } from '@ai-accounts/vue-headless'

// 0.3.8 / 0.3.9-pre additions — exposed so future Agented call sites can
// type their account-list and cliproxy-install handling without
// importing directly from ts-core.
export type { BackendAccountOption, CliproxyLoginStatus } from '@ai-accounts/ts-core'
