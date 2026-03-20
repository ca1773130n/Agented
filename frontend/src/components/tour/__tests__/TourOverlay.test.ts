import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import TourOverlay from '../TourOverlay.vue'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), currentRoute: { value: { path: '/' } } }),
}))

describe('TourOverlay', () => {
  it('does not render when inactive', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: false, step: null, stepNumber: 1, totalSteps: 8 },
    })
    expect(wrapper.find('.tour-overlay').exists()).toBe(false)
  })

  it('renders overlay and bottom bar when active with a step', () => {
    const wrapper = mount(TourOverlay, {
      props: {
        active: true,
        step: {
          id: 'workspace',
          route: '/settings',
          target: '[data-tour="workspace-root"]',
          title: 'Workspace Directory',
          message: 'Set the root directory',
          skippable: false,
        },
        stepNumber: 2,
        totalSteps: 8,
      },
    })
    expect(wrapper.find('.tour-overlay').exists()).toBe(true)
    expect(wrapper.find('.tour-bottom-bar').exists()).toBe(true)
    expect(wrapper.text()).toContain('STEP 2 OF 8')
    expect(wrapper.text()).toContain('Set the root directory')
  })

  it('shows skip button for skippable steps', () => {
    const wrapper = mount(TourOverlay, {
      props: {
        active: true,
        step: {
          id: 'product',
          route: '/products',
          target: '[data-tour="create-product"]',
          title: 'First Product',
          message: 'Create your first product',
          skippable: true,
        },
        stepNumber: 6,
        totalSteps: 8,
      },
    })
    expect(wrapper.find('.tour-skip-btn').exists()).toBe(true)
  })

  it('hides skip button for non-skippable steps', () => {
    const wrapper = mount(TourOverlay, {
      props: {
        active: true,
        step: {
          id: 'workspace',
          route: '/settings',
          target: '[data-tour="workspace-root"]',
          title: 'Workspace Directory',
          message: 'Set the root directory',
          skippable: false,
        },
        stepNumber: 2,
        totalSteps: 8,
      },
    })
    expect(wrapper.find('.tour-skip-btn').exists()).toBe(false)
  })

  it('emits next on next button click', async () => {
    const wrapper = mount(TourOverlay, {
      props: {
        active: true,
        step: {
          id: 'workspace',
          route: '/settings',
          target: '[data-tour="workspace-root"]',
          title: 'Workspace',
          message: 'Set workspace',
          skippable: false,
        },
        stepNumber: 2,
        totalSteps: 8,
      },
    })
    await wrapper.find('.tour-next-btn').trigger('click')
    expect(wrapper.emitted('next')).toBeTruthy()
  })

  it('emits skip on skip button click', async () => {
    const wrapper = mount(TourOverlay, {
      props: {
        active: true,
        step: {
          id: 'product',
          route: '/products',
          target: '[data-tour="create-product"]',
          title: 'Product',
          message: 'Create product',
          skippable: true,
        },
        stepNumber: 6,
        totalSteps: 8,
      },
    })
    await wrapper.find('.tour-skip-btn').trigger('click')
    expect(wrapper.emitted('skip')).toBeTruthy()
  })
})
