import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { readFileSync } from 'fs'
import { resolve } from 'path'
import TourProgressBar from '../TourProgressBar.vue'

const baseProps = {
  stepNumber: 3,
  totalSteps: 8,
  substepLabel: null as string | null,
  message: 'Configure your workspace',
  skippable: false,
  visible: true,
  stepTitle: 'Configure Workspace',
  skipNeedsConfirm: false,
}

describe('TourProgressBar', () => {
  it('shows step counter with correct numbers', () => {
    const wrapper = mount(TourProgressBar, { props: baseProps })
    expect(wrapper.find('.tour-step-counter').text()).toContain('STEP 3 OF 8')
  })

  it('shows substep label when provided', () => {
    const wrapper = mount(TourProgressBar, {
      props: { ...baseProps, substepLabel: 'Claude Code (1/4)' },
    })
    expect(wrapper.find('.tour-substep-label').exists()).toBe(true)
    expect(wrapper.find('.tour-substep-label').text()).toBe('Claude Code (1/4)')
  })

  it('hides substep label when null', () => {
    const wrapper = mount(TourProgressBar, { props: baseProps })
    expect(wrapper.find('.tour-substep-label').exists()).toBe(false)
  })

  it('hides skip button when skippable is false', () => {
    const wrapper = mount(TourProgressBar, { props: baseProps })
    expect(wrapper.find('.tour-skip-btn').exists()).toBe(false)
  })

  it('shows skip button when skippable is true', () => {
    const wrapper = mount(TourProgressBar, {
      props: { ...baseProps, skippable: true },
    })
    expect(wrapper.find('.tour-skip-btn').exists()).toBe(true)
  })

  it('emits next on next button click', async () => {
    const wrapper = mount(TourProgressBar, { props: baseProps })
    await wrapper.find('.tour-next-btn').trigger('click')
    expect(wrapper.emitted('next')).toBeTruthy()
  })

  it('emits skip on skip button click', async () => {
    const wrapper = mount(TourProgressBar, {
      props: { ...baseProps, skippable: true },
    })
    await wrapper.find('.tour-skip-btn').trigger('click')
    expect(wrapper.emitted('skip')).toBeTruthy()
  })

  it('does not render when visible is false', () => {
    const wrapper = mount(TourProgressBar, {
      props: { ...baseProps, visible: false },
    })
    expect(wrapper.find('.tour-progress-bar').exists()).toBe(false)
  })

  it('shows message text', () => {
    const wrapper = mount(TourProgressBar, { props: baseProps })
    expect(wrapper.find('.tour-step-message').text()).toBe('Configure your workspace')
  })

  it('has no hardcoded color values in style block', () => {
    const source = readFileSync(
      resolve(__dirname, '../TourProgressBar.vue'),
      'utf-8',
    )
    const styleMatch = source.match(/<style[^>]*>([\s\S]*?)<\/style>/)
    expect(styleMatch).toBeTruthy()
    const styleBlock = styleMatch![1]
    const hexColors = styleBlock.match(/#[0-9a-fA-F]{3,8}\b/g) || []
    expect(hexColors).toEqual([])
    const rgbColors = styleBlock.match(/rgba?\s*\(/g) || []
    expect(rgbColors).toEqual([])
  })

  it('has no hardcoded z-index values in style block', () => {
    const source = readFileSync(
      resolve(__dirname, '../TourProgressBar.vue'),
      'utf-8',
    )
    const styleMatch = source.match(/<style[^>]*>([\s\S]*?)<\/style>/)
    expect(styleMatch).toBeTruthy()
    const styleBlock = styleMatch![1]
    const hardcodedZIndex = styleBlock.match(/z-index:\s*\d+/g) || []
    expect(hardcodedZIndex).toEqual([])
  })
})
