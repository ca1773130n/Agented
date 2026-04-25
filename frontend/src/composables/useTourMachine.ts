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
import { API_BASE } from '../services/api/client'

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

const INSTANCE_ID_RETRIES = 2
const INSTANCE_ID_RETRY_MS = 800

async function fetchInstanceId(): Promise<string | null> {
  for (let attempt = 0; attempt <= INSTANCE_ID_RETRIES; attempt++) {
    try {
      const resp = await fetch(`${API_BASE}/health/instance-id`)
      if (!resp.ok) {
        if (attempt < INSTANCE_ID_RETRIES) {
          await new Promise(r => setTimeout(r, INSTANCE_ID_RETRY_MS))
          continue
        }
        return null
      }
      const json = await resp.json()
      return json.instance_id ?? null
    } catch {
      if (attempt < INSTANCE_ID_RETRIES) {
        await new Promise(r => setTimeout(r, INSTANCE_ID_RETRY_MS))
        continue
      }
      return null
    }
  }
  return null
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
    } else if (!remoteInstanceId && persisted.instanceId) {
      // Backend unreachable but we have persisted state tied to an instance —
      // cannot validate, so discard to avoid restoring stale tour from a
      // previous DB that was wiped (e.g. `just reset && just deploy`).
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
    initPromise = initActor().catch((err) => {
      console.error('[tour] init failed:', err);
      initPromise = null;  // allow retry on next useTourMachine() call
      throw err;
    })
  }

  // Reactive snapshot reference
  const snapshot = shallowRef<SnapshotFrom<typeof tourMachine> | null>(
    sharedActor?.getSnapshot() ?? null,
  )

  // Update snapshot ref when actor transitions
  let unsubscribe: (() => void) | null = null

  // Track unmount so an actor init that resolves AFTER the component has
  // already gone away does not install a stale subscription that leaks the
  // snapshot ref or inflates the subscriber count.
  let isUnmounted = false
  let subscribed = false

  // Handle async init — once actor is ready, subscribe (unless the caller
  // already unmounted while we were waiting).
  initPromise.then(() => {
    if (isUnmounted || !sharedActor) return
    snapshot.value = sharedActor.getSnapshot()
    const sub = sharedActor.subscribe((s) => {
      snapshot.value = s
    })
    unsubscribe = () => sub.unsubscribe()
    subscribed = true
    subscriberCount++
  })

  onUnmounted(() => {
    isUnmounted = true
    unsubscribe?.()
    // Only decrement the subscriber count if we actually installed a
    // subscription — otherwise early unmounts would drive the count
    // negative (the pre-fix behaviour).
    if (subscribed) {
      subscribed = false
      subscriberCount--
    }
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

// ---------------------------------------------------------------------------
// ai-accounts plugin event bridge
// ---------------------------------------------------------------------------

/**
 * Minimal shape of a @ai-accounts/ts-core AiAccountsEvent.
 * Kept local to avoid forcing a hard import of @ai-accounts/ts-core into
 * this file; the real type lives in `@ai-accounts/ts-core`.
 */
type AiAccountsEventLike =
  | { type: 'wizard.opened'; backendKind: string }
  | { type: 'wizard.step'; backendKind: string; step: string }
  | { type: 'wizard.account.created'; backendKind: string; accountId: string }
  | { type: 'wizard.closed'; backendKind: string; reason: 'done' | 'skip' | 'cancel' }
  | { type: 'login.started'; sessionId: string; backendKind: string; flow: string }
  | { type: 'login.prompt'; sessionId: string; promptKind: 'url' | 'text' | 'menu' }
  | { type: 'login.completed'; sessionId: string; accountId: string }
  | { type: 'login.failed'; sessionId: string; code: string; message: string }
  | { type: 'internal.handler_error'; error: string; original: unknown }

/**
 * Bridge an AiAccountsEvent from the @ai-accounts/vue-headless plugin into
 * the Agented tour state machine.  Call this from the plugin's `onEvent`
 * hook in `main.ts`.
 *
 * Currently observational only — no event advances the tour.  Earlier
 * versions auto-NEXTed on `login.completed` / `wizard.account.created`,
 * but both fire *before* the user has walked through the full wizard
 * (proxy + plan + Save + explicit "다음 백엔드" click), which
 * short-circuited the wizard and bounced the user to the next backend as
 * soon as the OAuth code was accepted.  Tour advancement now only
 * happens when the user clicks the wizard's "다음 백엔드" button →
 * `BackendDetailPage.onWizardDone` → `tourMachine.nextStep()`.
 *
 * The function still initializes the shared actor so that analytics
 * consumers layered on top see a live actor, and so the "no-op" contract
 * is stable for plugin callers even if the tour itself was never started.
 */
export function notifyAiAccountsEvent(event: AiAccountsEventLike): void {
  // Ensure actor init has kicked off (idempotent; resolves async).
  if (!initPromise) {
    initPromise = initActor().catch((err) => {
      console.error('[tour] init failed:', err);
      initPromise = null;
      throw err;
    })
  }
  void event;
}
