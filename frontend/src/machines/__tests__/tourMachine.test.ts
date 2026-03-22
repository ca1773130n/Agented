/**
 * Comprehensive unit tests for the XState v5 tour state machine.
 *
 * Tests the machine as a black box: createActor -> send events -> assert on
 * getSnapshot().value and .context. No Vue, no DOM, no mocks.
 *
 * Covers: all 10 states, forward/backward/skip navigation, SKIP_ALL guard,
 * RESTART reset, markStepCompleted action, clearProgress action, event
 * rejection in invalid states, and hierarchical backends substates.
 */

import { describe, it, expect, afterEach } from 'vitest'
import { createActor, type Actor } from 'xstate'
import { tourMachine } from '../tourMachine'

// Helper: create and start actor, track for cleanup
let activeActor: Actor<typeof tourMachine> | null = null

function startActor(machine = tourMachine) {
  const actor = createActor(machine)
  actor.start()
  activeActor = actor
  return actor
}

afterEach(() => {
  activeActor?.stop()
  activeActor = null
})

// Helper: navigate to a specific state via event sequence
function navigateTo(
  actor: Actor<typeof tourMachine>,
  events: Array<{ type: string }>
) {
  for (const event of events) {
    actor.send(event as any)
  }
}

// Common event sequences
const toWelcome = [{ type: 'START' }] as const
const toWorkspace = [...toWelcome, { type: 'NEXT' }] as const
const toBackendsClaude = [...toWorkspace, { type: 'NEXT' }] as const
const toBackendsCodex = [...toBackendsClaude, { type: 'NEXT' }] as const
const toBackendsGemini = [...toBackendsCodex, { type: 'NEXT' }] as const
const toBackendsOpencode = [...toBackendsGemini, { type: 'NEXT' }] as const
const toVerification = [...toBackendsOpencode, { type: 'NEXT' }] as const
const toComplete = [...toVerification, { type: 'NEXT' }] as const

// ---------------------------------------------------------------------------
// 1. Initial state
// ---------------------------------------------------------------------------

describe('initial state', () => {
  it('starts in idle with default context', () => {
    const actor = startActor()
    const snap = actor.getSnapshot()

    expect(snap.value).toBe('idle')
    expect(snap.context.instanceId).toBeNull()
    expect(snap.context.schemaVersion).toBe(1)
    expect(snap.context.completedSteps).toEqual([])
    expect(snap.status).toBe('active')
  })
})

// ---------------------------------------------------------------------------
// 2. Forward navigation (NEXT)
// ---------------------------------------------------------------------------

