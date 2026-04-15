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
    isWorkspaceConfigured: () => false,
    hasClaudeAccount: () => false,
    hasAnyBackend: () => false,
    isMonitoringConfigured: () => false,
    canSkipAll: () => false,
  },

  actions: {
    markStepCompleted: assign({
      completedSteps: ({ context, self }) => {
        // self.getSnapshot().value gives the current state value
        const snapshot = self.getSnapshot()
        const stateValue = snapshot.value
        const step = typeof stateValue === 'string' ? stateValue : JSON.stringify(stateValue)
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

    workspace: {
      on: {
        NEXT: {
          target: 'backends',
          actions: ['markStepCompleted'],
        },
        BACK: { target: 'welcome' },
        SKIP: { target: 'backends' },
      },
    },

    backends: {
      initial: 'claude',
      on: {
        NEXT: {
          target: 'monitoring',
          actions: ['markStepCompleted'],
        },
        BACK: { target: 'workspace' },
        SKIP: { target: 'monitoring' },
      },
      states: {
        claude: {
          on: {
            NEXT: {
              target: 'codex',
              actions: ['markStepCompleted'],
            },
            SKIP: { target: 'codex' },
          },
        },
        codex: {
          on: {
            NEXT: {
              target: 'gemini',
              actions: ['markStepCompleted'],
            },
            BACK: { target: 'claude' },
            SKIP: { target: 'gemini' },
          },
        },
        gemini: {
          on: {
            NEXT: {
              target: 'opencode',
              actions: ['markStepCompleted'],
            },
            BACK: { target: 'codex' },
            SKIP: { target: 'opencode' },
          },
        },
        opencode: {
          on: {
            BACK: { target: 'gemini' },
          },
        },
      },
    },

    monitoring: {
      on: {
        NEXT: {
          target: 'verification',
          actions: ['markStepCompleted'],
        },
        BACK: { target: 'backends' },
        SKIP: { target: 'verification' },
      },
    },

    verification: {
      on: {
        NEXT: {
          target: 'create_product',
          actions: ['markStepCompleted'],
        },
        BACK: { target: 'monitoring' },
        SKIP: { target: 'create_product' },
      },
    },

    create_product: {
      on: {
        NEXT: {
          target: 'create_project',
          actions: ['markStepCompleted'],
        },
        BACK: { target: 'verification' },
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

    complete: { type: 'final' },
  },
})
