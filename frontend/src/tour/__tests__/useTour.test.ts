/**
 * useTour boot + auto-skip-completed tests (Plan 01-02).
 *
 * Covers OB-08 (resume from last incomplete step), and the boot integration
 * of persistence + guards.
 */
import { describe, expect, it, vi } from 'vitest'

import { useTour } from '../useTour'

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

function fakeFetch(payload: Record<string, unknown>) {
  return vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(payload),
  } as Response)
}

const FRESH_STATUS = {
  instance_id: 'inst-1',
  has_workspace: false,
  has_claude_account: false,
  has_codex_account: false,
  has_gemini_account: false,
  has_opencode_account: false,
  has_harness_synced: false,
  has_first_product: false,
}

describe('useTour — fresh boot', () => {
  it('starts in idle and can be advanced to welcome via START', async () => {
    const storage = new MemoryStorage()
    const fetchFn = fakeFetch(FRESH_STATUS) as unknown as typeof fetch

    const tour = useTour({ storage, fetchFn })
    expect(tour.snapshot.value.value).toBe('idle')

    await tour.boot()
    expect(tour.snapshot.value.value).toBe('idle') // boot doesn't auto-START
    expect(tour.isActive.value).toBe(false)

    tour.start()
    expect(tour.snapshot.value.value).toBe('welcome')
    expect(tour.isActive.value).toBe(true)
    tour.stop()
  })

  it('persists the snapshot to localStorage on every transition after boot', async () => {
    const storage = new MemoryStorage()
    const fetchFn = fakeFetch(FRESH_STATUS) as unknown as typeof fetch
    const tour = useTour({ storage, fetchFn })
    await tour.boot()

    expect(storage.getItem('agented-tour-state')).toBeTruthy()
    const beforeNext = storage.getItem('agented-tour-state')

    tour.start()
    tour.next()
    expect(tour.currentStepId.value).toBe('workspace')
    const afterNext = storage.getItem('agented-tour-state')
    expect(afterNext).not.toBe(beforeNext)
    tour.stop()
  })
})

describe('useTour — OB-08 auto-skip-completed', () => {
  it('boot without persisted state lands on idle (HYDRATE only updates context)', async () => {
    // Fresh boot: actor is in idle. Auto-skip is a no-op because the leaf
    // step id is null. The user has to send START → NEXT to enter setup.
    const storage = new MemoryStorage()
    const fetchFn = fakeFetch({
      ...FRESH_STATUS,
      has_workspace: true,
      has_claude_account: true,
      has_codex_account: true,
    }) as unknown as typeof fetch

    const tour = useTour({ storage, fetchFn })
    await tour.boot()
    expect(tour.snapshot.value.value).toBe('idle')

    // Once the user starts the tour, NEXT past welcome enters workspace.
    // Subsequent NEXTs land on the first incomplete backend (gemini).
    tour.start()
    tour.next() // welcome → setup.workspace
    expect(tour.currentStepId.value).toBe('workspace')
    tour.stop()
  })

  it('boot with persisted state at workspace + workspace completed → auto-skips to backends.claude', async () => {
    const storage = new MemoryStorage()
    // Pre-populate localStorage with a snapshot at setup.workspace.
    const setupSnapshot = (await (async () => {
      const { createActor } = await import('xstate')
      const { tourMachine } = await import('../machine')
      const a = createActor(tourMachine)
      a.start()
      a.send({ type: 'START' })
      a.send({ type: 'NEXT' })
      const snap = a.getPersistedSnapshot()
      a.stop()
      return snap
    })())

    storage.setItem(
      'agented-tour-state',
      JSON.stringify({
        version: 1,
        instanceId: 'inst-1',
        snapshot: setupSnapshot,
      }),
    )

    const fetchFn = fakeFetch({
      ...FRESH_STATUS,
      has_workspace: true,
    }) as unknown as typeof fetch

    const tour = useTour({ storage, fetchFn })
    await tour.boot()
    // Booted from setup.workspace, hydrated with workspace=true → auto-skipped.
    expect(tour.currentStepId.value).toBe('claude')
    tour.stop()
  })

  it('OB-06: instance_id mismatch drops persisted state', async () => {
    const storage = new MemoryStorage()
    storage.setItem(
      'agented-tour-state',
      JSON.stringify({
        version: 1,
        instanceId: 'old-inst',
        snapshot: { value: { setup: 'workspace' } },
      }),
    )
    const fetchFn = fakeFetch({
      ...FRESH_STATUS,
      instance_id: 'new-inst',
    }) as unknown as typeof fetch

    const tour = useTour({ storage, fetchFn })
    await tour.boot()

    // Should land on idle (fresh start), and the old snapshot should be gone
    // (replaced by the boot-time write keyed to the new instance id).
    expect(tour.snapshot.value.value).toBe('idle')
    const stored = JSON.parse(
      storage.getItem('agented-tour-state') ?? '{}',
    )
    expect(stored.instanceId).toBe('new-inst')
    tour.stop()
  })
})

describe('useTour — survives an unreachable backend', () => {
  it('boot does not throw when /health/setup-status fails', async () => {
    const storage = new MemoryStorage()
    const fetchFn = vi
      .fn()
      .mockRejectedValue(new TypeError('network down')) as unknown as typeof fetch
    const tour = useTour({ storage, fetchFn })
    await expect(tour.boot()).resolves.toBeUndefined()
    expect(tour.snapshot.value.value).toBe('idle')
    tour.stop()
  })
})
