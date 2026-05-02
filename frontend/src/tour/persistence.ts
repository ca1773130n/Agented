/**
 * Tour state persistence (Plan 01-02).
 *
 * Round-trips the XState actor's snapshot through `localStorage` so reloads
 * resume at the exact step the user left off (OB-05). The persisted blob is
 * keyed by the backend's `instance_id`; mismatches mean the DB was reset and
 * we drop all tour state (OB-06).
 *
 * Failure modes (all → "treat as fresh, don't crash"):
 *   - Empty / missing localStorage value
 *   - Malformed JSON
 *   - `version !== 1` (forward migration not yet implemented)
 *   - `instanceId` mismatch with the running backend
 */
import type { Snapshot } from 'xstate'

const STORAGE_KEY = 'agented-tour-state'
const STORAGE_VERSION = 1 as const

export interface PersistedTour {
  version: typeof STORAGE_VERSION
  instanceId: string | null
  snapshot: unknown
}

/** Load + validate the persisted blob. Returns null on any failure. */
export function readPersisted(
  storage: Storage = localStorage,
): PersistedTour | null {
  try {
    const raw = storage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as PersistedTour
    if (
      parsed === null ||
      typeof parsed !== 'object' ||
      parsed.version !== STORAGE_VERSION ||
      !('instanceId' in parsed) ||
      !('snapshot' in parsed)
    ) {
      return null
    }
    return parsed
  } catch {
    return null
  }
}

/** Drop the persisted blob (called on instance_id mismatch). */
export function clearPersisted(storage: Storage = localStorage): void {
  try {
    storage.removeItem(STORAGE_KEY)
  } catch {
    // ignore — best-effort
  }
}

/**
 * Persist the actor's current snapshot. Caller passes the snapshot it got
 * from `actor.getPersistedSnapshot()` to avoid coupling to the actor type.
 */
export function writePersisted(
  snapshot: Snapshot<unknown>,
  instanceId: string | null,
  storage: Storage = localStorage,
): void {
  const blob: PersistedTour = {
    version: STORAGE_VERSION,
    instanceId,
    snapshot,
  }
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(blob))
  } catch {
    // QuotaExceededError, private mode, etc. — degrade silently.
  }
}

/**
 * Decide whether a freshly-loaded blob is usable for the current backend.
 * Returns the blob's snapshot when usable, otherwise null (caller starts
 * fresh and clears the blob).
 */
export function snapshotForBackend(
  blob: PersistedTour | null,
  currentInstanceId: string | null,
): unknown | null {
  if (!blob) return null
  if (currentInstanceId === null) {
    // Backend didn't return an instance_id (network glitch or mid-migration);
    // don't risk overwriting a valid local state. Surface the local snapshot.
    return blob.snapshot
  }
  if (blob.instanceId !== currentInstanceId) return null
  return blob.snapshot
}
