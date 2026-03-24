import { describe, it, expect, beforeEach, vi } from 'vitest'

// Mock vue-router
vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: vi.fn(),
    currentRoute: { value: { path: '/' } },
  }),
}))

describe('useTour', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('starts inactive', async () => {
    const { useTour } = await import('../useTour')
    const tour = useTour()
    expect(tour.active.value).toBe(false)
    expect(tour.currentStep.value).toBeNull()
  })

  it('activates and sets first step on startTour', async () => {
    const { useTour } = await import('../useTour')
    const tour = useTour()
    tour.startTour()
    expect(tour.active.value).toBe(true)
    expect(tour.currentStepIndex.value).toBe(0)
    expect(tour.currentStep.value).not.toBeNull()
  })

  it('advances to next step', async () => {
    const { useTour } = await import('../useTour')
    const tour = useTour()
    tour.startTour()
    // Step 0 has no substeps, so nextStep advances to step 1
    tour.nextStep()
    expect(tour.currentStepIndex.value).toBe(1)
  })

  it('advances substeps before major step', async () => {
    const { useTour } = await import('../useTour')
    const tour = useTour()
    tour.startTour()
    tour.nextStep() // step 0 → step 1 (backends, has 4 substeps)
    expect(tour.currentStepIndex.value).toBe(1)
    expect(tour.currentSubstepIndex.value).toBe(0)
    tour.nextStep() // substep 0 → substep 1
    expect(tour.currentStepIndex.value).toBe(1) // still on step 1
    expect(tour.currentSubstepIndex.value).toBe(1)
    tour.nextStep() // substep 1 → substep 2
    expect(tour.currentSubstepIndex.value).toBe(2)
    tour.nextStep() // substep 2 → substep 3
    expect(tour.currentSubstepIndex.value).toBe(3)
    tour.nextStep() // substep 3 (last) → step 2
    expect(tour.currentStepIndex.value).toBe(2)
    expect(tour.currentSubstepIndex.value).toBe(0)
  })

  it('skips only skippable steps', async () => {
    const { useTour } = await import('../useTour')
    const tour = useTour()
    tour.startTour()
    // Step 0 (workspace) is not skippable
    tour.skipStep()
    expect(tour.currentStepIndex.value).toBe(0) // didn't skip
  })

  it('persists state to localStorage', async () => {
    const { useTour } = await import('../useTour')
    const tour = useTour()
    tour.startTour()
    tour.nextStep()
    const stored = JSON.parse(localStorage.getItem('agented-tour-state') || '{}')
    expect(stored.currentStepIndex).toBe(1)
    expect(stored.active).toBe(true)
  })

  it('restores state from localStorage', async () => {
    localStorage.setItem('agented-tour-state', JSON.stringify({
      active: true,
      currentStepIndex: 3,
      completed: ['workspace', 'backends', 'monitoring'],
    }))
    vi.resetModules()
    const { useTour } = await import('../useTour')
    const tour = useTour()
    expect(tour.active.value).toBe(true)
    expect(tour.currentStepIndex.value).toBe(3)
  })

  it('ends tour and marks complete', async () => {
    const { useTour } = await import('../useTour')
    const tour = useTour()
    tour.startTour()
    tour.endTour()
    expect(tour.active.value).toBe(false)
    const stored = JSON.parse(localStorage.getItem('agented-tour-state') || '{}')
    expect(stored.tourComplete).toBe(true)
  })

  it('does not start if tour already completed', async () => {
    localStorage.setItem('agented-tour-state', JSON.stringify({ tourComplete: true }))
    vi.resetModules()
    const { useTour } = await import('../useTour')
    const tour = useTour()
    tour.startTour()
    expect(tour.active.value).toBe(false)
  })
})
