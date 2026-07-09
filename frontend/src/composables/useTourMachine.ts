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

/** Aggregate guard prefetch (OB-07, OB-18). Mirrors GET /health/setup-status. */
export interface SetupStatus {
  instance_id: string | null
  has_workspace: boolean
  has_claude_account: boolean
  has_codex_account: boolean
  has_gemini_account: boolean
  has_opencode_account: boolean
  has_harness_synced: boolean
  has_first_product: boolean
}

export async function fetchSetupStatus(
  fetchFn: typeof fetch = fetch,
): Promise<SetupStatus | null> {
  try {
    const resp = await fetchFn(`${API_BASE}/health/setup-status`, {
      headers: { Accept: 'application/json' },
    })
    if (!resp.ok) return null
    return (await resp.json()) as SetupStatus
  } catch {
    return null
  }
}

/**
 * Map the API response to the tour state keys the machine uses. Used by the
 * post-init walker to drive synthetic SKIP events past states the user has
 * already finished.
 */
export function setupStatusToCompleted(
  status: SetupStatus,
): Record<string, boolean> {
  // The per-backend register steps were removed (accounts are now auto-detected
  // in onboarding), so the completed-map no longer carries backends.* keys.
  return {
    workspace: status.has_workspace,
    monitoring: false, // read-only step, never auto-skipped
    create_product: status.has_first_product,
    create_project: false,
    create_team: false,
  }
}

/**
 * Drive the actor past completed states via synthetic SKIP events. Walks at
 * most 12 hops (one per state) so a misbehaving guard map can't infinite
 * loop. Designed to be called after `actor.start()` once the user-visible
 * state is `idle` or whatever was restored from persistence.
 *
 * Implements OB-08 ("Resume from last incomplete step") and OB-18's
 * "completing one substep advances past it".
 */
export function autoSkipCompletedSteps(
  actor: Actor<typeof tourMachine>,
  completed: Record<string, boolean>,
): void {
  for (let safety = 0; safety < 12; safety++) {
    const snapshot = actor.getSnapshot()
    if (snapshot.status === 'done') return
    const stateKey = stateValueToKey(snapshot.value)
    if (!stateKey || !completed[stateKey]) return
    actor.send({ type: 'SKIP' })
  }
}

function stateValueToKey(value: string): string | null {
  // Flat machine: value is always a string. idle/welcome/complete carry no
  // completion key, so the walker has nothing to auto-skip there.
  return value === 'idle' || value === 'welcome' || value === 'complete'
    ? null
    : value
}

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
  // Fetch instance-id and setup-status in parallel — both are public,
  // both are read-only, and the user is going to wait on the slower of
  // the two anyway. The aggregate setup-status payload itself contains
  // the instance_id; we only call /instance-id separately as a fallback
  // because /setup-status was added later and may be missing on older
  // backends. Once a release deprecates that fallback, this can collapse
  // to a single call.
  const [remoteInstanceId, setupStatus] = await Promise.all([
    fetchInstanceId(),
    fetchSetupStatus(),
  ])

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

  // OB-08 + OB-18: walk past steps the user has already finished, using
  // the aggregate /health/setup-status response. Done after .start() so
  // the SKIP transitions emit normally and persist via the subscription.
  if (setupStatus) {
    autoSkipCompletedSteps(sharedActor, setupStatusToCompleted(setupStatus))
  }
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
    // Flat machine: the state value is a string step id (or null before init).
    const val = state.value
    return typeof val === 'string' ? val : 'idle'
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
 * Bridge from the @ai-accounts/vue-headless plugin's onEvent hook to the
 * Agented tour actor's lifecycle. Called from main.ts's plugin install.
 *
 * Tour advancement is NOT driven by these events — earlier versions
 * auto-NEXTed on login.completed / wizard.account.created, but both fire
 * before the user finishes the proxy + plan + Save + explicit "Next
 * Backend" click, so the wizard short-circuited. Advancement is wired
 * directly: BackendDetailPage.onWizardDone → tourMachine.nextStep().
 *
 * This function is kept solely for its side effect: lazy-initializing the
 * shared actor so analytics consumers layered on top see a live one. The
 * full discriminated-union AiAccountsEvent type was removed because no
 * branch was ever inspected; argument is `unknown` to make that explicit.
 */
export function notifyAiAccountsEvent(_event: unknown): void {
  if (!initPromise) {
    initPromise = initActor().catch((err) => {
      console.error('[tour] init failed:', err);
      initPromise = null;
      throw err;
    })
  }
}
