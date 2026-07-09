/**
 * Comprehensive unit tests for the XState v5 tour state machine.
 *
 * Tests the machine as a black box: createActor -> send events -> assert on
 * getSnapshot().value and .context. No Vue, no DOM, no mocks.
 *
 * Covers all states, forward/backward/skip navigation, SKIP_ALL guard,
 * RESTART reset, markStepCompleted action, clearProgress action, and event
 * rejection in invalid states.
 *
 * NOTE: the per-backend register substeps (backends.claude/codex/gemini/
 * opencode) were removed — onboarding now auto-detects accounts in the
 * WelcomePage `discover` phase, so the machine is flat: welcome -> workspace
 * -> monitoring -> create_product -> create_project -> create_team -> complete.
 */

import { describe, it, expect, afterEach } from 'vitest'
import { createActor, type Actor } from 'xstate'
import { tourMachine, type TourEvent } from '../tourMachine'

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
  events: ReadonlyArray<TourEvent>
) {
  for (const event of events) {
    actor.send(event)
  }
}

// Common event sequences
const toWelcome = [{ type: 'START' }] as const
const toWorkspace = [...toWelcome, { type: 'NEXT' }] as const
const toMonitoring = [...toWorkspace, { type: 'NEXT' }] as const
const toCreateProduct = [...toMonitoring, { type: 'NEXT' }] as const
const toCreateProject = [...toCreateProduct, { type: 'NEXT' }] as const
const toCreateTeam = [...toCreateProject, { type: 'NEXT' }] as const
const toComplete = [...toCreateTeam, { type: 'NEXT' }] as const

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

  it('workspace -> NEXT -> monitoring (marks workspace completed)', () => {
    const actor = startActor()
    navigateTo(actor, [...toWorkspace])
    actor.send({ type: 'NEXT' })

    const snap = actor.getSnapshot()
    expect(snap.value).toBe('monitoring')
    expect(snap.context.completedSteps).toContain('workspace')
  })

  it('monitoring -> NEXT -> create_product (marks monitoring completed)', () => {
    const actor = startActor()
    navigateTo(actor, [...toMonitoring])
    actor.send({ type: 'NEXT' })

    const snap = actor.getSnapshot()
    expect(snap.value).toBe('create_product')
    expect(snap.context.completedSteps).toContain('monitoring')
  })

  it('create_product -> NEXT -> create_project', () => {
    const actor = startActor()
    navigateTo(actor, [...toCreateProduct])
    actor.send({ type: 'NEXT' })

    const snap = actor.getSnapshot()
    expect(snap.value).toBe('create_project')
    expect(snap.context.completedSteps).toContain('create_product')
  })

  it('create_project -> NEXT -> create_team', () => {
    const actor = startActor()
    navigateTo(actor, [...toCreateProject])
    actor.send({ type: 'NEXT' })

    const snap = actor.getSnapshot()
    expect(snap.value).toBe('create_team')
    expect(snap.context.completedSteps).toContain('create_project')
  })

  it('create_team -> NEXT -> complete (reachable, NOT a final state)', () => {
    const actor = startActor()
    navigateTo(actor, [...toCreateTeam])
    actor.send({ type: 'NEXT' })

    const snap = actor.getSnapshot()
    expect(snap.value).toBe('complete')
    // complete must NOT be a final state — a final state stops the actor and
    // the completion screen's RESTART would be ignored, wedging the popup.
    expect(snap.status).toBe('active')
    expect(snap.context.completedSteps).toContain('create_team')
  })

  it('complete -> RESTART -> idle with cleared progress (dismiss the completion screen)', () => {
    const actor = startActor()
    navigateTo(actor, [...toCreateTeam])
    actor.send({ type: 'NEXT' })
    expect(actor.getSnapshot().value).toBe('complete')

    actor.send({ type: 'RESTART' })
    const snap = actor.getSnapshot()
    expect(snap.value).toBe('idle')
    expect(snap.status).toBe('active')
    expect(snap.context.completedSteps).toEqual([])
  })

  it('complete -> START -> welcome (re-run the tour from the completion screen)', () => {
    const actor = startActor()
    navigateTo(actor, [...toCreateTeam])
    actor.send({ type: 'NEXT' })
    actor.send({ type: 'START' })
    expect(actor.getSnapshot().value).toBe('welcome')
  })

  it('complete forward path accumulates all completed steps', () => {
    const actor = startActor()
    navigateTo(actor, [...toComplete])

    const snap = actor.getSnapshot()
    expect(snap.context.completedSteps).toEqual([
      'welcome',
      'workspace',
      'monitoring',
      'create_product',
      'create_project',
      'create_team',
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

  it('monitoring -> BACK -> workspace', () => {
    const actor = startActor()
    navigateTo(actor, [...toMonitoring])
    actor.send({ type: 'BACK' })
    expect(actor.getSnapshot().value).toBe('workspace')
  })

  it('create_product -> BACK -> monitoring', () => {
    const actor = startActor()
    navigateTo(actor, [...toCreateProduct])
    actor.send({ type: 'BACK' })
    expect(actor.getSnapshot().value).toBe('monitoring')
  })

  it('create_project -> BACK -> create_product', () => {
    const actor = startActor()
    navigateTo(actor, [...toCreateProject])
    actor.send({ type: 'BACK' })
    expect(actor.getSnapshot().value).toBe('create_product')
  })

  it('create_team -> BACK -> create_project', () => {
    const actor = startActor()
    navigateTo(actor, [...toCreateTeam])
    actor.send({ type: 'BACK' })
    expect(actor.getSnapshot().value).toBe('create_project')
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

  it('workspace -> SKIP -> monitoring (no markStepCompleted)', () => {
    const actor = startActor()
    navigateTo(actor, [...toWelcome])
    actor.send({ type: 'SKIP' }) // skip welcome
    actor.send({ type: 'SKIP' }) // skip workspace

    const snap = actor.getSnapshot()
    expect(snap.value).toBe('monitoring')
    expect(snap.context.completedSteps).toEqual([])
  })

  it('monitoring -> SKIP -> create_product', () => {
    const actor = startActor()
    navigateTo(actor, [...toMonitoring])
    actor.send({ type: 'SKIP' })
    expect(actor.getSnapshot().value).toBe('create_product')
  })

  it('create_product -> SKIP -> create_project', () => {
    const actor = startActor()
    navigateTo(actor, [...toCreateProduct])
    actor.send({ type: 'SKIP' })
    expect(actor.getSnapshot().value).toBe('create_project')
  })

  it('create_project -> SKIP -> create_team', () => {
    const actor = startActor()
    navigateTo(actor, [...toCreateProject])
    actor.send({ type: 'SKIP' })
    expect(actor.getSnapshot().value).toBe('create_team')
  })

  it('create_team -> SKIP -> complete', () => {
    const actor = startActor()
    navigateTo(actor, [...toCreateTeam])
    actor.send({ type: 'SKIP' })

    const snap = actor.getSnapshot()
    expect(snap.value).toBe('complete')
    expect(snap.status).toBe('active')
  })

  it('skip-all path results in empty completedSteps', () => {
    const actor = startActor()
    actor.send({ type: 'START' })
    actor.send({ type: 'SKIP' }) // welcome -> workspace
    actor.send({ type: 'SKIP' }) // workspace -> monitoring
    actor.send({ type: 'SKIP' }) // monitoring -> create_product
    actor.send({ type: 'SKIP' }) // create_product -> create_project
    actor.send({ type: 'SKIP' }) // create_project -> create_team
    actor.send({ type: 'SKIP' }) // create_team -> complete

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

  it('default: SKIP_ALL is blocked from monitoring', () => {
    const actor = startActor()
    navigateTo(actor, [...toMonitoring])
    actor.send({ type: 'SKIP_ALL' })
    expect(actor.getSnapshot().value).toBe('monitoring')
  })

  it('default: SKIP_ALL is blocked from create_product', () => {
    const actor = startActor()
    navigateTo(actor, [...toCreateProduct])
    actor.send({ type: 'SKIP_ALL' })
    expect(actor.getSnapshot().value).toBe('create_product')
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
    expect(snap.status).toBe('active')
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

  it('with guard override: SKIP_ALL from monitoring -> complete', () => {
    const overridden = tourMachine.provide({
      guards: { canSkipAll: () => true },
    })
    const actor = createActor(overridden)
    actor.start()
    activeActor = actor

    navigateTo(actor, [...toMonitoring])
    actor.send({ type: 'SKIP_ALL' })
    expect(actor.getSnapshot().value).toBe('complete')
  })

  it('with guard override: SKIP_ALL from create_product -> complete', () => {
    const overridden = tourMachine.provide({
      guards: { canSkipAll: () => true },
    })
    const actor = createActor(overridden)
    actor.start()
    activeActor = actor

    navigateTo(actor, [...toCreateProduct])
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

  it('from monitoring: RESTART -> idle with completedSteps cleared', () => {
    const actor = startActor()
    navigateTo(actor, [...toMonitoring])
    // Should have accumulated steps
    expect(actor.getSnapshot().context.completedSteps.length).toBeGreaterThan(0)

    actor.send({ type: 'RESTART' })
    const snap = actor.getSnapshot()
    expect(snap.value).toBe('idle')
    expect(snap.context.completedSteps).toEqual([])
  })

  it('from create_product: RESTART -> idle', () => {
    const actor = startActor()
    navigateTo(actor, [...toCreateProduct])
    actor.send({ type: 'RESTART' })
    expect(actor.getSnapshot().value).toBe('idle')
  })

  it('context is fully reset after RESTART', () => {
    const actor = startActor()
    navigateTo(actor, [...toCreateProduct])

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
    navigateTo(actor, [...toMonitoring])

    const steps = actor.getSnapshot().context.completedSteps
    expect(steps).toContain('welcome')
    expect(steps).toContain('workspace')
  })

  it('does not duplicate steps on revisit', () => {
    const actor = startActor()
    navigateTo(actor, [...toWorkspace])
    expect(actor.getSnapshot().context.completedSteps).toContain('welcome')

    actor.send({ type: 'RESTART' })
    actor.send({ type: 'START' })
    actor.send({ type: 'NEXT' }) // welcome -> workspace, marks 'welcome'

    const steps = actor.getSnapshot().context.completedSteps
    const welcomeCount = steps.filter((s: string) => s === 'welcome').length
    expect(welcomeCount).toBe(1)
  })

  it('re-marking an already-completed step is a no-op (dedup, no clear)', () => {
    const actor = startActor()
    actor.send({ type: 'START' })
    actor.send({ type: 'NEXT' }) // welcome -> workspace, marks 'welcome'
    actor.send({ type: 'BACK' }) // workspace -> welcome (no mark)
    actor.send({ type: 'NEXT' }) // welcome -> workspace again, re-marks 'welcome'

    const steps = actor.getSnapshot().context.completedSteps
    expect(steps.filter((s: string) => s === 'welcome')).toHaveLength(1)
  })
})

// ---------------------------------------------------------------------------
// 8. clearProgress action
// ---------------------------------------------------------------------------

describe('clearProgress action', () => {
  it('RESTART clears completedSteps', () => {
    const actor = startActor()
    navigateTo(actor, [...toCreateProduct])
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

  // complete is a normal (non-final) state: it has no NEXT/BACK/SKIP handler
  // so those are inert, but it DOES handle RESTART/START so the completion
  // screen can dismiss itself or re-run the tour.
  it('complete: NEXT is ignored (no handler)', () => {
    const actor = startActor()
    navigateTo(actor, [...toComplete])
    actor.send({ type: 'NEXT' })
    expect(actor.getSnapshot().value).toBe('complete')
    expect(actor.getSnapshot().status).toBe('active')
  })

  it('complete: BACK is ignored (no handler)', () => {
    const actor = startActor()
    navigateTo(actor, [...toComplete])
    actor.send({ type: 'BACK' })
    expect(actor.getSnapshot().value).toBe('complete')
  })

  it('complete: SKIP is ignored (no handler)', () => {
    const actor = startActor()
    navigateTo(actor, [...toComplete])
    actor.send({ type: 'SKIP' })
    expect(actor.getSnapshot().value).toBe('complete')
  })

  it('complete: SKIP_ALL is ignored (canSkipAll guard false)', () => {
    const actor = startActor()
    navigateTo(actor, [...toComplete])
    actor.send({ type: 'SKIP_ALL' })
    expect(actor.getSnapshot().value).toBe('complete')
  })

  it('complete: RESTART resets to idle (completion screen dismiss)', () => {
    const actor = startActor()
    navigateTo(actor, [...toComplete])
    actor.send({ type: 'RESTART' })
    expect(actor.getSnapshot().value).toBe('idle')
    expect(actor.getSnapshot().status).toBe('active')
    expect(actor.getSnapshot().context.completedSteps).toEqual([])
  })

  it('welcome: BACK is ignored (no BACK handler)', () => {
    const actor = startActor()
    navigateTo(actor, [...toWelcome])
    actor.send({ type: 'BACK' })
    expect(actor.getSnapshot().value).toBe('welcome')
  })
})
