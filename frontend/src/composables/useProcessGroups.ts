/**
 * Type re-export shim for restored b2ee00d~1 chat components.
 *
 * Replaces the deleted local composable; the runtime hook and
 * `ProcessGroup` type now live in `@ai-accounts/vue-headless`. The
 * `ProcessGroupType` discriminator (used by deeper consumers) lives in
 * `@ai-accounts/ts-core`.
 *
 * Path Y / v0.5.6+ migrates the components to import directly from
 * those packages and deletes this shim.
 */
export { useProcessGroups } from '@ai-accounts/vue-headless'
export type { ProcessGroup } from '@ai-accounts/vue-headless'
export type { ProcessGroupType } from '@ai-accounts/ts-core'
