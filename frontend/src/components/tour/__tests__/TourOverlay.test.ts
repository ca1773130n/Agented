import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import TourOverlay from '../TourOverlay.vue'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), currentRoute: { value: { path: '/' } } }),
}))

vi.mock('@floating-ui/vue', () => ({
  useFloating: vi.fn(() => ({
    floatingStyles: ref({ position: 'absolute', top: '100px', left: '200px' }),
    placement: ref('bottom'),
    middlewareData: ref({ arrow: { x: 50, y: 0 } }),
  })),
  offset: vi.fn(() => ({})),
  flip: vi.fn(() => ({})),
  shift: vi.fn(() => ({})),
  arrow: vi.fn(() => ({})),
  autoUpdate: vi.fn(),
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

  it('renders overlay when active with a step', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
    })
    expect(wrapper.find('.tour-overlay').exists()).toBe(true)
  })

  it('renders TourSpotlight child component', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
    })
    const spotlight = wrapper.findComponent({ name: 'TourSpotlight' })
    expect(spotlight.exists()).toBe(true)
  })

  it('renders TourTooltip child component', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
    })
    const tooltip = wrapper.findComponent({ name: 'TourTooltip' })
    expect(tooltip.exists()).toBe(true)
  })

  it('renders TourProgressBar child component', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
    })
    const progressBar = wrapper.findComponent({ name: 'TourProgressBar' })
    expect(progressBar.exists()).toBe(true)
  })

  it('shows step counter via TourProgressBar', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
    })
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
    expect(wrapper.find('.tour-spinner').exists()).toBe(true)
  })

  it('displays correct step counter text for different step numbers', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 5, totalSteps: 8 },
    })
    expect(wrapper.find('.tour-step-counter').text()).toContain('STEP 5 OF 8')
  })

  it('does not show substep label when null', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
    })
    expect(wrapper.find('.tour-substep-label').exists()).toBe(false)
  })

  it('shows effectiveTarget message when different from step message', () => {
    const customTarget = {
      target: '[data-tour="workspace-root"]',
      message: 'Override message from effective target',
    }
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: customTarget, substepLabel: null, stepNumber: 2, totalSteps: 8 },
    })
    expect(wrapper.find('.tour-step-message').text()).toBe('Override message from effective target')
    expect(wrapper.find('.tour-step-message').text()).not.toBe('Set the root directory')
  })

  it('emits events in correct order for rapid clicks', async () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: productStep, effectiveTarget: productStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
    })
    await wrapper.find('.tour-next-btn').trigger('click')
    await wrapper.find('.tour-next-btn').trigger('click')
    const nextEmits = wrapper.emitted('next')
    expect(nextEmits).toBeTruthy()
    expect(nextEmits!.length).toBe(2)
  })

  it('handles null step gracefully when active', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: null, effectiveTarget: null, substepLabel: null, stepNumber: 1, totalSteps: 8 },
    })
    expect(wrapper.find('.tour-overlay').exists()).toBe(false)
  })

  it('shows dim fallback when target element not in DOM', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
    })
    expect(wrapper.find('.tour-dim-fallback').exists()).toBe(true)
  })
})
