import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import TourOverlay from '../TourOverlay.vue'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), currentRoute: { value: { path: '/' } } }),
}))

const workspaceStep = {
  id: 'workspace',
  route: '/settings',
  target: '[data-tour="workspace-root"]',
  title: 'Workspace Directory',
  message: 'Set the root directory',
  skippable: false,
}

const productStep = {
  id: 'product',
  route: '/products',
  target: '[data-tour="create-product"]',
  title: 'First Product',
  message: 'Create your first product',
  skippable: true,
}

describe('TourOverlay', () => {
  it('does not render when inactive', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: false, step: null, effectiveTarget: null, substepLabel: null, stepNumber: 1, totalSteps: 8 },
    })
    expect(wrapper.find('.tour-overlay').exists()).toBe(false)
  })

  it('renders overlay and bottom bar when active with a step', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
    })
    expect(wrapper.find('.tour-overlay').exists()).toBe(true)
    expect(wrapper.find('.tour-bottom-bar').exists()).toBe(true)
    expect(wrapper.text()).toContain('STEP 2 OF 8')
    expect(wrapper.text()).toContain('Set the root directory')
  })

  it('shows skip button for skippable steps', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: productStep, effectiveTarget: productStep, substepLabel: null, stepNumber: 6, totalSteps: 8 },
    })
    expect(wrapper.find('.tour-skip-btn').exists()).toBe(true)
  })

  it('hides skip button for non-skippable steps', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
    })
    expect(wrapper.find('.tour-skip-btn').exists()).toBe(false)
  })

  it('emits next on next button click', async () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
    })
    await wrapper.find('.tour-next-btn').trigger('click')
    expect(wrapper.emitted('next')).toBeTruthy()
  })

  it('emits skip on skip button click', async () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: productStep, effectiveTarget: productStep, substepLabel: null, stepNumber: 6, totalSteps: 8 },
    })
    await wrapper.find('.tour-skip-btn').trigger('click')
    expect(wrapper.emitted('skip')).toBeTruthy()
  })

  it('shows substep label when provided', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: 'Claude Code (1/4)', stepNumber: 3, totalSteps: 8 },
    })
    expect(wrapper.text()).toContain('Claude Code (1/4)')
  })

  it('shows spinner when target not found', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
    })
    // Target won't be found in test DOM, so spinner should show
    expect(wrapper.find('.tour-spinner').exists()).toBe(true)
  })
})
