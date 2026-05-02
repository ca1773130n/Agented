/**
 * setupStatus tests (Plan 01-02).
 */
import { describe, expect, it, vi } from 'vitest'

import { deriveCompleted, fetchSetupStatus } from '../setupStatus'

const PAYLOAD = {
  instance_id: 'inst-abc',
  has_workspace: true,
  has_claude_account: false,
  has_codex_account: true,
  has_gemini_account: false,
  has_opencode_account: false,
  has_harness_synced: true,
  has_first_product: false,
}

describe('deriveCompleted', () => {
  it('maps API has_* fields to StepId-keyed completion', () => {
    const completed = deriveCompleted(PAYLOAD)
    expect(completed.workspace).toBe(true)
    expect(completed.claude).toBe(false)
    expect(completed.codex).toBe(true)
    expect(completed.gemini).toBe(false)
    expect(completed.opencode).toBe(false)
    expect(completed.harness).toBe(true)
    expect(completed.product).toBe(false)
  })

  it('always reports monitoring as not-complete (read-only step)', () => {
    expect(deriveCompleted(PAYLOAD).monitoring).toBe(false)
  })
})

describe('fetchSetupStatus', () => {
  it('parses a 200 response into the typed shape', async () => {
    const fetchFn = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(PAYLOAD),
    } as Response)
    const result = await fetchSetupStatus(fetchFn as unknown as typeof fetch)
    expect(result.unknown).toBe(false)
    expect(result.instanceId).toBe('inst-abc')
    expect(result.completed.codex).toBe(true)
  })

  it('returns the unknown sentinel on non-OK status', async () => {
    const fetchFn = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: () => Promise.resolve({}),
    } as Response)
    const result = await fetchSetupStatus(fetchFn as unknown as typeof fetch)
    expect(result.unknown).toBe(true)
    expect(result.instanceId).toBeNull()
  })

  it('returns the unknown sentinel on network error', async () => {
    const fetchFn = vi.fn().mockRejectedValue(new TypeError('network down'))
    const result = await fetchSetupStatus(fetchFn as unknown as typeof fetch)
    expect(result.unknown).toBe(true)
  })
})
