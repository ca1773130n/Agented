/**
 * `useTour` composable (Plan 01-02).
 *
 * Wraps the v0.5.0 XState machine with persistence + guard prefetching +
 * auto-skip-completed-steps so callers (Phase 2 visual components) can
 * consume tour state via Vue refs and trigger transitions via thin methods.
 *
 * Replaces the flat-index `frontend/src/composables/useTour.ts`.
 *
 * Boot sequence:
 *   1. Fetch /health/setup-status (Plan 01-01 endpoint).
 *   2. If localStorage has a snapshot AND instance_id matches → restore it;
 *      otherwise drop it and start fresh.
 *   3. Create the actor (with restored snapshot when available).
 *   4. Send HYDRATE to populate context.completed.
 *   5. Send EVALUATE — actor walks past any completed step at-or-after the
 *      current state via SKIP events. Handles OB-08 ("Resume from last
 *      incomplete step").
 *   6. Subscribe — every transition writes the new snapshot to localStorage.
 */
import { computed, shallowRef } from 'vue'
import type { ComputedRef, ShallowRef } from 'vue'
import type { Actor, Snapshot } from 'xstate'
import { createActor } from 'xstate'

import { snapshotStepId, tourMachine } from './machine'
import type { StepId, TourEvent } from './machine'
import {
  clearPersisted,
  readPersisted,
  snapshotForBackend,
  writePersisted,
} from './persistence'
import { fetchSetupStatus } from './setupStatus'

type TourActor = Actor<typeof tourMachine>

/**
 * Drives the actor forward via SKIP events, one per completed step at-or-
 * after the current state, until either the current step is incomplete or
 * the actor reaches `complete`. Pure-functional given the actor; called
 * from `boot()` after HYDRATE.
 */
function autoSkipCompleted(actor: TourActor): void {
  for (let safety = 0; safety < 16; safety++) {
    const snapshot = actor.getSnapshot()
    if (snapshot.status === 'done') return
    const stepId = snapshotStepId(snapshot)
    if (stepId === null) return
    const isCompleted = snapshot.context.completed[stepId]
    if (!isCompleted) return
    actor.send({ type: 'SKIP' })
  }
}

interface UseTourOptions {
  storage?: Storage
  fetchFn?: typeof fetch
  /** Override the boot sequence — useful for tests that pre-populate state. */
  autoStart?: boolean
}

export interface UseTourReturn {
  /** Reactive XState snapshot. */
  snapshot: ShallowRef<ReturnType<TourActor['getSnapshot']>>
  /** Convenience: leaf step id (`'workspace'` etc.) or null when not in setup. */
  currentStepId: ComputedRef<StepId | null>
  /** True between welcome and complete. */
  isActive: ComputedRef<boolean>
  /** True once the user finishes (final state). */
  isComplete: ComputedRef<boolean>
  /** Asynchronously fetch status + restore snapshot. */
  boot: () => Promise<void>
  /** Send arbitrary event (escape hatch for tests / debug). */
  send: (event: TourEvent) => void
  /** Convenience wrappers. */
  start: () => void
  next: () => void
  back: () => void
  skip: () => void
  skipTour: () => void
  /** Clear local storage + transition back to idle. Used by "restart tour". */
  reset: () => void
  /** Tear down the actor. */
  stop: () => void
}

export function useTour(options: UseTourOptions = {}): UseTourReturn {
  const storage = options.storage ?? globalThis.localStorage
  const fetchFn = options.fetchFn ?? globalThis.fetch
  const autoStart = options.autoStart !== false

  // The actor is rebuilt on boot when a persisted snapshot is available, so
  // it has to live behind a mutable handle. The composable's public methods
  // close over `actorRef` rather than a single actor instance.
  const actorRef = { current: createActor(tourMachine) as TourActor }
  const snapshot = shallowRef(actorRef.current.getSnapshot())

  let booted = false

  function attachSubscription(next: TourActor) {
    next.subscribe((s) => {
      snapshot.value = s
    })
  }

  attachSubscription(actorRef.current)
  actorRef.current.start()
  void autoStart  // reserved for tests; currently always starts the actor

  async function boot() {
    if (booted) return
    booted = true

    const status = await fetchSetupStatus(fetchFn)

    const blob = readPersisted(storage)
    const restoredSnapshot = snapshotForBackend(blob, status.instanceId)

    if (blob && !restoredSnapshot) {
      // Instance mismatch (DB reset). OB-06: drop everything.
      clearPersisted(storage)
    }

    if (restoredSnapshot) {
      // Replace the empty actor with one rehydrated from the persisted
      // snapshot. XState v5 takes the snapshot via createActor's options.
      actorRef.current.stop()
      const restored = createActor(tourMachine, {
        snapshot: restoredSnapshot as Snapshot<unknown>,
      })
      attachSubscription(restored)
      restored.start()
      actorRef.current = restored
      // Push the rehydrated state into the ref so consumers see it immediately.
      snapshot.value = restored.getSnapshot()
    }

    actorRef.current.send({
      type: 'HYDRATE',
      completed: status.completed,
      instanceId: status.instanceId,
    })

    autoSkipCompleted(actorRef.current)

    // Subscribe AFTER hydrate/auto-skip so we don't write the intermediate
    // states. Final state of the boot sequence is the first persisted blob.
    actorRef.current.subscribe(() => {
      const persistableSnapshot = actorRef.current.getPersistedSnapshot()
      writePersisted(persistableSnapshot, status.instanceId, storage)
    })
    writePersisted(
      actorRef.current.getPersistedSnapshot(),
      status.instanceId,
      storage,
    )
  }

  const currentStepId = computed<StepId | null>(() =>
    snapshotStepId(snapshot.value),
  )
  const isActive = computed(
    () =>
      snapshot.value.value !== 'idle' &&
      snapshot.value.value !== 'complete',
  )
  const isComplete = computed(() => snapshot.value.status === 'done')

  return {
    snapshot,
    currentStepId,
    isActive,
    isComplete,
    boot,
    send: (event) => actorRef.current.send(event),
    start: () => actorRef.current.send({ type: 'START' }),
    next: () => actorRef.current.send({ type: 'NEXT' }),
    back: () => actorRef.current.send({ type: 'BACK' }),
    skip: () => actorRef.current.send({ type: 'SKIP' }),
    skipTour: () => actorRef.current.send({ type: 'SKIP_TOUR' }),
    reset: () => {
      clearPersisted(storage)
      actorRef.current.stop()
    },
    stop: () => actorRef.current.stop(),
  }
}
