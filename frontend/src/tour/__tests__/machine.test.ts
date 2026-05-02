/**
 * Topology tests for the v0.5.0 tour state machine (Plan 01-01).
 *
 * Pure-functional: no DOM, no API, no Vue. Drives the machine directly with
 * `createActor` and asserts state transitions. Covers OB-04 success criterion
 * #1 ("XState v5 state machine handles forward, backward, and skip
 * transitions between all tour states without entering invalid states").
 */
import { describe, expect, it } from 'vitest'
import { createActor } from 'xstate'

import { snapshotStepId, tourMachine } from '../machine'

function fresh() {
  const actor = createActor(tourMachine)
  actor.start()
  return actor
}

describe('tour machine — initial state', () => {
  it('starts in idle', () => {
    const actor = fresh()
    expect(actor.getSnapshot().value).toBe('idle')
  })

  it('START transitions idle → welcome', () => {
    const actor = fresh()
    actor.send({ type: 'START' })
    expect(actor.getSnapshot().value).toBe('welcome')
  })

  it('NEXT from idle is a no-op', () => {
    const actor = fresh()
    actor.send({ type: 'NEXT' })
    expect(actor.getSnapshot().value).toBe('idle')
  })
})

describe('tour machine — welcome state', () => {
  it('NEXT from welcome enters setup.workspace (initial child)', () => {
    const actor = fresh()
    actor.send({ type: 'START' })
    actor.send({ type: 'NEXT' })
    expect(actor.getSnapshot().value).toEqual({ setup: 'workspace' })
  })

  it('SKIP_TOUR from welcome jumps to complete', () => {
    const actor = fresh()
    actor.send({ type: 'START' })
    actor.send({ type: 'SKIP_TOUR' })
    expect(actor.getSnapshot().value).toBe('complete')
    expect(actor.getSnapshot().status).toBe('done')
  })
})

describe('tour machine — forward path through setup', () => {
  it('walks through every step and lands on complete', () => {
    const actor = fresh()
    actor.send({ type: 'START' })
    actor.send({ type: 'NEXT' })

    const path: unknown[] = []
    path.push(actor.getSnapshot().value)

    for (let i = 0; i < 8; i++) {
      actor.send({ type: 'NEXT' })
      path.push(actor.getSnapshot().value)
    }

    expect(path).toEqual([
      { setup: 'workspace' },
      { setup: { backends: 'claude' } },
      { setup: { backends: 'codex' } },
      { setup: { backends: 'gemini' } },
      { setup: { backends: 'opencode' } },
      { setup: 'monitoring' },
      { setup: 'harness' },
      { setup: 'product' },
      'complete',
    ])
  })

  it('SKIP from each step has the same target as NEXT', () => {
    const next = fresh()
    next.send({ type: 'START' })
    next.send({ type: 'NEXT' })
    const skip = fresh()
    skip.send({ type: 'START' })
    skip.send({ type: 'NEXT' })

    for (let i = 0; i < 8; i++) {
      next.send({ type: 'NEXT' })
      skip.send({ type: 'SKIP' })
      expect(skip.getSnapshot().value).toEqual(next.getSnapshot().value)
    }
  })
})

describe('tour machine — backward navigation', () => {
  it('BACK from setup.workspace returns to welcome', () => {
    const actor = fresh()
    actor.send({ type: 'START' })
    actor.send({ type: 'NEXT' })
    expect(actor.getSnapshot().value).toEqual({ setup: 'workspace' })
    actor.send({ type: 'BACK' })
    expect(actor.getSnapshot().value).toBe('welcome')
  })

  it('BACK from setup.backends.claude returns to setup.workspace', () => {
    const actor = fresh()
    actor.send({ type: 'START' })
    actor.send({ type: 'NEXT' })
    actor.send({ type: 'NEXT' })
    expect(actor.getSnapshot().value).toEqual({ setup: { backends: 'claude' } })
    actor.send({ type: 'BACK' })
    expect(actor.getSnapshot().value).toEqual({ setup: 'workspace' })
  })

  it('BACK from setup.backends.opencode returns to setup.backends.gemini', () => {
    const actor = fresh()
    actor.send({ type: 'START' })
    actor.send({ type: 'NEXT' })  // workspace
    actor.send({ type: 'NEXT' })  // claude
    actor.send({ type: 'NEXT' })  // codex
    actor.send({ type: 'NEXT' })  // gemini
    actor.send({ type: 'NEXT' })  // opencode
    expect(actor.getSnapshot().value).toEqual({
      setup: { backends: 'opencode' },
    })
    actor.send({ type: 'BACK' })
    expect(actor.getSnapshot().value).toEqual({
      setup: { backends: 'gemini' },
    })
  })

  it('BACK from setup.monitoring returns to setup.backends.opencode', () => {
    const actor = fresh()
    actor.send({ type: 'START' })
    for (let i = 0; i < 6; i++) {
      actor.send({ type: 'NEXT' })
    }
    expect(actor.getSnapshot().value).toEqual({ setup: 'monitoring' })
    actor.send({ type: 'BACK' })
    expect(actor.getSnapshot().value).toEqual({
      setup: { backends: 'opencode' },
    })
  })

  it('BACK from welcome stays on welcome (no transition)', () => {
    const actor = fresh()
    actor.send({ type: 'START' })
    actor.send({ type: 'BACK' })
    expect(actor.getSnapshot().value).toBe('welcome')
  })
})

describe('tour machine — terminal states', () => {
  it('NEXT from complete is a no-op (final state)', () => {
    const actor = fresh()
    actor.send({ type: 'START' })
    actor.send({ type: 'SKIP_TOUR' })
    expect(actor.getSnapshot().status).toBe('done')
    actor.send({ type: 'NEXT' })
    expect(actor.getSnapshot().value).toBe('complete')
  })
})

describe('snapshotStepId helper', () => {
  it('returns null for idle / welcome / complete', () => {
    const actor = fresh()
    expect(snapshotStepId(actor.getSnapshot())).toBeNull()
    actor.send({ type: 'START' })
    expect(snapshotStepId(actor.getSnapshot())).toBeNull()
    actor.send({ type: 'SKIP_TOUR' })
    expect(snapshotStepId(actor.getSnapshot())).toBeNull()
  })

  it('returns the leaf step id for setup children', () => {
    const actor = fresh()
    actor.send({ type: 'START' })
    actor.send({ type: 'NEXT' })
    expect(snapshotStepId(actor.getSnapshot())).toBe('workspace')
    actor.send({ type: 'NEXT' })
    expect(snapshotStepId(actor.getSnapshot())).toBe('claude')
    actor.send({ type: 'NEXT' })
    expect(snapshotStepId(actor.getSnapshot())).toBe('codex')
  })
})