describe('forward navigation (NEXT)', () => {
  it('idle -> START -> welcome', () => {
    const actor = startActor()
    actor.send({ type: 'START' })
    expect(actor.getSnapshot().value).toBe('welcome')
  })

  it('welcome -> NEXT -> workspace (marks welcome completed)', () => {
    const actor = startActor()
    navigateTo(actor, [...toWelcome])
    actor.send({ type: 'NEXT' })

    const snap = actor.getSnapshot()
    expect(snap.value).toBe('workspace')
    expect(snap.context.completedSteps).toContain('welcome')
  })

  it('workspace -> NEXT -> backends.claude (marks workspace completed)', () => {
    const actor = startActor()
    navigateTo(actor, [...toWorkspace])
    actor.send({ type: 'NEXT' })

    const snap = actor.getSnapshot()
    expect(snap.value).toEqual({ backends: 'claude' })
    expect(snap.context.completedSteps).toContain('workspace')
  })

  it('backends.claude -> NEXT -> backends.codex (marks claude completed)', () => {
    const actor = startActor()
    navigateTo(actor, [...toBackendsClaude])
    actor.send({ type: 'NEXT' })

    const snap = actor.getSnapshot()
    expect(snap.value).toEqual({ backends: 'codex' })
    expect(snap.context.completedSteps).toContain(
      JSON.stringify({ backends: 'claude' })
    )
  })

  it('backends.codex -> NEXT -> backends.gemini', () => {
    const actor = startActor()
    navigateTo(actor, [...toBackendsCodex])
    actor.send({ type: 'NEXT' })
    expect(actor.getSnapshot().value).toEqual({ backends: 'gemini' })
  })

  it('backends.gemini -> NEXT -> backends.opencode', () => {
    const actor = startActor()
    navigateTo(actor, [...toBackendsGemini])
    actor.send({ type: 'NEXT' })
    expect(actor.getSnapshot().value).toEqual({ backends: 'opencode' })
  })

  it('backends.opencode -> NEXT -> verification (parent handler fires)', () => {
    const actor = startActor()
    navigateTo(actor, [...toBackendsOpencode])
    actor.send({ type: 'NEXT' })

    const snap = actor.getSnapshot()
    expect(snap.value).toBe('verification')
    // Parent backends NEXT handler runs markStepCompleted with current state
    expect(snap.context.completedSteps).toContain(
      JSON.stringify({ backends: 'opencode' })
    )
  })

  it('verification -> NEXT -> complete (final state)', () => {
    const actor = startActor()
    navigateTo(actor, [...toVerification])
    actor.send({ type: 'NEXT' })

    const snap = actor.getSnapshot()
    expect(snap.value).toBe('complete')
    expect(snap.status).toBe('done')
  })

  it('complete forward path accumulates all completed steps', () => {
    const actor = startActor()
    navigateTo(actor, [...toComplete])

    const snap = actor.getSnapshot()
    expect(snap.context.completedSteps).toEqual([
      'welcome',
      'workspace',
      JSON.stringify({ backends: 'claude' }),
      JSON.stringify({ backends: 'codex' }),
      JSON.stringify({ backends: 'gemini' }),
      JSON.stringify({ backends: 'opencode' }),
      'verification',
    ])
  })
})

// ---------------------------------------------------------------------------
// 3. Backward navigation (BACK)
// ---------------------------------------------------------------------------

describe('backward navigation (BACK)', () => {
  it('workspace -> BACK -> welcome', () => {
    const actor = startActor()
    navigateTo(actor, [...toWorkspace])
    actor.send({ type: 'BACK' })
    expect(actor.getSnapshot().value).toBe('welcome')
  })

  it('backends.claude -> BACK -> workspace (parent handler)', () => {
    const actor = startActor()
    navigateTo(actor, [...toBackendsClaude])
    actor.send({ type: 'BACK' })
    expect(actor.getSnapshot().value).toBe('workspace')
  })

  it('backends.codex -> BACK -> backends.claude', () => {
    const actor = startActor()
    navigateTo(actor, [...toBackendsCodex])
    actor.send({ type: 'BACK' })
    expect(actor.getSnapshot().value).toEqual({ backends: 'claude' })
  })

  it('backends.gemini -> BACK -> backends.codex', () => {
    const actor = startActor()
    navigateTo(actor, [...toBackendsGemini])
    actor.send({ type: 'BACK' })
    expect(actor.getSnapshot().value).toEqual({ backends: 'codex' })
  })

  it('backends.opencode -> BACK -> backends.gemini', () => {
    const actor = startActor()
    navigateTo(actor, [...toBackendsOpencode])
    actor.send({ type: 'BACK' })
    expect(actor.getSnapshot().value).toEqual({ backends: 'gemini' })
  })

  it('verification -> BACK -> backends (re-enters at initial child claude)', () => {
    const actor = startActor()
    navigateTo(actor, [...toVerification])
    actor.send({ type: 'BACK' })
    expect(actor.getSnapshot().value).toEqual({ backends: 'claude' })
  })

  it('idle: BACK event is ignored', () => {
    const actor = startActor()
    actor.send({ type: 'BACK' })
    expect(actor.getSnapshot().value).toBe('idle')
  })

  it('welcome: BACK event is ignored', () => {
    const actor = startActor()
    navigateTo(actor, [...toWelcome])
    actor.send({ type: 'BACK' })
    expect(actor.getSnapshot().value).toBe('welcome')
  })

  it('BACK does not modify completedSteps', () => {
    const actor = startActor()
    navigateTo(actor, [...toWorkspace])
    const stepsBefore = [...actor.getSnapshot().context.completedSteps]
    actor.send({ type: 'BACK' })
    expect(actor.getSnapshot().context.completedSteps).toEqual(stepsBefore)
  })
})

