/**
 * Re-export ai-accounts smart chat composable as useAiChat
 * for backward compatibility with existing Agented views during migration.
 *
 * The return-type contract differs from the original (see @ai-accounts/vue-headless
 * UseSmartChatReturn). Consumer views will be migrated one at a time in subsequent
 * tasks.
 */
export { useSmartChat as useAiChat } from '@ai-accounts/vue-headless'
export type { UseSmartChatReturn as UseAiChatReturn } from '@ai-accounts/vue-headless'
export { useProcessGroups } from '@ai-accounts/vue-headless'
export type { ProcessGroup } from '@ai-accounts/vue-headless'
export { useStreamingParser } from '@ai-accounts/vue-headless'
export type { UseStreamingParserReturn, UseStreamingParserOptions } from '@ai-accounts/vue-headless'
