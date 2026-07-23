/**
 * XState v5 tour state machine definition.
 *
 * Defines the complete onboarding tour flow with all states, transitions,
 * guards, and actions. No side effects — pure machine definition.
 *
 * The machine uses XState v5's setup() API for type-safe guards and actions.
 */

import { setup, assign } from 'xstate'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TourContext {
  /** Backend instance ID for staleness detection */
  instanceId: string | null
  /** Persistence format version */
  schemaVersion: number
  /** Steps completed (not skipped) by the user */
  completedSteps: string[]
}

export type TourEvent =
  | { type: 'START' }
  | { type: 'NEXT' }
  | { type: 'BACK' }
  | { type: 'SKIP' }
  | { type: 'SKIP_ALL' }
  | { type: 'RESTART' }

// ---------------------------------------------------------------------------
// Initial context
// ---------------------------------------------------------------------------

const initialContext: TourContext = {
  instanceId: null,
  schemaVersion: 1,
  completedSteps: [],
}

// ---------------------------------------------------------------------------
// Machine definition
// ---------------------------------------------------------------------------

export const tourMachine = setup({
  types: {
    context: {} as TourContext,
    events: {} as TourEvent,
  },

  guards: {
    // Only canSkipAll is wired to a transition (SKIP_ALL). The old per-step
    // guards (isWorkspaceConfigured/hasClaudeAccount/hasAnyBackend/
    // isMonitoringConfigured) were never referenced and went with the
    // per-backend steps.
    canSkipAll: () => false,
  },

  actions: {
    markStepCompleted: assign({
      completedSteps: ({ context, self }) => {
        // The machine is flat (no compound states), so the state value is
        // always a plain string step id.
        const step = self.getSnapshot().value as string
        if (context.completedSteps.includes(step)) return context.completedSteps
        return [...context.completedSteps, step]
      },
    }),
    clearProgress: assign(() => ({ ...initialContext })),
    persistState: () => {
      // Placeholder — localStorage persistence added in Plan 02
    },
  },
}).createMachine({
  id: 'tour',
  initial: 'idle',
  context: initialContext,

  on: {
    RESTART: {
      target: '.idle',
      actions: ['clearProgress'],
    },
    SKIP_ALL: {
      target: '.complete',
      guard: 'canSkipAll',
    },
  },

  states: {
    idle: {
      on: {
        START: { target: 'welcome' },
      },
    },

    welcome: {
      on: {
        NEXT: {
          target: 'workspace',
          actions: ['markStepCompleted'],
        },
        SKIP: { target: 'workspace' },
      },
    },

    // The per-backend register substeps (claude/codex/gemini/opencode) were
    // retired: onboarding now auto-detects & imports existing accounts in the
    // WelcomePage `discover` phase, so the tour skips straight to monitoring.
    // (Git history holds the old `backends` compound state if it needs to
    // return.)
    workspace: {
      on: {
        NEXT: {
          target: 'monitoring',
          actions: ['markStepCompleted'],
        },
        BACK: { target: 'welcome' },
        SKIP: { target: 'monitoring' },
      },
    },

    monitoring: {
      on: {
        NEXT: {
          target: 'create_product',
          actions: ['markStepCompleted'],
        },
        BACK: { target: 'workspace' },
        SKIP: { target: 'create_product' },
      },
    },

    create_product: {
      on: {
        NEXT: {
          target: 'create_project',
          actions: ['markStepCompleted'],
        },
        BACK: { target: 'monitoring' },
        SKIP: { target: 'create_project' },
      },
    },

    create_project: {
      on: {
        NEXT: {
          target: 'create_team',
          actions: ['markStepCompleted'],
        },
        BACK: { target: 'create_product' },
        SKIP: { target: 'create_team' },
      },
    },

    create_team: {
      on: {
        NEXT: {
          target: 'complete',
          actions: ['markStepCompleted'],
        },
        BACK: { target: 'create_project' },
        SKIP: { target: 'complete' },
      },
    },

    // NOT a `type: 'final'` state. A final top-level state STOPS the actor
    // (status → 'done'), after which it ignores ALL events — including the
    // RESTART that the completion screen's "Go to dashboard" button sends to
    // dismiss itself. That left the completion popup stuck on screen forever
    // (App.vue `tourComplete = state === 'complete'` never flipped back).
    // Keeping it a normal state lets RESTART reset to idle (clearing
    // progress) and START re-run the tour. The auto-skip walker still
    // terminates here because `stateValueToKey('complete')` returns null.
    complete: {
      on: {
        RESTART: { target: 'idle', actions: ['clearProgress'] },
        START: { target: 'welcome' },
      },
    },
  },
})

/** The concrete machine type. Exported so consumers can annotate actors/
 *  snapshots (`Actor<TourMachine>`, `SnapshotFrom<TourMachine>`) via a
 *  type-only import — keeping xstate out of their runtime import graph. */
export type TourMachine = typeof tourMachine
