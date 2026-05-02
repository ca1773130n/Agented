/**
 * Persistence tests (Plan 01-02).
 *
 * Covers OB-05 (round-trip), OB-06 (instance_id mismatch invalidates).
 */
import { describe, expect, it } from 'vitest'

import {
  clearPersisted,
  readPersisted,
  snapshotForBackend,
  writePersisted,
} from '../persistence'

class MemoryStorage implements Storage {
  private store = new Map<string, string>()
  get length() {
    return this.store.size
  }
  clear() {
    this.store.clear()
  }
  getItem(key: string) {
    return this.store.get(key) ?? null
  }
  setItem(key: string, value: string) {
    this.store.set(key, value)
  }
  removeItem(key: string) {
    this.store.delete(key)
  }
  key(index: number) {
    return Array.from(this.store.keys())[index] ?? null
  }
}

const FAKE_SNAPSHOT = {
  value: { setup: 'workspace' },
  context: { instanceId: 'inst-1' },
} as const

describe('persistence — round-trip', () => {
  it('writes then reads the same blob', () => {
    const storage = new MemoryStorage()
    writePersisted(FAKE_SNAPSHOT as never, 'inst-1', storage)
    const got = readPersisted(storage)
    expect(got?.version).toBe(1)
    expect(got?.instanceId).toBe('inst-1')
    expect(got?.snapshot).toEqual(FAKE_SNAPSHOT)
  })

  it('returns null when the storage key is missing', () => {
    const storage = new MemoryStorage()
    expect(readPersisted(storage)).toBeNull()
  })

  it('returns null when the JSON is malformed', () => {
    const storage = new MemoryStorage()
    storage.setItem('agented-tour-state', '{not valid')
    expect(readPersisted(storage)).toBeNull()
  })

  it('returns null when version mismatches', () => {
    const storage = new MemoryStorage()
    storage.setItem(
      'agented-tour-state',
      JSON.stringify({ version: 99, instanceId: 'x', snapshot: {} }),
    )
    expect(readPersisted(storage)).toBeNull()
  })

  it('clearPersisted removes the key', () => {
    const storage = new MemoryStorage()
    writePersisted(FAKE_SNAPSHOT as never, 'inst-1', storage)
    clearPersisted(storage)
    expect(readPersisted(storage)).toBeNull()
  })

  it('writePersisted swallows quota errors silently', () => {
    const storage: Storage = {
      length: 0,
      clear: () => undefined,
      getItem: () => null,
      key: () => null,
      removeItem: () => undefined,
      setItem: () => {
        throw new Error('QuotaExceededError')
      },
    }
    // Must not throw.
    expect(() =>
      writePersisted(FAKE_SNAPSHOT as never, 'inst-1', storage),
    ).not.toThrow()
  })
})

describe('persistence — snapshotForBackend (OB-06 invalidation)', () => {
  it('returns null when the blob is null', () => {
    expect(snapshotForBackend(null, 'inst-1')).toBeNull()
  })

  it('returns null when instance ids differ (DB reset)', () => {
    expect(
      snapshotForBackend(
        { version: 1, instanceId: 'old', snapshot: FAKE_SNAPSHOT },
        'new',
      ),
    ).toBeNull()
  })

  it('returns the snapshot when instance ids match', () => {
    expect(
      snapshotForBackend(
        { version: 1, instanceId: 'inst-1', snapshot: FAKE_SNAPSHOT },
        'inst-1',
      ),
    ).toEqual(FAKE_SNAPSHOT)
  })

  it('returns the snapshot when the backend instance_id is unknown (network glitch)', () => {
    // Don't punish the user with a tour reset because the backend was unreachable.
    expect(
      snapshotForBackend(
        { version: 1, instanceId: 'inst-1', snapshot: FAKE_SNAPSHOT },
        null,
      ),
    ).toEqual(FAKE_SNAPSHOT)
  })
})
