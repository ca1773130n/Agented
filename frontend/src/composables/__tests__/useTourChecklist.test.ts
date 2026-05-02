import { describe, it, expect, beforeEach, vi } from 'vitest'
import { ref } from 'vue'
import { TOUR_STEP_DEFINITIONS } from '../../constants/tourSteps'

// Stand-in for the tour machine — useTourChecklist only reads
// `state.value` and `context.value.completedSteps`.
const stubState = ref<string>('idle')
const stubContext = ref<{ completedSteps: string[] }>({ completedSteps: [] })

vi.mock('../useTourMachine', () => ({
  useTourMachine: () => ({
    state: stubState,
    context: stubContext,
  }),
}))

import { useTourChecklist } from '../useTourChecklist'

describe('useTourChecklist (OB-35)', () => {
  beforeEach(() => {
    stubState.value = 'idle'
    stubContext.value = { completedSteps: [] }
  })

  it('checklistItems has one entry per TOUR_STEP_DEFINITIONS', () => {
    const { checklistItems } = useTourChecklist()
    expect(checklistItems.value).toHaveLength(TOUR_STEP_DEFINITIONS.length)
    const keys = checklistItems.value.map((i) => i.key)
    expect(keys).toEqual(TOUR_STEP_DEFINITIONS.map((d) => d.key))
  })

  it('marks each item completed iff its key is in completedSteps', () => {
    stubContext.value = {
      completedSteps: ['workspace', 'create_product'],
    }
    const { checklistItems } = useTourChecklist()
    const map = Object.fromEntries(
      checklistItems.value.map((i) => [i.key, i.completed]),
    )
    expect(map['workspace']).toBe(true)
    expect(map['create_product']).toBe(true)
    // A step not in completedSteps is not completed.
    expect(map['create_team']).toBe(false)
  })

  it('completedCount reflects the number of completed items', () => {
    stubContext.value = {
      completedSteps: ['workspace', 'create_product', 'create_project'],
    }
    const { completedCount } = useTourChecklist()
    expect(completedCount.value).toBe(3)
  })

  it('totalCount equals TOUR_STEP_DEFINITIONS.length', () => {
    const { totalCount } = useTourChecklist()
    expect(totalCount.value).toBe(TOUR_STEP_DEFINITIONS.length)
  })

  it('showChecklist is true once state === complete OR any step is completed', () => {
    const { showChecklist } = useTourChecklist()

    // Idle + zero completions: hidden.
    expect(showChecklist.value).toBe(false)

    // Any completion → shown, even mid-tour.
    stubContext.value = { completedSteps: ['workspace'] }
    expect(showChecklist.value).toBe(true)

    // Complete state with no completions (skipped everything) → still shown.
    stubContext.value = { completedSteps: [] }
    stubState.value = 'complete'
    expect(showChecklist.value).toBe(true)
  })
})
