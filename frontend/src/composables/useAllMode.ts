/**
 * Type re-export shim for restored b2ee00d~1 chat components.
 *
 * Pre-`06f6cdd`, these types lived in a 462-line useAllMode composable
 * (commit `2c765d2`). v0.5.4 migration moved them upstream to
 * `@ai-accounts/ts-core`. This shim preserves the legacy
 * `'../../composables/useAllMode'` import path for the restored
 * components without re-creating the runtime composable.
 *
 * Path Y / v0.5.6+ should migrate the components to import directly
 * from `@ai-accounts/ts-core` and delete this shim.
 */
export type { ChatMode, BackendResponse, SynthesisState } from '@ai-accounts/ts-core'
