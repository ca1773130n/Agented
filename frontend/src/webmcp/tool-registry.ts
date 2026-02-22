/**
 * Runtime tool manifest for discoverability.
 *
 * Tracks all currently registered WebMCP tools so that the
 * `hive_list_registered_tools` generic tool can enumerate them.
 * The useWebMcpTool composable calls registerInManifest/deregisterFromManifest
 * on mount/unmount to keep this manifest in sync with actual registrations.
 */

import type { ManifestEntry } from './types';

/** Private registry storing registered tool metadata. */
const registry = new Map<string, ManifestEntry>();

/** Adds a tool entry to the manifest. */
export function registerInManifest(
  name: string,
  description: string,
  page: string
): void {
  registry.set(name, { name, description, page });
}

/** Removes a tool entry from the manifest. */
export function deregisterFromManifest(name: string): void {
  registry.delete(name);
}

/** Returns all manifest entries as an array (for hive_list_registered_tools to consume). */
export function getManifest(): ManifestEntry[] {
  return Array.from(registry.values());
}

/** Check for duplicate names (collision detection during development). */
export function isRegistered(name: string): boolean {
  return registry.has(name);
}

/** Clear all entries from the registry. Exposed for testing purposes only. */
export function clearRegistry(): void {
  registry.clear();
}
