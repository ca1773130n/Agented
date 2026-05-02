/**
 * XState v5 hierarchical state machine for the v0.5.0 onboarding tour.
 *
 * Phase 1, Plan 01-01: machine topology only — no persistence, no guards,
 * no I/O. Plan 01-02 layers `EVALUATE` (auto-skip-completed) + persistence
 * + the `useTour` Vue composable on top. Phase 2+ adds visual components.
 *
 * Topology:
 *   idle → welcome → setup → complete
 *   setup is a compound state with children:
 *     workspace, backends, monitoring, harness, product
 *   setup.backends is a compound state with children:
 *     claude, codex, gemini, opencode
 *
 * Every step responds to NEXT, BACK, and SKIP. SKIP_TOUR from welcome jumps
 * straight to complete (the welcome screen's "skip tour" button).
 *
 * Requirement: OB-04 — "Hierarchical state machine for tour flow".
 */
import { assign, setup } from 'xstate'

export type StepId =
  | 'workspace'
  | 'claude'
  | 'codex'
  | 'gemini'
  | 'opencode'
  | 'monitoring'
  | 'harness'
  | 'product'

/**
 * Mutable state the machine carries across transitions. 01-01 declares the
 * shape; 01-02 fills in real values via the composable.
 */
export interface TourContext {
  /** Steps the user has already completed (set by 01-02's prefetch). */
  completed: Record<StepId, boolean>
  /** Steps the user explicitly skipped (vs. auto-skipped via guard). */
  skipped: Record<StepId, boolean>
  /** Backend's instance_id at the moment the tour started; used by 01-02
   *  to invalidate persistence when the DB is reset. */
  instanceId: string | null
}

export type TourEvent =
  | { type: 'START' }
  | { type: 'NEXT' }
  | { type: 'BACK' }
  | { type: 'SKIP' }
  | { type: 'SKIP_TOUR' }
  // Reserved for 01-02; kept here so tests of the topology don't break when
  // 01-02 wires the action.
  | { type: 'EVALUATE' }
  | {
      type: 'HYDRATE'
      completed: Record<StepId, boolean>
      instanceId: string | null
    }

const emptyCompletion = (): Record<StepId, boolean> => ({
  workspace: false,
  claude: false,
  codex: false,
  gemini: false,
  opencode: false,
  monitoring: false,
  harness: false,
  product: false,
})

export const tourMachine = setup({
  types: {} as {
    context: TourContext
    events: TourEvent
  },
  actions: {
    hydrate: assign(({ event }) => {
      if (event.type !== 'HYDRATE') return {}
      return {
        completed: event.completed,
        instanceId: event.instanceId,
      }
    }),
  },
}).createMachine({
  id: 'tour',
  initial: 'idle',
  context: {
    completed: emptyCompletion(),
    skipped: emptyCompletion(),
    instanceId: null,
  },
  on: {
    // Plan 01-02: HYDRATE is sent on actor boot once the prefetch resolves.
    // It updates the context for subsequent guard checks but does not move
    // state — the EVALUATE event drives auto-advance past completed steps.
    HYDRATE: { actions: 'hydrate' },
  },
  states: {
    idle: {
      on: {
        START: { target: 'welcome' },
      },
    },
    welcome: {
      on: {
        NEXT: { target: 'setup' },
        SKIP_TOUR: { target: 'complete' },
      },
    },
    setup: {
      initial: 'workspace',
      states: {
        workspace: {
          on: {
            NEXT: { target: 'backends' },
            SKIP: { target: 'backends' },
            BACK: { target: '#tour.welcome' },
          },
        },
        backends: {
          initial: 'claude',
          states: {
            claude: {
              on: {
                NEXT: { target: 'codex' },
                SKIP: { target: 'codex' },
                BACK: { target: '#tour.setup.workspace' },
              },
            },
            codex: {
              on: {
                NEXT: { target: 'gemini' },
                SKIP: { target: 'gemini' },
                BACK: { target: 'claude' },
              },
            },
            gemini: {
              on: {
                NEXT: { target: 'opencode' },
                SKIP: { target: 'opencode' },
                BACK: { target: 'codex' },
              },
            },
            opencode: {
              on: {
                NEXT: { target: '#tour.setup.monitoring' },
                SKIP: { target: '#tour.setup.monitoring' },
                BACK: { target: 'gemini' },
              },
            },
          },
        },
        monitoring: {
          on: {
            NEXT: { target: 'harness' },
            SKIP: { target: 'harness' },
            BACK: { target: '#tour.setup.backends.opencode' },
          },
        },
        harness: {
          on: {
            NEXT: { target: 'product' },
            SKIP: { target: 'product' },
            BACK: { target: 'monitoring' },
          },
        },
        product: {
          on: {
            NEXT: { target: '#tour.complete' },
            SKIP: { target: '#tour.complete' },
            BACK: { target: 'harness' },
          },
        },
      },
    },
    complete: {
      type: 'final',
    },
  },
})

/**
 * Type-safe accessor for the leaf step id from an actor snapshot. Returns
 * `null` for the welcome / idle / complete macro states which don't have a
 * step id from the StepId enum.
 */
export function snapshotStepId(state: { value: unknown }): StepId | null {
  const value = state.value
  if (typeof value === 'string') {
    return null  // idle, welcome, complete
  }
  if (value && typeof value === 'object' && 'setup' in value) {
    const setupValue = (value as { setup: unknown }).setup
    if (typeof setupValue === 'string') {
      return setupValue as StepId
    }
    if (
      setupValue &&
      typeof setupValue === 'object' &&
      'backends' in setupValue
    ) {
      return (setupValue as { backends: StepId }).backends
    }
  }
  return null
}
