/**
 * Vue 3 composable wrapping the XState v5 tour state machine.
 *
 * Provides:
 * - Persistent state via localStorage (survives page reload)
 * - Instance-ID validation (detects backend DB resets)
 * - Schema-version migration (discards stale snapshots)
 * - Async guard-check-then-advance pattern for backend API queries
 * - Reactive state exposure for Vue components
 */

import { shallowRef, computed, onUnmounted, type ComputedRef } from 'vue'
import { createActor, type Actor, type SnapshotFrom } from 'xstate'
import { tourMachine, type TourContext, type TourEvent } from '../machines/tourMachine'
import { API_BASE, getApiKey } from '../services/api/client'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STORAGE_KEY = 'agented-tour-machine-state'
const SCHEMA_VERSION = 1

// ---------------------------------------------------------------------------
// Persistence types
// ---------------------------------------------------------------------------

interface PersistedTourData {
  schemaVersion: number
  instanceId: string | null
  snapshot: unknown
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function loadPersistedData(): PersistedTourData | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return null
    return parsed as PersistedTourData
  } catch {
    return null
  }
}

function persistSnapshot(
  actor: Actor<typeof tourMachine>,
  instanceId: string | null,
): void {
  try {
    const data: PersistedTourData = {
      schemaVersion: SCHEMA_VERSION,
      instanceId,
      snapshot: actor.getPersistedSnapshot(),
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
  } catch {
    // localStorage may be full or unavailable — degrade gracefully
  }
}

async function fetchInstanceId(): Promise<string | null> {
  try {
    const resp = await fetch(`${API_BASE}/health/instance-id`)
    if (!resp.ok) return null
    const json = await resp.json()
    return json.instance_id ?? null
  } catch {
    return null
  }
}

async function fetchWithAuth<T>(url: string): Promise<T | null> {
  try {
    const apiKey = getApiKey()
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }
    if (apiKey) headers['X-API-Key'] = apiKey
    const resp = await fetch(`${API_BASE}${url}`, { headers })
    if (!resp.ok) return null
    return await resp.json()
  } catch {
    return null
  }
}

// ---------------------------------------------------------------------------
// Guard check results (async-then-advance pattern)
// ---------------------------------------------------------------------------

interface GuardCheckResults {
  workspaceConfigured: boolean
  hasClaudeAccount: boolean
  hasAnyBackend: boolean
  monitoringConfigured: boolean
}

async function runGuardChecks(): Promise<GuardCheckResults> {
  const results: GuardCheckResults = {
    workspaceConfigured: false,
    hasClaudeAccount: false,
    hasAnyBackend: false,
    monitoringConfigured: false,
  }

  // Check workspace configuration via settings
  const settings = await fetchWithAuth<{ settings: Record<string, string> }>('/api/settings')
  if (settings?.settings?.workspace_dir) {
    results.workspaceConfigured = true
  }

  // Check backends
  const backends = await fetchWithAuth<{ backends: Array<{ id: string; accounts?: unknown[] }> }>(
    '/admin/backends',
  )
  if (backends?.backends) {
    results.hasAnyBackend = backends.backends.some(
      (b) => Array.isArray((b as Record<string, unknown>).accounts) &&
        ((b as Record<string, unknown>).accounts as unknown[]).length > 0,
    )
    const claudeBackend = backends.backends.find((b) => b.id === 'backend-claude')
    if (claudeBackend) {
      const detail = await fetchWithAuth<{
        accounts?: Array<Record<string, unknown>>
      }>(`/admin/backends/${claudeBackend.id}`)
      if (detail?.accounts && detail.accounts.length > 0) {
        results.hasClaudeAccount = true
      }
    }
  }

  // Check monitoring configuration
  const monitoringResp = await fetchWithAuth<{ enabled?: boolean }>('/api/monitoring/config')
  if (monitoringResp?.enabled) {
    results.monitoringConfigured = true
  }

  return results
}

// ---------------------------------------------------------------------------
// Singleton actor management
// ---------------------------------------------------------------------------

let sharedActor: Actor<typeof tourMachine> | null = null
let sharedInstanceId: string | null = null
let subscriberCount = 0
let initPromise: Promise<void> | null = null

