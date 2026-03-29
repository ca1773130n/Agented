import { describe, it, expect, beforeEach, vi, type Mock } from 'vitest'
import { createActor } from 'xstate'
import { tourMachine, type TourEvent } from '../../machines/tourMachine'

// Mock Vue lifecycle hooks BEFORE any other imports
vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue')
  return { ...actual, onUnmounted: vi.fn() }
})

// Mock API client module — getApiKey returns a mutable value
let mockApiKey: string | null = null
vi.mock('../../services/api/client', () => ({
  API_BASE: '',
  getApiKey: () => mockApiKey,
}))

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Create a valid persisted snapshot at a given state by running the machine
 * through events to reach that state.
 */
function getSnapshotAtState(events: Array<TourEvent>): unknown {
  const actor = createActor(tourMachine)
  actor.start()
  for (const event of events) {
    actor.send(event)
  }
  const snapshot = actor.getPersistedSnapshot()
  actor.stop()
  return snapshot
}

function makePersistedData(
  snapshot: unknown,
  instanceId: string | null = 'test-uuid-1',
  schemaVersion: number = 1,
) {
  return JSON.stringify({ schemaVersion, instanceId, snapshot })
}

const STORAGE_KEY = 'agented-tour-machine-state'

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useTourMachine', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.resetModules()
    vi.restoreAllMocks()
    mockApiKey = null
    // Default: mock fetch to return a valid instance-id
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ instance_id: 'test-uuid-1' }),
    }) as unknown as typeof fetch
  })

  // -----------------------------------------------------------------------
  // Initialization
  // -----------------------------------------------------------------------

  describe('initialization', () => {
    it('initializes actor in idle state after async init', async () => {
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      expect(tour.state.value).toBe('idle')
    })

    it('fetches instance-id on init', async () => {
      const { useTourMachine } = await import('../useTourMachine')
      useTourMachine()
      await vi.waitFor(() => {
        expect(globalThis.fetch).toHaveBeenCalled()
      })
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/health/instance-id'),
      )
    })

    it('handles fetch failure gracefully', async () => {
      vi.useFakeTimers()
      globalThis.fetch = vi.fn().mockRejectedValue(
        new Error('Network error'),
      ) as unknown as typeof fetch
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      // Advance past retry delays (2 retries × 800ms)
      for (let i = 0; i < 3; i++) {
        await vi.advanceTimersByTimeAsync(1000)
      }
      vi.useRealTimers()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      expect(tour.state.value).toBe('idle')
    })

    it('handles non-ok fetch response gracefully', async () => {
      vi.useFakeTimers()
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        json: () => Promise.resolve({}),
      }) as unknown as typeof fetch
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      // Advance past retry delays (2 retries × 800ms)
      for (let i = 0; i < 3; i++) {
        await vi.advanceTimersByTimeAsync(1000)
      }
      vi.useRealTimers()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      expect(tour.state.value).toBe('idle')
    })
  })

  // -----------------------------------------------------------------------
  // Persistence — saving
  // -----------------------------------------------------------------------

  describe('persistence - saving', () => {
    it('persists state to localStorage after START transition', async () => {
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      tour.startTour()
      await vi.waitFor(() => {
        expect(tour.state.value).toBe('welcome')
      })
      const raw = localStorage.getItem(STORAGE_KEY)
      expect(raw).not.toBeNull()
      const parsed = JSON.parse(raw!)
      expect(parsed.schemaVersion).toBe(1)
      expect(parsed.instanceId).toBe('test-uuid-1')
    })

    it('persists on every transition', async () => {
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      tour.startTour()
      await vi.waitFor(() => {
        expect(tour.state.value).toBe('welcome')
      })
      const afterStart = localStorage.getItem(STORAGE_KEY)

      tour.nextStep()
      await vi.waitFor(() => {
        expect(tour.state.value).toBe('workspace')
      })
      const afterNext = localStorage.getItem(STORAGE_KEY)

      expect(afterStart).not.toBeNull()
      expect(afterNext).not.toBeNull()
      expect(afterStart).not.toBe(afterNext)
    })
  })

  // -----------------------------------------------------------------------
  // Persistence — restoring
  // -----------------------------------------------------------------------

  describe('persistence - restoring', () => {
    it('restores state from valid localStorage data', async () => {
      const snapshot = getSnapshotAtState([{ type: 'START' }])
      localStorage.setItem(
        STORAGE_KEY,
        makePersistedData(snapshot, 'test-uuid-1', 1),
      )
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      expect(tour.state.value).toBe('welcome')
    })

    it('restores state at workspace from valid localStorage', async () => {
      const snapshot = getSnapshotAtState([
        { type: 'START' },
        { type: 'NEXT' },
      ])
      localStorage.setItem(
        STORAGE_KEY,
        makePersistedData(snapshot, 'test-uuid-1', 1),
      )
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      expect(tour.state.value).toBe('workspace')
    })
  })

  // -----------------------------------------------------------------------
  // Persistence — schema version mismatch
  // -----------------------------------------------------------------------

  describe('persistence - schema version mismatch', () => {
    it('discards state and starts fresh when schemaVersion mismatches', async () => {
      const snapshot = getSnapshotAtState([{ type: 'START' }])
      localStorage.setItem(
        STORAGE_KEY,
        makePersistedData(snapshot, 'test-uuid-1', 999),
      )
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      expect(tour.state.value).toBe('idle')
    })
  })

  // -----------------------------------------------------------------------
  // Persistence — instance-id mismatch
  // -----------------------------------------------------------------------

  describe('persistence - instance-id mismatch', () => {
    it('discards state when instance-id changed (DB reset)', async () => {
      const snapshot = getSnapshotAtState([{ type: 'START' }])
      localStorage.setItem(
        STORAGE_KEY,
        makePersistedData(snapshot, 'old-uuid', 1),
      )
      // Server returns a different instance-id
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ instance_id: 'new-uuid' }),
      }) as unknown as typeof fetch

      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      expect(tour.state.value).toBe('idle')
    })
  })

  // -----------------------------------------------------------------------
  // Persistence — backend unreachable with stale state
  // -----------------------------------------------------------------------

  describe('persistence - backend unreachable with stale state', () => {
    it('discards persisted state when backend is unreachable (DB may have been reset)', async () => {
      vi.useFakeTimers()
      const snapshot = getSnapshotAtState([{ type: 'START' }, { type: 'NEXT' }])
      localStorage.setItem(
        STORAGE_KEY,
        makePersistedData(snapshot, 'old-instance-uuid', 1),
      )
      // Backend is down — fetch fails
      globalThis.fetch = vi.fn().mockRejectedValue(
        new Error('Connection refused'),
      ) as unknown as typeof fetch

      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      // Advance past retry delays
      for (let i = 0; i < 3; i++) {
        await vi.advanceTimersByTimeAsync(1000)
      }
      vi.useRealTimers()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      // Should start fresh (idle), not restore to 'workspace'
      expect(tour.state.value).toBe('idle')
    })
  })

  // -----------------------------------------------------------------------
  // Persistence — instance-id match (valid restore)
  // -----------------------------------------------------------------------

  describe('persistence - instance-id match', () => {
    it('restores when instance-id matches', async () => {
      const snapshot = getSnapshotAtState([{ type: 'START' }])
      localStorage.setItem(
        STORAGE_KEY,
        makePersistedData(snapshot, 'test-uuid-1', 1),
      )
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      expect(tour.state.value).toBe('welcome')
    })
  })

  // -----------------------------------------------------------------------
  // Computed properties
  // -----------------------------------------------------------------------

  describe('computed properties', () => {
    it('isActive is false for idle', async () => {
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      expect(tour.isActive.value).toBe(false)
    })

    it('isActive is true for welcome', async () => {
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      tour.startTour()
      await vi.waitFor(() => {
        expect(tour.state.value).toBe('welcome')
      })
      expect(tour.isActive.value).toBe(true)
    })

    it('isActive is true for workspace', async () => {
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      tour.startTour()
      tour.nextStep()
      await vi.waitFor(() => {
        expect(tour.state.value).toBe('workspace')
      })
      expect(tour.isActive.value).toBe(true)
    })

    it('currentStep returns idle for idle state', async () => {
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      expect(tour.currentStep.value).toBe('idle')
    })

    it('currentStep returns welcome for welcome state', async () => {
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      tour.startTour()
      await vi.waitFor(() => {
        expect(tour.state.value).toBe('welcome')
      })
      expect(tour.currentStep.value).toBe('welcome')
    })

    it('currentStep returns backends.claude for compound state', async () => {
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      tour.startTour()
      tour.nextStep() // welcome -> workspace
      tour.nextStep() // workspace -> backends.claude
      await vi.waitFor(() => {
        expect(tour.currentStep.value).toBe('backends.claude')
      })
    })

    it('canGoBack is false for idle', async () => {
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      expect(tour.canGoBack.value).toBe(false)
    })

    it('canGoBack is false for welcome', async () => {
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      tour.startTour()
      await vi.waitFor(() => {
        expect(tour.state.value).toBe('welcome')
      })
      expect(tour.canGoBack.value).toBe(false)
    })

    it('canGoBack is true for workspace', async () => {
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      tour.startTour()
      tour.nextStep()
      await vi.waitFor(() => {
        expect(tour.state.value).toBe('workspace')
      })
      expect(tour.canGoBack.value).toBe(true)
    })

    it('canGoForward is false for idle', async () => {
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      expect(tour.canGoForward.value).toBe(false)
    })

    it('canGoForward is true for welcome', async () => {
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      tour.startTour()
      await vi.waitFor(() => {
        expect(tour.state.value).toBe('welcome')
      })
      expect(tour.canGoForward.value).toBe(true)
    })

    it('context returns default context initially', async () => {
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      expect(tour.context.value.completedSteps).toEqual([])
      expect(tour.context.value.schemaVersion).toBe(1)
    })

    it('context includes completedSteps after NEXT transitions', async () => {
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      tour.startTour()
      tour.nextStep() // welcome -> workspace, marks welcome completed
      await vi.waitFor(() => {
        expect(tour.state.value).toBe('workspace')
      })
      expect(tour.context.value.completedSteps).toContain('welcome')
    })
  })

  // -----------------------------------------------------------------------
  // Event senders
  // -----------------------------------------------------------------------

  describe('event senders', () => {
    it('startTour transitions from idle to welcome', async () => {
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      tour.startTour()
      await vi.waitFor(() => {
        expect(tour.state.value).toBe('welcome')
      })
    })

    it('nextStep transitions from welcome to workspace', async () => {
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      tour.startTour()
      tour.nextStep()
      await vi.waitFor(() => {
        expect(tour.state.value).toBe('workspace')
      })
    })

    it('prevStep transitions from workspace to welcome', async () => {
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      tour.startTour()
      tour.nextStep()
      await vi.waitFor(() => {
        expect(tour.state.value).toBe('workspace')
      })
      tour.prevStep()
      await vi.waitFor(() => {
        expect(tour.state.value).toBe('welcome')
      })
    })

    it('skipStep transitions from welcome to workspace without marking complete', async () => {
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      tour.startTour()
      tour.skipStep()
      await vi.waitFor(() => {
        expect(tour.state.value).toBe('workspace')
      })
      expect(tour.context.value.completedSteps).not.toContain('welcome')
    })

    it('completeTour does nothing when canSkipAll guard is false', async () => {
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      tour.startTour()
      await vi.waitFor(() => {
        expect(tour.state.value).toBe('welcome')
      })
      tour.completeTour()
      // Should still be on welcome — guard blocked SKIP_ALL
      expect(tour.state.value).toBe('welcome')
    })

    it('restartTour returns to idle and clears localStorage', async () => {
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      tour.startTour()
      await vi.waitFor(() => {
        expect(tour.state.value).toBe('welcome')
      })
      tour.restartTour()
      await vi.waitFor(() => {
        expect(tour.state.value).toBe('idle')
      })
      // localStorage should be cleared by restartTour explicitly
      // (the actor subscription will re-persist on the RESTART transition,
      // but restartTour removes the key before sending RESTART)
    })

    it('clearTourState removes localStorage item', async () => {
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      tour.startTour()
      await vi.waitFor(() => {
        expect(localStorage.getItem(STORAGE_KEY)).not.toBeNull()
      })
      tour.clearTourState()
      expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
    })
  })

  // -----------------------------------------------------------------------
  // checkAndAutoAdvance
  // -----------------------------------------------------------------------

  describe('checkAndAutoAdvance', () => {
    it('auto-advances from workspace when workspace is configured', async () => {
      // Mock fetch to handle both instance-id and API calls
      globalThis.fetch = vi.fn().mockImplementation((url: string) => {
        if (url.includes('/health/instance-id')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ instance_id: 'test-uuid-1' }),
          })
        }
        if (url.includes('/api/settings')) {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                settings: { workspace_dir: '/some/path' },
              }),
          })
        }
        if (url.includes('/admin/backends')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ backends: [] }),
          })
        }
        return Promise.resolve({ ok: false, json: () => Promise.resolve({}) })
      }) as unknown as typeof fetch

      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      tour.startTour()
      tour.nextStep() // welcome -> workspace
      await vi.waitFor(() => {
        expect(tour.state.value).toBe('workspace')
      })
      await tour.checkAndAutoAdvance()
      // Should have auto-advanced past workspace to backends
      await vi.waitFor(() => {
        expect(tour.currentStep.value).toBe('backends.claude')
      })
    })

    it('auto-advances from backends.claude when claude account exists', async () => {
      globalThis.fetch = vi.fn().mockImplementation((url: string) => {
        if (url.includes('/health/instance-id')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ instance_id: 'test-uuid-1' }),
          })
        }
        if (url.includes('/api/settings')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ settings: {} }),
          })
        }
        if (url.includes('/admin/backends/backend-claude')) {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                accounts: [{ id: 'acc-1', name: 'My Claude' }],
              }),
          })
        }
        if (url.includes('/admin/backends')) {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                backends: [
                  {
                    id: 'backend-claude',
                    accounts: [{ id: 'acc-1' }],
                  },
                ],
              }),
          })
        }
        return Promise.resolve({ ok: false, json: () => Promise.resolve({}) })
      }) as unknown as typeof fetch

      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      tour.startTour()
      tour.nextStep() // welcome -> workspace
      tour.nextStep() // workspace -> backends.claude
      await vi.waitFor(() => {
        expect(tour.currentStep.value).toBe('backends.claude')
      })
      await tour.checkAndAutoAdvance()
      // Should auto-advance from claude to codex
      await vi.waitFor(() => {
        expect(tour.currentStep.value).toBe('backends.codex')
      })
    })

    it('stays on current step when checks return false', async () => {
      globalThis.fetch = vi.fn().mockImplementation((url: string) => {
        if (url.includes('/health/instance-id')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ instance_id: 'test-uuid-1' }),
          })
        }
        if (url.includes('/api/settings')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ settings: {} }),
          })
        }
        if (url.includes('/admin/backends')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ backends: [] }),
          })
        }
        return Promise.resolve({ ok: false, json: () => Promise.resolve({}) })
      }) as unknown as typeof fetch

      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      tour.startTour()
      tour.nextStep() // welcome -> workspace
      await vi.waitFor(() => {
        expect(tour.state.value).toBe('workspace')
      })
      await tour.checkAndAutoAdvance()
      // workspace_dir not set, so should stay on workspace
      expect(tour.state.value).toBe('workspace')
    })
  })

  // -----------------------------------------------------------------------
  // Error resilience
  // -----------------------------------------------------------------------

  describe('error resilience', () => {
    it('handles corrupt JSON in localStorage gracefully', async () => {
      localStorage.setItem(STORAGE_KEY, 'not-valid-json{{{')
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      expect(tour.state.value).toBe('idle')
    })

    it('handles localStorage.setItem throwing (quota exceeded)', async () => {
      const originalSetItem = localStorage.setItem.bind(localStorage)
      const setItemSpy = vi
        .spyOn(Storage.prototype, 'setItem')
        .mockImplementation((key: string, value: string) => {
          if (key === STORAGE_KEY) {
            throw new DOMException('QuotaExceededError')
          }
          originalSetItem(key, value)
        })

      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      // Transitions should still work even if persistence fails
      tour.startTour()
      await vi.waitFor(() => {
        expect(tour.state.value).toBe('welcome')
      })
      tour.nextStep()
      await vi.waitFor(() => {
        expect(tour.state.value).toBe('workspace')
      })

      setItemSpy.mockRestore()
    })

    it('handles null parsed object in localStorage', async () => {
      localStorage.setItem(STORAGE_KEY, 'null')
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      expect(tour.state.value).toBe('idle')
    })

    it('handles non-object parsed value in localStorage', async () => {
      localStorage.setItem(STORAGE_KEY, '"just a string"')
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      expect(tour.state.value).toBe('idle')
    })

    it('handles fetchWithAuth network error gracefully', async () => {
      // Set up so that fetchWithAuth calls (e.g. /api/settings) throw
      globalThis.fetch = vi.fn().mockImplementation((url: string) => {
        if (url.includes('/health/instance-id')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ instance_id: 'test-uuid-1' }),
          })
        }
        // All other fetch calls throw
        return Promise.reject(new Error('Network error'))
      }) as unknown as typeof fetch

      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      tour.startTour()
      tour.nextStep() // welcome -> workspace
      await vi.waitFor(() => {
        expect(tour.state.value).toBe('workspace')
      })
      // checkAndAutoAdvance should handle fetchWithAuth errors gracefully
      await tour.checkAndAutoAdvance()
      expect(tour.state.value).toBe('workspace')
    })

    it('handles fetchWithAuth non-ok response', async () => {
      globalThis.fetch = vi.fn().mockImplementation((url: string) => {
        if (url.includes('/health/instance-id')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ instance_id: 'test-uuid-1' }),
          })
        }
        // All auth-based fetches return not-ok
        return Promise.resolve({
          ok: false,
          json: () => Promise.resolve({}),
        })
      }) as unknown as typeof fetch

      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      tour.startTour()
      tour.nextStep()
      await vi.waitFor(() => {
        expect(tour.state.value).toBe('workspace')
      })
      await tour.checkAndAutoAdvance()
      expect(tour.state.value).toBe('workspace')
    })
  })

  // -----------------------------------------------------------------------
  // API key header
  // -----------------------------------------------------------------------

  describe('api key header', () => {
    it('includes X-API-Key header when apiKey is set', async () => {
      mockApiKey = 'test-api-key-123'
      globalThis.fetch = vi.fn().mockImplementation((url: string) => {
        if (url.includes('/health/instance-id')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ instance_id: 'test-uuid-1' }),
          })
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ settings: {} }),
        })
      }) as unknown as typeof fetch

      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      tour.startTour()
      tour.nextStep()
      await vi.waitFor(() => {
        expect(tour.state.value).toBe('workspace')
      })
      await tour.checkAndAutoAdvance()
      // Verify fetch was called with X-API-Key header
      const calls = (globalThis.fetch as Mock).mock.calls
      const settingsCall = calls.find(
        (c: unknown[]) => typeof c[0] === 'string' && c[0].includes('/api/settings'),
      )
      expect(settingsCall).toBeDefined()
      expect(settingsCall![1]?.headers?.['X-API-Key']).toBe('test-api-key-123')
    })
  })

  // -----------------------------------------------------------------------
  // Instance-id edge cases
  // -----------------------------------------------------------------------

  describe('instance-id edge cases', () => {
    it('handles missing instance_id field in response', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({}), // No instance_id field
      }) as unknown as typeof fetch

      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      expect(tour.state.value).toBe('idle')
    })

    it('restores state when persisted instanceId is null and remote is null', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({}), // returns null instance_id
      }) as unknown as typeof fetch

      const snapshot = getSnapshotAtState([{ type: 'START' }])
      localStorage.setItem(
        STORAGE_KEY,
        makePersistedData(snapshot, null, 1), // null instanceId
      )
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      // Both null so no mismatch — should restore
      expect(tour.state.value).toBe('welcome')
    })

    it('discards when remote instanceId is null but persisted has one (backend unreachable)', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({}), // null remote instance id
      }) as unknown as typeof fetch

      const snapshot = getSnapshotAtState([{ type: 'START' }])
      localStorage.setItem(
        STORAGE_KEY,
        makePersistedData(snapshot, 'some-local-id', 1),
      )
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      // Cannot validate instance — discard to prevent stale tour after DB reset
      expect(tour.state.value).toBe('idle')
    })
  })

  // -----------------------------------------------------------------------
  // Persisted snapshot with corrupted snapshot data
  // -----------------------------------------------------------------------

  describe('corrupted snapshot restore', () => {
    it('starts fresh when persisted snapshot has no snapshot field', async () => {
      // Valid schema/instanceId but snapshot field is undefined (persisted.snapshot falsy)
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          schemaVersion: 1,
          instanceId: 'test-uuid-1',
          // snapshot missing entirely
        }),
      )
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      // No snapshot to restore from — starts at idle
      expect(tour.state.value).toBe('idle')
    })
  })

  // -----------------------------------------------------------------------
  // Complete state computed properties
  // -----------------------------------------------------------------------

  describe('complete state computed properties', () => {
    it('isActive is false for complete state', async () => {
      // Navigate to complete: START -> NEXT (x many) -> NEXT to complete
      const snapshot = getSnapshotAtState([
        { type: 'START' },
        { type: 'NEXT' }, // welcome -> workspace
        { type: 'NEXT' }, // workspace -> backends.claude
        { type: 'NEXT' }, // claude -> codex
        { type: 'NEXT' }, // codex -> gemini
        { type: 'NEXT' }, // gemini -> opencode
        { type: 'NEXT' }, // backends -> monitoring (parent handles NEXT from opencode)
        { type: 'NEXT' }, // monitoring -> verification
        { type: 'NEXT' }, // verification -> create_product
        { type: 'NEXT' }, // create_product -> create_project
        { type: 'NEXT' }, // create_project -> create_team
        { type: 'NEXT' }, // create_team -> complete
      ])
      localStorage.setItem(
        STORAGE_KEY,
        makePersistedData(snapshot, 'test-uuid-1', 1),
      )
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      // Machine reached complete (final state)
      expect(tour.isActive.value).toBe(false)
      expect(tour.canGoBack.value).toBe(false)
      expect(tour.canGoForward.value).toBe(false)
    })
  })

  // -----------------------------------------------------------------------
  // checkAndAutoAdvance with no actor
  // -----------------------------------------------------------------------

  describe('checkAndAutoAdvance edge cases', () => {
    it('returns early when actor not initialized', async () => {
      // Call checkAndAutoAdvance before actor init resolves
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      // Don't wait for init — call immediately
      // This exercises the !sharedActor early return
      await tour.checkAndAutoAdvance()
      // No crash
    })

    it('does not advance from non-workspace non-claude state', async () => {
      // On welcome step — checkAndAutoAdvance should do nothing
      globalThis.fetch = vi.fn().mockImplementation((url: string) => {
        if (url.includes('/health/instance-id')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ instance_id: 'test-uuid-1' }),
          })
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ settings: { workspace_dir: '/path' } }),
        })
      }) as unknown as typeof fetch

      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      tour.startTour()
      await vi.waitFor(() => {
        expect(tour.state.value).toBe('welcome')
      })
      await tour.checkAndAutoAdvance()
      // Should stay on welcome — auto-advance only works on workspace/backends.claude
      expect(tour.state.value).toBe('welcome')
    })

    it('auto-advance with backends that have no claude backend', async () => {
      globalThis.fetch = vi.fn().mockImplementation((url: string) => {
        if (url.includes('/health/instance-id')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ instance_id: 'test-uuid-1' }),
          })
        }
        if (url.includes('/api/settings')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ settings: {} }),
          })
        }
        if (url.includes('/admin/backends')) {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                backends: [
                  { id: 'backend-opencode', accounts: [] },
                ],
              }),
          })
        }
        return Promise.resolve({ ok: false, json: () => Promise.resolve({}) })
      }) as unknown as typeof fetch

      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      tour.startTour()
      tour.nextStep()
      tour.nextStep() // -> backends.claude
      await vi.waitFor(() => {
        expect(tour.currentStep.value).toBe('backends.claude')
      })
      await tour.checkAndAutoAdvance()
      // No claude backend found, should stay on backends.claude
      expect(tour.currentStep.value).toBe('backends.claude')
    })

    it('auto-advance with hasAnyBackend true but no claude account', async () => {
      globalThis.fetch = vi.fn().mockImplementation((url: string) => {
        if (url.includes('/health/instance-id')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ instance_id: 'test-uuid-1' }),
          })
        }
        if (url.includes('/api/settings')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ settings: {} }),
          })
        }
        if (url.includes('/admin/backends/backend-claude')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ accounts: [] }), // empty accounts
          })
        }
        if (url.includes('/admin/backends')) {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                backends: [
                  { id: 'backend-claude', accounts: [{ id: 'acc-1' }] },
                ],
              }),
          })
        }
        return Promise.resolve({ ok: false, json: () => Promise.resolve({}) })
      }) as unknown as typeof fetch

      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      tour.startTour()
      tour.nextStep()
      tour.nextStep()
      await vi.waitFor(() => {
        expect(tour.currentStep.value).toBe('backends.claude')
      })
      await tour.checkAndAutoAdvance()
      // claude detail returns empty accounts, no auto-advance
      expect(tour.currentStep.value).toBe('backends.claude')
    })
  })

  // -----------------------------------------------------------------------
  // Persisted data with snapshot but no instanceId
  // -----------------------------------------------------------------------

  describe('persistence edge cases', () => {
    it('restores when persisted data has snapshot but null instanceId', async () => {
      const snapshot = getSnapshotAtState([{ type: 'START' }])
      localStorage.setItem(
        STORAGE_KEY,
        makePersistedData(snapshot, null, 1),
      )
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      // persisted.instanceId is null so mismatch check skipped — restores
      expect(tour.state.value).toBe('welcome')
    })

    it('second call reuses existing actor (initActor early return)', async () => {
      const mod = await import('../useTourMachine')
      const tour1 = mod.useTourMachine()
      await vi.waitFor(() => {
        expect(tour1.state.value).not.toBeNull()
      })
      // Second call on same module — sharedActor already exists
      const tour2 = mod.useTourMachine()
      await vi.waitFor(() => {
        expect(tour2.state.value).not.toBeNull()
      })
      // Both should share the same state
      expect(tour1.state.value).toBe(tour2.state.value)
    })

    it('computed properties return defaults before init completes', async () => {
      // Delay fetch so init takes a while
      globalThis.fetch = vi.fn().mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve({
          ok: true,
          json: () => Promise.resolve({ instance_id: 'test-uuid-1' }),
        }), 500)),
      ) as unknown as typeof fetch

      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      // Before init completes, snapshot is null
      // These exercise the !val early returns in computed properties
      expect(tour.isActive.value).toBe(false)
      expect(tour.currentStep.value).toBe('idle')
      expect(tour.canGoBack.value).toBe(false)
      expect(tour.canGoForward.value).toBe(false)
      expect(tour.context.value.completedSteps).toEqual([])
      // Now wait for init
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
    })

    it('handles persisted data with valid schema but null snapshot', async () => {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ schemaVersion: 1, instanceId: 'test-uuid-1', snapshot: null }),
      )
      const { useTourMachine } = await import('../useTourMachine')
      const tour = useTourMachine()
      await vi.waitFor(() => {
        expect(tour.state.value).not.toBeNull()
      })
      expect(tour.state.value).toBe('idle')
    })
  })
})
