/**
 * Tests for the Phase 4 plan 04-01 setup-status integration.
 *
 * Three concerns under test:
 *   - fetchSetupStatus: parses the API response, returns null on failure.
 *   - setupStatusToCompleted: maps API booleans to tour state keys.
 *   - autoSkipCompletedSteps: walks the actor past completed steps via
 *     synthetic SKIP events. Uses the real machine — no mocks.
 */
import { describe, expect, it, vi } from 'vitest'
import { createActor } from 'xstate'

import { tourMachine } from '../../machines/tourMachine'
import {
  autoSkipCompletedSteps,
  fetchSetupStatus,
  setupStatusToCompleted,
} from '../useTourMachine'

const FRESH_PAYLOAD = {
  instance_id: 'inst-1',
  has_workspace: false,
  has_claude_account: false,
  has_codex_account: false,
  has_gemini_account: false,
  has_opencode_account: false,
  has_harness_synced: false,
  has_first_product: false,
}

describe('fetchSetupStatus', () => {
  it('returns the parsed payload on a 200', async () => {
    const fetchFn = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ ...FRESH_PAYLOAD, has_workspace: true }),
    } as Response)
    const got = await fetchSetupStatus(fetchFn as unknown as typeof fetch)
    expect(got?.has_workspace).toBe(true)
    expect(got?.instance_id).toBe('inst-1')
  })

  it('returns null on non-OK', async () => {
    const fetchFn = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: () => Promise.resolve({}),
    } as Response)
    expect(
      await fetchSetupStatus(fetchFn as unknown as typeof fetch),
    ).toBeNull()
  })

  it('returns null on network error', async () => {
    const fetchFn = vi.fn().mockRejectedValue(new TypeError('offline'))
    expect(
      await fetchSetupStatus(fetchFn as unknown as typeof fetch),
    ).toBeNull()
  })
})

describe('setupStatusToCompleted', () => {
  it('maps each has_* field to the corresponding tour state key', () => {
    const completed = setupStatusToCompleted({
      ...FRESH_PAYLOAD,
      has_workspace: true,
      has_first_product: true,
      has_harness_synced: true,
    })
    expect(completed.workspace).toBe(true)
    expect(completed.create_product).toBe(true)
    // The per-backend register substeps were removed (accounts are now
    // auto-detected in onboarding), so no backends.* keys are emitted.
    expect(completed['backends.claude']).toBeUndefined()
  })

  it('always reports monitoring as not-complete (read-only step)', () => {
    const completed = setupStatusToCompleted({ ...FRESH_PAYLOAD })
    expect(completed.monitoring).toBe(false)
  })
})

describe('autoSkipCompletedSteps — real machine walker', () => {
  function freshActor() {
    const actor = createActor(tourMachine)
    actor.start()
    actor.send({ type: 'START' })
    actor.send({ type: 'NEXT' }) // welcome → workspace
    return actor
  }

  it('skips workspace when has_workspace=true, stops at monitoring', () => {
    const actor = freshActor()
    expect(actor.getSnapshot().value).toBe('workspace')
    autoSkipCompletedSteps(
      actor,
      setupStatusToCompleted({ ...FRESH_PAYLOAD, has_workspace: true }),
    )
    // workspace is done → skip to monitoring, which is never auto-skipped.
    expect(actor.getSnapshot().value).toBe('monitoring')
    actor.stop()
  })

  it('is a no-op when nothing is completed', () => {
    const actor = freshActor()
    autoSkipCompletedSteps(actor, setupStatusToCompleted(FRESH_PAYLOAD))
    expect(actor.getSnapshot().value).toBe('workspace')
    actor.stop()
  })

  it('walks all the way to complete when every step is done', () => {
    const actor = freshActor()
    autoSkipCompletedSteps(actor, {
      workspace: true,
      'backends.claude': true,
      'backends.codex': true,
      'backends.gemini': true,
      'backends.opencode': true,
      monitoring: true,
      create_product: true,
      create_project: true,
      create_team: true,
    })
    // The tour machine has no top-level `type: 'final'` state — 'complete' is a
    // normal resting state (it stays interactive), so `.status` is 'active', not
    // 'done'. Assert the reached state like every other test in this file.
    expect(actor.getSnapshot().value).toBe('complete')
    actor.stop()
  })

  it('stops at idle / welcome / complete (no key to look up)', () => {
    const actor = createActor(tourMachine)
    actor.start()
    expect(actor.getSnapshot().value).toBe('idle')
    autoSkipCompletedSteps(actor, { workspace: true })
    // idle has no completion key, so the walker exits immediately.
    expect(actor.getSnapshot().value).toBe('idle')
    actor.stop()
  })
})