async function initActor(): Promise<void> {
  if (sharedActor) return

  const persisted = loadPersistedData()
  const remoteInstanceId = await fetchInstanceId()

  let shouldRestore = false

  if (persisted) {
    // Validate schema version
    if (persisted.schemaVersion !== SCHEMA_VERSION) {
      // Schema mismatch — discard
      localStorage.removeItem(STORAGE_KEY)
    } else if (remoteInstanceId && persisted.instanceId && persisted.instanceId !== remoteInstanceId) {
      // Instance ID mismatch — DB was reset
      localStorage.removeItem(STORAGE_KEY)
    } else if (persisted.snapshot) {
      shouldRestore = true
    }
  }

  sharedInstanceId = remoteInstanceId

  if (shouldRestore && persisted?.snapshot) {
    try {
      sharedActor = createActor(tourMachine, {
        snapshot: persisted.snapshot as SnapshotFrom<typeof tourMachine>,
      })
    } catch {
      // Snapshot may be incompatible — start fresh
      sharedActor = createActor(tourMachine)
    }
  } else {
    sharedActor = createActor(tourMachine)
  }

  // Subscribe to persist on every transition
  sharedActor.subscribe(() => {
    if (sharedActor) {
      persistSnapshot(sharedActor, sharedInstanceId)
    }
  })

  sharedActor.start()
}

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useTourMachine() {
  // Ensure actor is initialized (idempotent)
  if (!initPromise) {
    initPromise = initActor()
  }

  // Reactive snapshot reference
  const snapshot = shallowRef<SnapshotFrom<typeof tourMachine> | null>(
    sharedActor?.getSnapshot() ?? null,
  )

  // Update snapshot ref when actor transitions
  let unsubscribe: (() => void) | null = null

  // Handle async init — once actor is ready, subscribe
  initPromise.then(() => {
    if (!sharedActor) return
    snapshot.value = sharedActor.getSnapshot()
    const sub = sharedActor.subscribe((s) => {
      snapshot.value = s
    })
    unsubscribe = () => sub.unsubscribe()
    subscriberCount++
  })

  onUnmounted(() => {
    unsubscribe?.()
    subscriberCount--
    // Do NOT stop the shared actor on unmount — it persists across route changes
  })

  // -------------------------------------------------------------------------
  // Computed properties
  // -------------------------------------------------------------------------

  const state: ComputedRef<SnapshotFrom<typeof tourMachine>['value'] | null> = computed(
    () => snapshot.value?.value ?? null,
  )

  const context: ComputedRef<TourContext> = computed(
    () =>
      snapshot.value?.context ?? {
        instanceId: null,
        schemaVersion: 1,
        completedSteps: [],
      },
  )

  const isActive: ComputedRef<boolean> = computed(() => {
    const val = state.value
    if (!val) return false
    return val !== 'idle' && val !== 'complete'
  })

  const currentStep: ComputedRef<string> = computed(() => {
    const val = state.value
    if (!val) return 'idle'
    if (typeof val === 'string') return val
    // Compound state — e.g., { backends: 'claude' }
    const keys = Object.keys(val as Record<string, unknown>)
    if (keys.length > 0) {
      const parent = keys[0]
      const child = (val as Record<string, string>)[parent]
      return `${parent}.${child}`
    }
    return 'unknown'
  })

  const canGoBack: ComputedRef<boolean> = computed(() => {
    const val = state.value
    if (!val) return false
    // Can go back from any step except idle, welcome, and complete
    return val !== 'idle' && val !== 'welcome' && val !== 'complete'
  })

  const canGoForward: ComputedRef<boolean> = computed(() => {
    const val = state.value
    if (!val) return false
    return val !== 'idle' && val !== 'complete'
  })

  // -------------------------------------------------------------------------
  // Event senders
  // -------------------------------------------------------------------------

  function send(event: TourEvent): void {
    sharedActor?.send(event)
  }

  function startTour(): void {
    send({ type: 'START' })
  }

  function nextStep(): void {
    send({ type: 'NEXT' })
  }

  function prevStep(): void {
    send({ type: 'BACK' })
  }

  function skipStep(): void {
    send({ type: 'SKIP' })
  }

  function completeTour(): void {
    send({ type: 'SKIP_ALL' })
  }

  function restartTour(): void {
    localStorage.removeItem(STORAGE_KEY)
    send({ type: 'RESTART' })
  }

  function clearTourState(): void {
    localStorage.removeItem(STORAGE_KEY)
  }

  // -------------------------------------------------------------------------
  // Async guard auto-advance
  // -------------------------------------------------------------------------

  /**
   * Run async guard checks and auto-advance past already-completed steps.
   * Call this when the tour becomes active and the user lands on a step
   * that may already be satisfied.
   */
  async function checkAndAutoAdvance(): Promise<void> {
    if (!sharedActor) return
    const checks = await runGuardChecks()
    const snap = sharedActor.getSnapshot()
    const val = snap.value

    // If on workspace step and workspace is configured, auto-advance
    if (val === 'workspace' && checks.workspaceConfigured) {
      send({ type: 'NEXT' })
      return
    }

    // If on monitoring step and monitoring is configured, auto-advance
    if (val === 'monitoring' && checks.monitoringConfigured) {
      send({ type: 'NEXT' })
      return
    }

    // If on backends.claude and has claude account, auto-advance
    if (
      typeof val === 'object' &&
      val !== null &&
      (val as Record<string, string>).backends === 'claude' &&
      checks.hasClaudeAccount
    ) {
      send({ type: 'NEXT' })
    }
  }

  return {
    state,
    context,
    send,
    isActive,
    currentStep,
    canGoBack,
    canGoForward,
    startTour,
    nextStep,
    prevStep,
    skipStep,
    completeTour,
    restartTour,
    clearTourState,
    checkAndAutoAdvance,
  }
}

// ---------------------------------------------------------------------------
// Route prefetching (OB-42) — fire-and-forget on tour start
// ---------------------------------------------------------------------------

/**
 * Prefetch route components visited during the tour.
 * Uses dynamic import() to trigger Vite chunk loading ahead of navigation.
 * Fire-and-forget — callers should NOT await this.
 */
export async function prefetchTourRoutes(): Promise<void> {
  await Promise.allSettled([
    import('../views/SettingsPage.vue'),
    import('../views/BackendDetailPage.vue'),
  ])
}