// ---------------------------------------------------------------------------
// 4. Skip navigation (SKIP)
// ---------------------------------------------------------------------------

describe('skip navigation (SKIP)', () => {
  it('welcome -> SKIP -> workspace (no markStepCompleted)', () => {
    const actor = startActor()
    navigateTo(actor, [...toWelcome])
    actor.send({ type: 'SKIP' })

    const snap = actor.getSnapshot()
    expect(snap.value).toBe('workspace')
    expect(snap.context.completedSteps).toEqual([])
  })

  it('workspace -> SKIP -> backends (no markStepCompleted)', () => {
    const actor = startActor()
    navigateTo(actor, [...toWelcome])
    actor.send({ type: 'SKIP' }) // skip welcome
    actor.send({ type: 'SKIP' }) // skip workspace

    const snap = actor.getSnapshot()
    expect(snap.value).toEqual({ backends: 'claude' })
    expect(snap.context.completedSteps).toEqual([])
  })

  it('backends.claude -> SKIP -> backends.codex (no markStepCompleted)', () => {
    const actor = startActor()
    navigateTo(actor, [...toBackendsClaude])
    actor.send({ type: 'SKIP' })
    expect(actor.getSnapshot().value).toEqual({ backends: 'codex' })
  })

  it('backends.codex -> SKIP -> backends.gemini', () => {
    const actor = startActor()
    navigateTo(actor, [...toBackendsCodex])
    actor.send({ type: 'SKIP' })
    expect(actor.getSnapshot().value).toEqual({ backends: 'gemini' })
  })

  it('backends.gemini -> SKIP -> backends.opencode', () => {
    const actor = startActor()
    navigateTo(actor, [...toBackendsGemini])
    actor.send({ type: 'SKIP' })
    expect(actor.getSnapshot().value).toEqual({ backends: 'opencode' })
  })

  it('backends.opencode -> SKIP -> verification (parent SKIP handler)', () => {
    const actor = startActor()
    navigateTo(actor, [...toBackendsOpencode])
    actor.send({ type: 'SKIP' })
    expect(actor.getSnapshot().value).toBe('verification')
  })

  it('verification -> SKIP -> complete', () => {
    const actor = startActor()
    navigateTo(actor, [...toVerification])
    actor.send({ type: 'SKIP' })

    const snap = actor.getSnapshot()
    expect(snap.value).toBe('complete')
    expect(snap.status).toBe('done')
  })

  it('skip-all path results in empty completedSteps', () => {
    const actor = startActor()
    actor.send({ type: 'START' })
    // Skip through every step
    actor.send({ type: 'SKIP' }) // welcome -> workspace
    actor.send({ type: 'SKIP' }) // workspace -> backends.claude
    actor.send({ type: 'SKIP' }) // claude -> codex
    actor.send({ type: 'SKIP' }) // codex -> gemini
    actor.send({ type: 'SKIP' }) // gemini -> opencode
    actor.send({ type: 'SKIP' }) // opencode -> verification (parent)
    actor.send({ type: 'SKIP' }) // verification -> complete

    const snap = actor.getSnapshot()
    expect(snap.value).toBe('complete')
    expect(snap.context.completedSteps).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// 5. SKIP_ALL global event
// ---------------------------------------------------------------------------

describe('SKIP_ALL global event', () => {
  it('default: SKIP_ALL does NOT transition (canSkipAll guard returns false)', () => {
    const actor = startActor()
    navigateTo(actor, [...toWelcome])
    actor.send({ type: 'SKIP_ALL' })
    expect(actor.getSnapshot().value).toBe('welcome')
  })

  it('default: SKIP_ALL is blocked from workspace', () => {
    const actor = startActor()
    navigateTo(actor, [...toWorkspace])
    actor.send({ type: 'SKIP_ALL' })
    expect(actor.getSnapshot().value).toBe('workspace')
  })

  it('default: SKIP_ALL is blocked from backends.claude', () => {
    const actor = startActor()
    navigateTo(actor, [...toBackendsClaude])
    actor.send({ type: 'SKIP_ALL' })
    expect(actor.getSnapshot().value).toEqual({ backends: 'claude' })
  })

  it('default: SKIP_ALL is blocked from verification', () => {
    const actor = startActor()
    navigateTo(actor, [...toVerification])
    actor.send({ type: 'SKIP_ALL' })
    expect(actor.getSnapshot().value).toBe('verification')
  })

  it('with guard override: SKIP_ALL from welcome -> complete', () => {
    const overridden = tourMachine.provide({
      guards: { canSkipAll: () => true },
    })
    const actor = createActor(overridden)
    actor.start()
    activeActor = actor

    actor.send({ type: 'START' })
    expect(actor.getSnapshot().value).toBe('welcome')

    actor.send({ type: 'SKIP_ALL' })
    const snap = actor.getSnapshot()
    expect(snap.value).toBe('complete')
    expect(snap.status).toBe('done')
  })

  it('with guard override: SKIP_ALL from workspace -> complete', () => {
    const overridden = tourMachine.provide({
      guards: { canSkipAll: () => true },
    })
    const actor = createActor(overridden)
    actor.start()
    activeActor = actor

    navigateTo(actor, [...toWorkspace])
    actor.send({ type: 'SKIP_ALL' })
    expect(actor.getSnapshot().value).toBe('complete')
  })

  it('with guard override: SKIP_ALL from backends.claude -> complete', () => {
    const overridden = tourMachine.provide({
      guards: { canSkipAll: () => true },
    })
    const actor = createActor(overridden)
    actor.start()
    activeActor = actor

    navigateTo(actor, [...toBackendsClaude])
    actor.send({ type: 'SKIP_ALL' })
    expect(actor.getSnapshot().value).toBe('complete')
  })

  it('with guard override: SKIP_ALL from verification -> complete', () => {
    const overridden = tourMachine.provide({
      guards: { canSkipAll: () => true },
    })
    const actor = createActor(overridden)
    actor.start()
    activeActor = actor

    navigateTo(actor, [...toVerification])
    actor.send({ type: 'SKIP_ALL' })
    expect(actor.getSnapshot().value).toBe('complete')
  })

  it('SKIP_ALL from idle with guard override -> complete', () => {
    const overridden = tourMachine.provide({
      guards: { canSkipAll: () => true },
    })
    const actor = createActor(overridden)
    actor.start()
    activeActor = actor

    actor.send({ type: 'SKIP_ALL' })
    expect(actor.getSnapshot().value).toBe('complete')
  })
})

// ---------------------------------------------------------------------------
// 6. RESTART global event
// ---------------------------------------------------------------------------

describe('RESTART global event', () => {
  it('from welcome: RESTART -> idle with cleared context', () => {
    const actor = startActor()
    navigateTo(actor, [...toWelcome])
    actor.send({ type: 'RESTART' })

    const snap = actor.getSnapshot()
    expect(snap.value).toBe('idle')
    expect(snap.context.instanceId).toBeNull()
    expect(snap.context.schemaVersion).toBe(1)
    expect(snap.context.completedSteps).toEqual([])
  })

  it('from backends.codex: RESTART -> idle with completedSteps cleared', () => {
    const actor = startActor()
    navigateTo(actor, [...toBackendsCodex])
    // Should have accumulated steps
    expect(actor.getSnapshot().context.completedSteps.length).toBeGreaterThan(0)

    actor.send({ type: 'RESTART' })
    const snap = actor.getSnapshot()
    expect(snap.value).toBe('idle')
    expect(snap.context.completedSteps).toEqual([])
  })

  it('from verification: RESTART -> idle', () => {
    const actor = startActor()
    navigateTo(actor, [...toVerification])
    actor.send({ type: 'RESTART' })
    expect(actor.getSnapshot().value).toBe('idle')
  })

  it('context is fully reset after RESTART', () => {
    const actor = startActor()
    navigateTo(actor, [...toVerification])

    actor.send({ type: 'RESTART' })
    const snap = actor.getSnapshot()
    expect(snap.context).toEqual({
      instanceId: null,
      schemaVersion: 1,
      completedSteps: [],
    })
  })

  it('from idle: RESTART -> idle (stays in idle with cleared context)', () => {
    const actor = startActor()
    actor.send({ type: 'RESTART' })
    expect(actor.getSnapshot().value).toBe('idle')
    expect(actor.getSnapshot().context.completedSteps).toEqual([])
  })

  it('can START again after RESTART', () => {
    const actor = startActor()
    navigateTo(actor, [...toWorkspace])
    actor.send({ type: 'RESTART' })
    actor.send({ type: 'START' })
    expect(actor.getSnapshot().value).toBe('welcome')
  })
})

// ---------------------------------------------------------------------------
// 7. markStepCompleted action
// ---------------------------------------------------------------------------

describe('markStepCompleted action', () => {
  it('adds current state name to completedSteps on NEXT from welcome', () => {
    const actor = startActor()
    navigateTo(actor, [...toWelcome])
    actor.send({ type: 'NEXT' })
    expect(actor.getSnapshot().context.completedSteps).toContain('welcome')
  })

  it('accumulates steps through multiple NEXT transitions', () => {
    const actor = startActor()
    navigateTo(actor, [...toBackendsCodex])

    const steps = actor.getSnapshot().context.completedSteps
    expect(steps).toContain('welcome')
    expect(steps).toContain('workspace')
    expect(steps).toContain(JSON.stringify({ backends: 'claude' }))
  })

  it('does not duplicate steps on revisit', () => {
    const actor = startActor()
    // Go to workspace
    navigateTo(actor, [...toWorkspace])
    expect(actor.getSnapshot().context.completedSteps).toContain('welcome')

    // Restart and go through welcome again
    actor.send({ type: 'RESTART' })
    actor.send({ type: 'START' })
    actor.send({ type: 'NEXT' }) // welcome -> workspace, marks 'welcome'

    const steps = actor.getSnapshot().context.completedSteps
    const welcomeCount = steps.filter((s: string) => s === 'welcome').length
    expect(welcomeCount).toBe(1)
  })

  it('serializes hierarchical state value as JSON string', () => {
    const actor = startActor()
    navigateTo(actor, [...toBackendsClaude])
    actor.send({ type: 'NEXT' }) // claude -> codex

    const steps = actor.getSnapshot().context.completedSteps
    // The step should be the JSON string of the compound state value
    expect(steps).toContain(JSON.stringify({ backends: 'claude' }))
  })
})

// ---------------------------------------------------------------------------
// 8. clearProgress action
// ---------------------------------------------------------------------------

describe('clearProgress action', () => {
  it('RESTART clears completedSteps', () => {
    const actor = startActor()
    navigateTo(actor, [...toVerification])
    expect(actor.getSnapshot().context.completedSteps.length).toBeGreaterThan(0)

    actor.send({ type: 'RESTART' })
    expect(actor.getSnapshot().context.completedSteps).toEqual([])
  })

  it('RESTART resets instanceId to null', () => {
    const actor = startActor()
    navigateTo(actor, [...toWorkspace])
    actor.send({ type: 'RESTART' })
    expect(actor.getSnapshot().context.instanceId).toBeNull()
  })

  it('RESTART resets schemaVersion to 1', () => {
    const actor = startActor()
    navigateTo(actor, [...toWorkspace])
    actor.send({ type: 'RESTART' })
    expect(actor.getSnapshot().context.schemaVersion).toBe(1)
  })
})

// ---------------------------------------------------------------------------
// 9. Event rejection in invalid states
// ---------------------------------------------------------------------------

describe('event rejection in invalid states', () => {
  it('idle: NEXT is ignored', () => {
    const actor = startActor()
    actor.send({ type: 'NEXT' })
    expect(actor.getSnapshot().value).toBe('idle')
  })

  it('idle: BACK is ignored', () => {
    const actor = startActor()
    actor.send({ type: 'BACK' })
    expect(actor.getSnapshot().value).toBe('idle')
  })

  it('idle: SKIP is ignored', () => {
    const actor = startActor()
    actor.send({ type: 'SKIP' })
    expect(actor.getSnapshot().value).toBe('idle')
  })

  it('complete: NEXT is ignored (final state)', () => {
    const actor = startActor()
    navigateTo(actor, [...toComplete])
    actor.send({ type: 'NEXT' })
    expect(actor.getSnapshot().value).toBe('complete')
    expect(actor.getSnapshot().status).toBe('done')
  })

  it('complete: BACK is ignored (final state)', () => {
    const actor = startActor()
    navigateTo(actor, [...toComplete])
    actor.send({ type: 'BACK' })
    expect(actor.getSnapshot().value).toBe('complete')
  })

  it('complete: SKIP is ignored (final state)', () => {
    const actor = startActor()
    navigateTo(actor, [...toComplete])
    actor.send({ type: 'SKIP' })
    expect(actor.getSnapshot().value).toBe('complete')
  })

  it('complete: SKIP_ALL is ignored (final state)', () => {
    const actor = startActor()
    navigateTo(actor, [...toComplete])
    actor.send({ type: 'SKIP_ALL' })
    expect(actor.getSnapshot().value).toBe('complete')
  })

  it('complete: RESTART is ignored (final state)', () => {
    const actor = startActor()
    navigateTo(actor, [...toComplete])
    actor.send({ type: 'RESTART' })
    // Final states do not process events
    expect(actor.getSnapshot().value).toBe('complete')
    expect(actor.getSnapshot().status).toBe('done')
  })

  it('welcome: BACK is ignored (no BACK handler)', () => {
    const actor = startActor()
    navigateTo(actor, [...toWelcome])
    actor.send({ type: 'BACK' })
    expect(actor.getSnapshot().value).toBe('welcome')
  })
})

// ---------------------------------------------------------------------------
// 10. Hierarchical backends substates
// ---------------------------------------------------------------------------

describe('hierarchical backends substates', () => {
  it('entering backends starts at initial child claude', () => {
    const actor = startActor()
    navigateTo(actor, [...toBackendsClaude])
    expect(actor.getSnapshot().value).toEqual({ backends: 'claude' })
  })

  it('BACK from verification goes to backends at initial child claude', () => {
    const actor = startActor()
    navigateTo(actor, [...toVerification])
    actor.send({ type: 'BACK' })
    // Re-enters backends at initial child, not where user left
    expect(actor.getSnapshot().value).toEqual({ backends: 'claude' })
  })

  it('all four backend substates are reachable', () => {
    const actor = startActor()
    navigateTo(actor, [...toBackendsClaude])
    expect(actor.getSnapshot().value).toEqual({ backends: 'claude' })

    actor.send({ type: 'NEXT' })
    expect(actor.getSnapshot().value).toEqual({ backends: 'codex' })

    actor.send({ type: 'NEXT' })
    expect(actor.getSnapshot().value).toEqual({ backends: 'gemini' })

    actor.send({ type: 'NEXT' })
    expect(actor.getSnapshot().value).toEqual({ backends: 'opencode' })
  })

  it('opencode has no local NEXT handler; parent NEXT fires', () => {
    const actor = startActor()
    navigateTo(actor, [...toBackendsOpencode])
    // opencode has no NEXT, so parent backends NEXT fires
    actor.send({ type: 'NEXT' })
    expect(actor.getSnapshot().value).toBe('verification')
  })

  it('opencode has no local SKIP handler; parent SKIP fires', () => {
    const actor = startActor()
    navigateTo(actor, [...toBackendsOpencode])
    actor.send({ type: 'SKIP' })
    expect(actor.getSnapshot().value).toBe('verification')
  })

  it('claude BACK uses parent handler to go to workspace', () => {
    const actor = startActor()
    navigateTo(actor, [...toBackendsClaude])
    // claude has no BACK, parent backends BACK fires
    actor.send({ type: 'BACK' })
    expect(actor.getSnapshot().value).toBe('workspace')
  })

  it('navigating back and forth within backends preserves completedSteps', () => {
    const actor = startActor()
    navigateTo(actor, [...toBackendsCodex])
    const stepsAtCodex = [...actor.getSnapshot().context.completedSteps]

    actor.send({ type: 'BACK' }) // codex -> claude
    actor.send({ type: 'NEXT' }) // claude -> codex (marks claude again, but dedup)

    // completedSteps should not shrink; claude was already marked
    expect(
      actor.getSnapshot().context.completedSteps.length
    ).toBeGreaterThanOrEqual(stepsAtCodex.length)
  })
})
